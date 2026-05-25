
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME",     "osuanalytics"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}


def getConn():
    return psycopg2.connect(**DB_CONFIG)


def query(sql, params=None):
    conn    = getConn()
    cur     = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    results = cur.fetchall()
    cur.close()
    return [dict(r) for r in results]


def queryOne(sql, params=None):
    results = query(sql, params)
    return results[0] if results else None


def execute(sql, params=None):
    conn = getConn()
    cur  = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    cur.close()


def getPlayerCoachWithFallback(username):
    """Get improvement coach data, falling back to nearest populated tier if player's tier has <5 players."""
    TIER_ORDER = ['Beginner','Bronze','Silver','Gold','Platinum','Emerald','Diamond','Master','Grandmaster','Ultimate']
    player = queryOne("SELECT * FROM players WHERE LOWER(username) = LOWER(%s)", (username,))
    if not player:
        return None
    tier = player['rank_tier']
    tierData = queryOne("SELECT player_count FROM rank_tier_averages WHERE rank_tier = %s", (tier,))
    if tierData and tierData['player_count'] >= 5:
        compareTier = tier
    else:
        # find nearest tier above with enough players
        idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else 0
        compareTier = None
        for t in TIER_ORDER[idx+1:]:
            td = queryOne("SELECT player_count FROM rank_tier_averages WHERE rank_tier = %s", (t,))
            if td and td['player_count'] >= 5:
                compareTier = t
                break
        if not compareTier:
            compareTier = 'Platinum'

    return queryOne("""
        SELECT
            p.userid, p.username, p.rank_tier, %s AS compare_tier,
            ROUND(p.pp, 2) AS player_pp,
            ROUND(rta.avg_pp, 2) AS tier_avg_pp,
            ROUND(p.pp - rta.avg_pp, 2) AS pp_vs_avg,
            CASE WHEN p.pp > rta.avg_pp * 1.1 THEN 'Above Average'
                 WHEN p.pp < rta.avg_pp * 0.9 THEN 'Needs Work'
                 ELSE 'Rank Average' END AS pp_status,
            ROUND(p.accuracy * 100, 2) AS player_acc_pct,
            ROUND(rta.avg_accuracy * 100, 2) AS tier_avg_acc_pct,
            ROUND((p.accuracy - rta.avg_accuracy) * 100, 2) AS acc_vs_avg,
            CASE WHEN p.accuracy > rta.avg_accuracy * 1.02 THEN 'Above Average'
                 WHEN p.accuracy < rta.avg_accuracy * 0.98 THEN 'Needs Work'
                 ELSE 'Rank Average' END AS acc_status,
            p.play_count,
            ROUND(rta.avg_play_count, 0) AS tier_avg_play_count,
            CASE WHEN p.play_count > rta.avg_play_count * 1.2 THEN 'Above Average'
                 WHEN p.play_count < rta.avg_play_count * 0.8 THEN 'Needs Work'
                 ELSE 'Rank Average' END AS play_count_status
        FROM players p
        INNER JOIN rank_tier_averages rta ON rta.rank_tier = %s
        WHERE LOWER(p.username) = LOWER(%s)
    """, (compareTier, compareTier, username))


def getTopPlayersForCycle(limit=50):
    """Get top players for the cycling widget."""
    return query("""
        SELECT userid, username, rank_tier, global_rank,
               ROUND(pp, 2) AS pp, country_code
        FROM players
        WHERE pp IS NOT NULL AND global_rank IS NOT NULL
        ORDER BY pp DESC
        LIMIT %s
    """, (limit,))


def getPlayerByName(username):
    return queryOne("""
        SELECT * FROM player_performance_summary
        WHERE LOWER(username) = LOWER(%s)
    """, (username,))


def getPlayerCoach(username):
    return queryOne("""
        SELECT * FROM improvement_coach
        WHERE LOWER(username) = LOWER(%s)
    """, (username,))


