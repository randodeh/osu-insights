"""
Scrape top-50 scores from every beatmap leaderboard to collect new player IDs,
then bulk-fetch their stats and insert into the database.

Usage: python etl/ingest_beatmap_players.py
"""

import os, sys, time
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

SLEEP_SEC = 0.3

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
        pp           = EXCLUDED.pp,
        accuracy     = EXCLUDED.accuracy,
        play_count   = EXCLUDED.play_count,
        play_time    = EXCLUDED.play_time,
        total_score  = EXCLUDED.total_score,
        rank_tier    = assign_rank_tier(EXCLUDED.pp),
        last_updated = NOW()
"""


def get(url, params=None):
    headers = {"Authorization": f"Bearer {_getToken()}"}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code == 429:
        wait = int(resp.headers.get("Retry-After", 10))
        print(f"  Rate limited — sleeping {wait}s")
        time.sleep(wait)
        return get(url, params)
    if resp.status_code != 200:
        return None
    return resp.json()


def getBeatmapScores(beatmapId):
    data = get(f"{BASE_URL}/beatmaps/{beatmapId}/scores", params={"mode": "osu"})
    if not data:
        return []
    return data.get("scores", [])


def getUserStats(userId):
    data = get(f"{BASE_URL}/users/{userId}/osu")
    if not data:
        return None
    stats = data.get("statistics") or {}
    country = data.get("country") or {}
    pp = stats.get("pp") or 0
    if pp == 0:
        return None
    return {
        "userId":      data.get("id"),
        "username":    data.get("username"),
        "globalRank":  stats.get("global_rank"),
        "countryRank": stats.get("country_rank"),
        "pp":          pp,
        "accuracy":    (stats.get("hit_accuracy") or 0) / 100.0,
        "playCount":   stats.get("play_count"),
        "playTime":    stats.get("play_time"),
        "totalScore":  stats.get("total_score"),
        "joinDate":    data.get("join_date", "")[:10] if data.get("join_date") else None,
        "countryCode": data.get("country_code") or country.get("code"),
        "profileIconId": None,
    }


if __name__ == "__main__":
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    # Get all beatmap IDs
    cur.execute("SELECT beatmap_id FROM beatmaps ORDER BY beatmap_id")
    beatmap_ids = [r[0] for r in cur.fetchall()]
    print(f"Scanning {len(beatmap_ids)} beatmaps for new player IDs...\n")

    # Get existing player IDs
    cur.execute("SELECT userid FROM players")
    existing_ids = set(r[0] for r in cur.fetchall())
    print(f"Already have {len(existing_ids):,} players in DB\n")

    new_ids = set()
    for i, bid in enumerate(beatmap_ids):
        try:
            scores = getBeatmapScores(bid)
            for s in scores:
                uid = s.get("user_id") or (s.get("user") or {}).get("id")
                if uid and uid not in existing_ids:
                    new_ids.add(uid)
        except Exception as e:
            pass
        if (i + 1) % 100 == 0:
            print(f"  Scanned {i+1}/{len(beatmap_ids)} beatmaps | {len(new_ids)} new player IDs found")
        time.sleep(SLEEP_SEC)

    print(f"\nFound {len(new_ids)} new players. Fetching their stats...\n")

    added = 0
    errors = 0
    new_ids_list = list(new_ids)
    for i, uid in enumerate(new_ids_list):
        try:
            stats = getUserStats(uid)
            if stats:
                psycopg2.extras.execute_batch(cur, UPSERT_SQL, [stats])
                conn.commit()
                existing_ids.add(uid)
                added += 1
        except Exception as e:
            errors += 1
        if (i + 1) % 100 == 0:
            cur.execute("SELECT COUNT(*) FROM players")
            total = cur.fetchone()[0]
            print(f"  {i+1}/{len(new_ids_list)} processed | +{added} added | DB total: {total:,}")
        time.sleep(SLEEP_SEC)

    print(f"\nRefreshing tier averages...")
    cur.execute("CALL refresh_rank_tier_averages()")
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM players")
    final = cur.fetchone()[0]
    print(f"\nDone! Added {added} new players. DB total: {final:,}")
    cur.close()
    conn.close()
