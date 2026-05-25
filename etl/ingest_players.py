# pulls players + scores from the osu! API and saves to postgres
# usage: python etl/ingest_players.py --pages 5
#        python etl/ingest_players.py --user randx0 --scores-only

import os
import sys
import time
import argparse
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from osu_api import (
    getRanking, getUserByName, getUserScores,
    extractPlayerData, extractBeatmapData, extractScoreData
)

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME",     "osuanalytics"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

SLEEP_BETWEEN = 0.6  # seconds between API calls to stay under rate limit


def getConn():
    return psycopg2.connect(**DB_CONFIG)


def upsertPlayer(cur, playerDict):
    cur.execute("""
        INSERT INTO players (
            userid, username, global_rank, country_rank, pp, accuracy,
            play_count, play_time, total_score, join_date, rank_tier,
            country_code, profile_icon_id, last_updated
        ) VALUES (
            %(userId)s, %(username)s, %(globalRank)s, %(countryRank)s,
            %(pp)s, %(accuracy)s, %(playCount)s, %(playTime)s, %(totalScore)s,
            %(joinDate)s, assign_rank_tier(%(pp)s), %(countryCode)s,
            %(profileIconId)s, NOW()
        )
        ON CONFLICT (userid) DO UPDATE SET
            username        = EXCLUDED.username,
            global_rank     = EXCLUDED.global_rank,
            country_rank    = EXCLUDED.country_rank,
            pp              = EXCLUDED.pp,
            accuracy        = EXCLUDED.accuracy,
            play_count      = EXCLUDED.play_count,
            play_time       = EXCLUDED.play_time,
            total_score     = EXCLUDED.total_score,
            rank_tier       = assign_rank_tier(EXCLUDED.pp),
            profile_icon_id = EXCLUDED.profile_icon_id,
            last_updated    = NOW()
    """, playerDict)


def upsertBeatmap(cur, beatmapDict):
    cur.execute("""
        INSERT INTO beatmaps (
            beatmap_id, beatmapset_id, title, artist, version, creator,
            star_rating, length_seconds, bpm, approach_rate, overall_diff,
            circle_size, hp_drain, max_combo, ranked_status
        ) VALUES (
            %(beatmapId)s, %(beatmapsetId)s, %(title)s, %(artist)s, %(version)s,
            %(creator)s, %(starRating)s, %(lengthSeconds)s, %(bpm)s,
            %(approachRate)s, %(overallDiff)s, %(circleSize)s, %(hpDrain)s,
            %(maxCombo)s, %(rankedStatus)s
        )
        ON CONFLICT (beatmap_id) DO UPDATE SET
            title  = EXCLUDED.title,
            artist = EXCLUDED.artist
    """, beatmapDict)


def upsertScore(cur, scoreDict):
    if not scoreDict.get("scoreId") or not scoreDict.get("beatmapId"):
        return
    cur.execute("""
        INSERT INTO scores (
            score_id, userid, beatmap_id, score, accuracy, max_combo,
            count_300, count_100, count_50, count_miss, pp, mods,
            rank_grade, passed, play_date
        ) VALUES (
            %(scoreId)s, %(userId)s, %(beatmapId)s, %(score)s, %(accuracy)s,
            %(maxCombo)s, %(count300)s, %(count100)s, %(count50)s,
            %(countMiss)s, %(pp)s, %(mods)s, %(rankGrade)s, %(passed)s,
            %(playDate)s
        )
        ON CONFLICT (score_id) DO NOTHING
    """, scoreDict)


def ingestPlayer(userId, username, fetchScores=True):
    """Pull one player's data + their top scores into the DB."""
    conn = getConn()
    cur  = conn.cursor()
    try:
        # Player profile is already fetched by caller, but re-fetch by ID for full data
        from osu_api import getUserById
        userData   = getUserById(userId)
        playerData = extractPlayerData(userData)
        upsertPlayer(cur, playerData)
        conn.commit()
        print(f"  Saved player: {username} (#{playerData['globalRank']} | {playerData['pp']} pp)")

        if fetchScores:
            time.sleep(SLEEP_BETWEEN)
            scores = getUserScores(userId, scoreType="best", limit=100)
            for rawScore in scores:
                if rawScore.get("beatmap"):
                    bmData = extractBeatmapData(rawScore["beatmap"], rawScore.get("beatmapset"))
                    upsertBeatmap(cur, bmData)
                scoreData = extractScoreData(rawScore, userId)
                upsertScore(cur, scoreData)
            conn.commit()
            print(f"    Saved {len(scores)} scores for {username}")

    except Exception as e:
        conn.rollback()
        print(f"  ERROR on {username}: {e}")
    finally:
        cur.close()
        conn.close()


def ingestRankingPages(numPages=5):
    """Pull top players from the global PP ranking."""
    print(f"\nFetching {numPages} ranking pages ({numPages * 50} players)...\n")
    for page in range(1, numPages + 1):
        print(f"Page {page}/{numPages}...")
        rankData = getRanking(page=page)
        users    = rankData.get("ranking", [])

        for entry in users:
            userId   = entry["user"]["id"]
            username = entry["user"]["username"]
            print(f"  [{entry['rank_change'] if 'rank_change' in entry else ''}] {username}")
            ingestPlayer(userId, username, fetchScores=True)
            time.sleep(SLEEP_BETWEEN)

        time.sleep(1)  # extra pause between pages


def ingestSingleUser(username):
    """Pull one player by username (e.g. your own account)."""
    print(f"\nFetching player: {username}")
    userData   = getUserByName(username)
    playerData = extractPlayerData(userData)
    ingestPlayer(playerData["userId"], username, fetchScores=True)


def refreshTierAverages():
    """Recompute rank_tier_averages after ingestion."""
    conn = getConn()
    cur  = conn.cursor()
    try:
        cur.execute("CALL refresh_rank_tier_averages()")
        conn.commit()
        print("\nRank tier averages refreshed.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest osu! players from API")
    parser.add_argument("--pages",       type=int, default=5,     help="Ranking pages to fetch (50 players each)")
    parser.add_argument("--user",        type=str, default=None,  help="Fetch a specific username")
    parser.add_argument("--scores-only", action="store_true",     help="Only fetch scores for --user, skip ranking")
    parser.add_argument("--no-scores",   action="store_true",     help="Skip score ingestion (players only)")
    args = parser.parse_args()

    # Always fetch your own account first
    ingestSingleUser("randx0")
    time.sleep(SLEEP_BETWEEN)

    if args.user and args.user.lower() != "randx0":
        ingestSingleUser(args.user)
        time.sleep(SLEEP_BETWEEN)

    if not args.scores_only:
        ingestRankingPages(numPages=args.pages)

    refreshTierAverages()
    print("\nIngestion complete.")