def getPlayerTopScores(userId, limit=10):
    return query("""
        SELECT
            s.pp,
            ROUND(s.accuracy * 100, 2)  AS accuracy_pct,
            s.mods,
            s.rank_grade,
            s.max_combo,
            b.title,
            b.artist,
            b.version,
            ROUND(b.star_rating, 2)     AS star_rating,
            s.play_date,
            b.beatmap_id
        FROM scores s
        INNER JOIN beatmaps b ON s.beatmap_id = b.beatmap_id
        WHERE s.userid = %s AND s.pp IS NOT NULL
        ORDER BY s.pp DESC
        LIMIT %s
    """, (userId, limit))


def getRankTierAverages():
    return query("""
        SELECT
            rank_tier,
            avg_pp,
            ROUND(avg_accuracy * 100, 2) AS avg_accuracy_pct,
            avg_play_count,
            ROUND(avg_play_time / 3600.0, 1) AS avg_play_hours,
            player_count
        FROM rank_tier_averages
        ORDER BY avg_pp
    """)


def getLeaderboard(orderBy="pp", limit=50):
    allowedColumns = {"pp", "global_rank", "accuracy", "play_count"}
    col = orderBy if orderBy in allowedColumns else "pp"
    colSql = f"p.{col}" if col != "global_rank" else "p.global_rank"
    direction = "ASC" if col == "global_rank" else "DESC"
    return query(f"""
        SELECT
            p.username,
            p.rank_tier,
            p.global_rank,
            ROUND(p.pp, 2)              AS pp,
            ROUND(p.accuracy * 100, 2)  AS accuracy_pct,
            p.play_count,
            p.country_code
        FROM players p
        WHERE p.{col} IS NOT NULL
        ORDER BY {colSql} {direction}
        LIMIT %s
    """, (limit,))


def getBeatmapStats(limit=20):
    return query("""
        SELECT bms.*, b.beatmapset_id
        FROM beatmap_meta_stats bms
        JOIN beatmaps b USING (beatmap_id)
        WHERE bms.total_scores > 0
        ORDER BY bms.avg_pp DESC NULLS LAST
        LIMIT %s
    """, (limit,))


def getTierDistribution():
    return query("""
        SELECT
            rank_tier,
            COUNT(*) AS player_count,
            ROUND(AVG(pp), 2) AS avg_pp
        FROM players
        WHERE rank_tier IS NOT NULL
        GROUP BY rank_tier
        ORDER BY avg_pp
    """)


def getModStats():
    return query("""
        SELECT
            mods,
            COUNT(score_id)               AS total_scores,
            ROUND(AVG(pp), 2)             AS avg_pp,
            ROUND(AVG(accuracy) * 100, 2) AS avg_accuracy_pct
        FROM scores
        WHERE mods IS NOT NULL AND pp > 0
        GROUP BY mods
        HAVING COUNT(score_id) >= 3
        ORDER BY total_scores DESC
        LIMIT 15
    """)


def getPlayerStarRange(userId):
    """Get the star rating range a player is comfortable with based on their top scores."""
    result = queryOne("""
        SELECT
            ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY b.star_rating)::numeric, 2) AS min_star,
            ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY b.star_rating)::numeric, 2) AS max_star,
            ROUND(AVG(b.star_rating)::numeric, 2) AS avg_star
        FROM scores s
        INNER JOIN beatmaps b ON s.beatmap_id = b.beatmap_id
        WHERE s.userid = %s AND s.pp IS NOT NULL AND s.pp > 0
    """, (userId,))
    if result and result.get('min_star'):
        return float(result['min_star']), float(result['max_star'])
    return 3.0, 6.0


