"""
Fast bulk ingestion, pulls up to 10,000 players from the osu! ranking.

The ranking endpoint returns 50 players per page including their full stats,
so we don't need a separate user-lookup per player. No scores are fetched
(player-level data only) which makes this ~50x faster than ingest_players.py.

Usage:
  python etl/bulk_ingest.py              # all 200 pages = 10,000 players (~3 min)
  python etl/bulk_ingest.py --pages 20   # 1,000 players  (~30 sec)
"""

import os, sys, time, argparse
import psycopg2, psycopg2.extras
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from osu_api import _getToken, BASE_URL
import requests

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME",     "osuanalytics"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

BATCH_SIZE = 50   # rows per executemany call
SLEEP_SEC  = 0.4  # between API calls  osu! allows ~20 req/s on client credentials


def getRankingPage(page):
    headers = {"Authorization": f"Bearer {_getToken()}"}
    resp    = requests.get(
        f"{BASE_URL}/rankings/osu/performance",
        headers=headers,
        params={"page": page}
    )
    if resp.status_code == 429:
        wait = int(resp.headers.get("Retry-After", 10))
        print(f"  Rate limited — sleeping {wait}s")
        time.sleep(wait)
        return getRankingPage(page)
    resp.raise_for_status()
    return resp.json().get("ranking", [])


def parseEntry(entry):
    """Extract player data directly from a ranking entry (no extra API call needed)."""
    user    = entry.get("user", {})
    country = user.get("country") or {}
    # hit_accuracy in ranking is a percentage (e.g. 98.3), convert to 0–1
    rawAcc  = entry.get("hit_accuracy") or 0
    pp      = entry.get("pp") or 0
    return {
        "userId":         user.get("id"),
        "username":       user.get("username"),
        "globalRank":     entry.get("global_rank"),
        "countryRank":    entry.get("country_rank"),
        "pp":             pp,
        "accuracy":       rawAcc / 100.0,
        "playCount":      entry.get("play_count"),
        "playTime":       entry.get("play_time"),
        "totalScore":     entry.get("total_score"),
        "joinDate":       user.get("join_date", "")[:10] if user.get("join_date") else None,
        "countryCode":    user.get("country_code") or country.get("code"),
        "profileIconId":  None,
    }


UPSERT_SQL = """
    INSERT INTO players (
        userid, username, global_rank, country_rank, pp, accuracy,
        play_count, play_time, total_score, join_date, rank_tier,
        country_code, last_updated
    ) VALUES (
        %(userId)s, %(username)s, %(globalRank)s, %(countryRank)s,
        %(pp)s, %(accuracy)s, %(playCount)s, %(playTime)s, %(totalScore)s,
        %(joinDate)s, assign_rank_tier(%(pp)s), %(countryCode)s, NOW()
    )
    ON CONFLICT (userid) DO UPDATE SET
        username     = EXCLUDED.username,
        global_rank  = EXCLUDED.global_rank,
        country_rank = EXCLUDED.country_rank,
        pp           = EXCLUDED.pp,
        accuracy     = EXCLUDED.accuracy,
        play_count   = EXCLUDED.play_count,
        play_time    = EXCLUDED.play_time,
        total_score  = EXCLUDED.total_score,
        rank_tier    = assign_rank_tier(EXCLUDED.pp),
        last_updated = NOW()
"""


def run(numPages):
    conn  = psycopg2.connect(**DB_CONFIG)
    cur   = conn.cursor()
    total = 0
    batch = []

    print(f"Fetching {numPages} pages × 50 players = up to {numPages * 50} players\n")
    startTime = time.time()

    for page in range(1, numPages + 1):
        try:
            entries = getRankingPage(page)
        except Exception as e:
            print(f"  Page {page} error: {e}")
            time.sleep(2)
            continue

        for entry in entries:
            parsed = parseEntry(entry)
            if parsed["userId"]:
                batch.append(parsed)

        if len(batch) >= BATCH_SIZE:
            psycopg2.extras.execute_batch(cur, UPSERT_SQL, batch)
            conn.commit()
            total += len(batch)
            elapsed = time.time() - startTime
            rate    = total / elapsed
            pp_last = batch[-1].get("pp", 0)
            print(f"  Page {page:>3} | {total:>5} players saved | {rate:.1f}/s | last pp: {pp_last:.0f}")
            batch = []

        time.sleep(SLEEP_SEC)

    if batch:
        psycopg2.extras.execute_batch(cur, UPSERT_SQL, batch)
        conn.commit()
        total += len(batch)

    print(f"\nSaved {total} players in {time.time() - startTime:.1f}s")

    print("Refreshing rank tier averages...")
    cur.execute("CALL refresh_rank_tier_averages()")
    conn.commit()

    cur.execute("SELECT rank_tier, player_count, avg_pp FROM rank_tier_averages ORDER BY avg_pp")
    print("\nTier breakdown:")
    for row in cur.fetchall():
        print(f"  {row[0]:<14} {row[1]:>5} players   avg {row[2]:>8.0f} pp")

    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=200,
                        help="Pages to fetch (max 200, each page = 50 players)")
    args = parser.parse_args()
    run(min(args.pages, 200))
