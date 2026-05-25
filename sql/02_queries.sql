-- osu! Analytics — Complex Queries
-- IU000282 Critical Project 2

-- ============================================================
-- Query 1: Average PP and accuracy per rank tier
-- ============================================================
SELECT
    p.rank_tier,
    COUNT(p.userid)                     AS player_count,
    ROUND(AVG(p.pp), 2)                 AS avg_pp,
    ROUND(AVG(p.accuracy) * 100, 2)     AS avg_accuracy_pct,
    ROUND(AVG(p.play_count), 0)         AS avg_play_count,
    ROUND(AVG(p.play_time) / 3600.0, 1) AS avg_play_hours
FROM players p
WHERE p.rank_tier IS NOT NULL
GROUP BY p.rank_tier
HAVING COUNT(p.userid) >= 5
ORDER BY AVG(p.pp);

-- ============================================================
-- Query 2: Top 10 maps by average PP awarded (among ranked scores)
-- ============================================================
SELECT
    b.title,
    b.artist,
    b.version,
    ROUND(b.star_rating, 2)         AS star_rating,
    COUNT(s.score_id)               AS times_scored,
    ROUND(AVG(s.pp), 2)             AS avg_pp_awarded,
    ROUND(AVG(s.accuracy) * 100, 2) AS avg_accuracy_pct
FROM scores s
INNER JOIN beatmaps b ON s.beatmap_id = b.beatmap_id
WHERE s.pp IS NOT NULL AND s.pp > 0
GROUP BY b.beatmap_id, b.title, b.artist, b.version, b.star_rating
HAVING COUNT(s.score_id) >= 3
ORDER BY avg_pp_awarded DESC
LIMIT 10;

-- ============================================================
-- Query 3: Mod usage breakdown with avg performance
-- ============================================================
SELECT
    s.mods,
    COUNT(s.score_id)               AS total_scores,
    ROUND(AVG(s.pp), 2)             AS avg_pp,
    ROUND(AVG(s.accuracy) * 100, 2) AS avg_accuracy_pct,
    ROUND(AVG(b.star_rating), 2)    AS avg_map_difficulty
FROM scores s
INNER JOIN beatmaps b ON s.beatmap_id = b.beatmap_id
WHERE s.mods IS NOT NULL
GROUP BY s.mods
HAVING COUNT(s.score_id) >= 2
ORDER BY total_scores DESC;

-- ============================================================
-- Query 4: Players above their rank tier average
-- Core query for the improvement coach feature
-- ============================================================
SELECT
    p.username,
    p.rank_tier,
    ROUND(p.pp, 2)                              AS player_pp,
    ROUND(rta.avg_pp, 2)                        AS tier_avg_pp,
    ROUND(p.pp - rta.avg_pp, 2)                 AS pp_above_avg,
    ROUND(p.accuracy * 100, 2)                  AS player_acc_pct,
    ROUND(rta.avg_accuracy * 100, 2)            AS tier_avg_acc_pct,
    ROUND((p.accuracy - rta.avg_accuracy) * 100, 2) AS acc_above_avg
FROM players p
INNER JOIN rank_tier_averages rta ON p.rank_tier = rta.rank_tier
WHERE p.pp > rta.avg_pp
ORDER BY pp_above_avg DESC;

-- ============================================================
-- Query 5: Players performing above their tier average (inline subquery)
-- ============================================================
SELECT
    p.username,
    p.rank_tier,
    ROUND(p.pp, 2)  AS player_pp,
    ROUND(tier.avg_pp, 2) AS tier_avg_pp,
    ROUND(p.pp - tier.avg_pp, 2) AS pp_above_avg
FROM players p
INNER JOIN (
    SELECT rank_tier, AVG(pp) AS avg_pp
    FROM players
    WHERE pp IS NOT NULL
    GROUP BY rank_tier
) AS tier ON p.rank_tier = tier.rank_tier
WHERE p.pp > tier.avg_pp
ORDER BY pp_above_avg DESC
LIMIT 20;

-- ============================================================
-- Query 6: Accuracy vs PP correlation by rank tier (window function)
-- ============================================================
SELECT
    p.rank_tier,
    p.username,
    ROUND(p.pp, 2)              AS pp,
    ROUND(p.accuracy * 100, 2)  AS accuracy_pct,
    p.play_count,
    RANK() OVER (
        PARTITION BY p.rank_tier
        ORDER BY p.pp DESC
    )                           AS rank_within_tier
FROM players p
WHERE p.rank_tier IS NOT NULL
  AND p.pp IS NOT NULL
ORDER BY p.rank_tier, rank_within_tier;

-- ============================================================
-- Query 7: PP farming recommendations
-- Maps the player hasn't played that players in their tier scored high PP on
-- ============================================================
-- Replace :userid, :tier, :min_star, :max_star with actual values
SELECT
    b.title,
    b.artist,
    b.version,
    ROUND(b.star_rating, 2)     AS star_rating,
    ROUND(AVG(s.pp), 2)         AS avg_pp_at_tier,
    COUNT(s.score_id)           AS times_scored_by_tier
FROM beatmaps b
INNER JOIN scores s   ON b.beatmap_id = s.beatmap_id
INNER JOIN players p  ON s.userid = p.userid
WHERE p.rank_tier = :tier
  AND s.pp IS NOT NULL
  AND b.star_rating BETWEEN :min_star AND :max_star
  AND b.beatmap_id NOT IN (
      SELECT beatmap_id FROM scores WHERE userid = :userid
  )
GROUP BY b.beatmap_id, b.title, b.artist, b.version, b.star_rating
HAVING COUNT(s.score_id) >= 2
ORDER BY avg_pp_at_tier DESC
LIMIT 10;

-- ============================================================
-- Query 8: Accuracy improvement recommendations
-- Maps the player has already played with low accuracy, showing potential PP gain
-- ============================================================
SELECT
    b.title,
    b.artist,
    b.version,
    ROUND(b.star_rating, 2)         AS star_rating,
    ROUND(s.pp, 2)                  AS current_pp,
    ROUND(s.accuracy * 100, 2)      AS current_acc_pct,
    ROUND(tier_avg.avg_pp, 2)       AS avg_pp_at_tier,
    ROUND(tier_avg.avg_pp - s.pp, 2) AS potential_pp_gain
FROM scores s
INNER JOIN beatmaps b ON s.beatmap_id = b.beatmap_id
INNER JOIN (
    SELECT s2.beatmap_id, AVG(s2.pp) AS avg_pp
    FROM scores s2
    INNER JOIN players p ON s2.userid = p.userid
    WHERE p.rank_tier = :tier AND s2.pp IS NOT NULL
    GROUP BY s2.beatmap_id
) AS tier_avg ON tier_avg.beatmap_id = s.beatmap_id
WHERE s.userid = :userid
  AND s.accuracy < 0.97
  AND s.pp IS NOT NULL AND s.pp > 0
  AND tier_avg.avg_pp > s.pp
ORDER BY potential_pp_gain DESC
LIMIT 10;
