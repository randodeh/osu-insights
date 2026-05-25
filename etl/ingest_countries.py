"""
Ingest players from every country's ranking.
Runs major osu! countries first, then all others.
Usage: python etl/ingest_countries.py
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

SLEEP_SEC = 0.4

# Major osu! countries first, then the rest
PRIORITY_COUNTRIES = [
    "KR","US","DE","PL","TW","JP","RU","GB","AU","BR",
    "FR","CA","HK","ID","CL","CN","MX","UA","FI","SE",
    "NL","IT","NO","AT","TR","SG","MY","NZ","BE","CZ",
    "HU","TH","ES","SK","DK","PT","RO","BG","HR","GR"
]

ALL_COUNTRIES = [
    "AF","AL","DZ","AD","AO","AG","AR","AM","AU","AT","AZ","BS","BH","BD","BB",
    "BY","BE","BZ","BJ","BT","BO","BA","BW","BR","BN","BG","BF","BI","CV","KH",
    "CM","CA","CF","TD","CL","CN","CO","KM","CG","CR","CI","HR","CU","CY","CZ",
    "DK","DJ","DM","DO","EC","EG","SV","GQ","ER","EE","SZ","ET","FJ","FI","FR",
    "GA","GM","GE","DE","GH","GR","GD","GT","GN","GW","GY","HT","HN","HK","HU",
    "IS","IN","ID","IR","IQ","IE","IL","IT","JM","JP","JO","KZ","KE","KI","KP",
    "KR","KW","KG","LA","LV","LB","LS","LR","LY","LI","LT","LU","MG","MW","MY",
    "MV","ML","MT","MH","MR","MU","MX","FM","MD","MC","MN","ME","MA","MZ","MM",
    "NA","NR","NP","NL","NZ","NI","NE","NG","NO","OM","PK","PW","PA","PG","PY",
    "PE","PH","PL","PT","QA","RO","RU","RW","KN","LC","VC","WS","SM","ST","SA",
    "SN","RS","SC","SL","SG","SK","SI","SB","SO","ZA","SS","ES","LK","SD","SR",
    "SE","CH","SY","TW","TJ","TZ","TH","TL","TG","TO","TT","TN","TR","TM","TV",
    "UG","UA","AE","GB","US","UY","UZ","VU","VE","VN","YE","ZM","ZW"
]

# Combine: priority first, then remaining
seen = set(PRIORITY_COUNTRIES)
COUNTRIES = PRIORITY_COUNTRIES + [c for c in ALL_COUNTRIES if c not in seen]

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


def getCountryPage(country, page):
    headers = {"Authorization": f"Bearer {_getToken()}"}
    resp = requests.get(
        f"{BASE_URL}/rankings/osu/performance",
        headers=headers,
        params={"country": country, "page": page}
    )
    if resp.status_code == 429:
        wait = int(resp.headers.get("Retry-After", 10))
        print(f"    Rate limited — sleeping {wait}s")
        time.sleep(wait)
        return getCountryPage(country, page)
    if resp.status_code != 200:
        return []
    return resp.json().get("ranking", [])


def parseEntry(entry):
    user    = entry.get("user", {})
    country = user.get("country") or {}
    rawAcc  = entry.get("hit_accuracy") or 0
    return {
        "userId":      user.get("id"),
        "username":    user.get("username"),
        "globalRank":  entry.get("global_rank"),
        "countryRank": entry.get("country_rank"),
        "pp":          entry.get("pp") or 0,
        "accuracy":    rawAcc / 100.0,
        "playCount":   entry.get("play_count"),
        "playTime":    entry.get("play_time"),
        "totalScore":  entry.get("total_score"),
        "joinDate":    user.get("join_date", "")[:10] if user.get("join_date") else None,
        "countryCode": user.get("country_code") or country.get("code"),
        "profileIconId": None,
    }


def ingestCountry(cur, conn, country):
    added = 0
    for page in range(1, 201):  # up to 200 pages = 10,000 per country
        entries = getCountryPage(country, page)
        if not entries:
            break
        batch = [parseEntry(e) for e in entries if e.get("user", {}).get("id")]
        if batch:
            psycopg2.extras.execute_batch(cur, UPSERT_SQL, batch)
            conn.commit()
            added += len(batch)
        if len(entries) < 50:
            break
        time.sleep(SLEEP_SEC)
    return added


if __name__ == "__main__":
    conn  = psycopg2.connect(**DB_CONFIG)
    cur   = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM players")
    start_count = cur.fetchone()[0]
    print(f"Starting with {start_count:,} players\n")

    grand_total = 0
    for i, country in enumerate(COUNTRIES):
        try:
            n = ingestCountry(cur, conn, country)
            grand_total += n
            cur.execute("SELECT COUNT(*) FROM players")
            total = cur.fetchone()[0]
            print(f"[{i+1}/{len(COUNTRIES)}] {country}: +{n} players | Total in DB: {total:,}")
        except Exception as e:
            print(f"[{i+1}/{len(COUNTRIES)}] {country}: ERROR — {e}")

    print(f"\nRefreshing tier averages...")
    cur.execute("CALL refresh_rank_tier_averages()")
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM players")
    end_count = cur.fetchone()[0]
    print(f"\nDone! {start_count:,} → {end_count:,} players (+{end_count - start_count:,} new)")
    cur.close()
    conn.close()