def getPPFarmRecommendations(userId, tier, minStar, maxStar):
    """Maps the player hasn't played that their tier scores high PP on."""
    results = query("""
        SELECT
            b.beatmap_id,
            b.title,
            b.artist,
            b.version,
            ROUND(b.star_rating, 2)     AS star_rating,
            ROUND(AVG(s.pp), 2)         AS avg_pp_at_tier,
            COUNT(s.score_id)           AS times_scored
        FROM beatmaps b
        INNER JOIN scores s  ON b.beatmap_id = s.beatmap_id
        INNER JOIN players p ON s.userid = p.userid
        WHERE p.rank_tier = %s
          AND s.pp IS NOT NULL
          AND b.star_rating BETWEEN %s AND %s
          AND b.beatmap_id NOT IN (
              SELECT beatmap_id FROM scores WHERE userid = %s
          )
        GROUP BY b.beatmap_id, b.title, b.artist, b.version, b.star_rating
        HAVING COUNT(s.score_id) >= 1
        ORDER BY avg_pp_at_tier DESC
        LIMIT 10
    """, (tier, minStar, maxStar, userId))
    if results:
        return results
    # Fallback: any tier, just popular maps in star range
    return query("""
        SELECT
            b.beatmap_id,
            b.title,
            b.artist,
            b.version,
            ROUND(b.star_rating, 2)     AS star_rating,
            ROUND(AVG(s.pp), 2)         AS avg_pp_at_tier,
            COUNT(s.score_id)           AS times_scored
        FROM beatmaps b
        INNER JOIN scores s  ON b.beatmap_id = s.beatmap_id
        WHERE s.pp IS NOT NULL
          AND b.star_rating BETWEEN %s AND %s
          AND b.beatmap_id NOT IN (
              SELECT beatmap_id FROM scores WHERE userid = %s
          )
        GROUP BY b.beatmap_id, b.title, b.artist, b.version, b.star_rating
        HAVING COUNT(s.score_id) >= 2
        ORDER BY avg_pp_at_tier DESC
        LIMIT 10
    """, (minStar, maxStar, userId))


def getAccuracyRecommendations(userId, tier):
    """Maps the player has played with low accuracy, showing PP gain potential."""
    results = query("""
        SELECT
            b.beatmap_id,
            b.title,
            b.artist,
            b.version,
            ROUND(b.star_rating, 2)          AS star_rating,
            ROUND(s.pp, 2)                   AS current_pp,
            ROUND(s.accuracy * 100, 2)       AS current_acc_pct,
            ROUND(tier_avg.avg_pp, 2)        AS avg_pp_at_tier,
            ROUND(tier_avg.avg_pp - s.pp, 2) AS potential_pp_gain
        FROM scores s
        INNER JOIN beatmaps b ON s.beatmap_id = b.beatmap_id
        INNER JOIN (
            SELECT s2.beatmap_id, AVG(s2.pp) AS avg_pp
            FROM scores s2
            INNER JOIN players p ON s2.userid = p.userid
            WHERE p.rank_tier = %s AND s2.pp IS NOT NULL
            GROUP BY s2.beatmap_id
        ) AS tier_avg ON tier_avg.beatmap_id = s.beatmap_id
        WHERE s.userid = %s
          AND s.accuracy < 0.99
          AND s.pp IS NOT NULL AND s.pp > 0
          AND tier_avg.avg_pp > s.pp
        ORDER BY potential_pp_gain DESC
        LIMIT 10
    """, (tier, userId))
    if results:
        return results
    # Fallback: use any tier averages if own tier has no data
    return query("""
        SELECT
            b.beatmap_id,
            b.title,
            b.artist,
            b.version,
            ROUND(b.star_rating, 2)          AS star_rating,
            ROUND(s.pp, 2)                   AS current_pp,
            ROUND(s.accuracy * 100, 2)       AS current_acc_pct,
            ROUND(tier_avg.avg_pp, 2)        AS avg_pp_at_tier,
            ROUND(tier_avg.avg_pp - s.pp, 2) AS potential_pp_gain
        FROM scores s
        INNER JOIN beatmaps b ON s.beatmap_id = b.beatmap_id
        INNER JOIN (
            SELECT s2.beatmap_id, AVG(s2.pp) AS avg_pp
            FROM scores s2
            WHERE s2.pp IS NOT NULL
            GROUP BY s2.beatmap_id
        ) AS tier_avg ON tier_avg.beatmap_id = s.beatmap_id
        WHERE s.userid = %s
          AND s.accuracy < 0.99
          AND s.pp IS NOT NULL AND s.pp > 0
          AND tier_avg.avg_pp > s.pp
        ORDER BY potential_pp_gain DESC
        LIMIT 10
    """, (userId,))


def getDbStats():
    return queryOne("""
        SELECT
            (SELECT COUNT(*) FROM players)  AS total_players,
            (SELECT COUNT(*) FROM beatmaps) AS total_beatmaps,
            (SELECT COUNT(*) FROM scores)   AS total_scores
    """)
