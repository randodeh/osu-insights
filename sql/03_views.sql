-- osu! Analytics — Views
-- IU000282 Critical Project 2

-- ============================================================
-- View 1: player_performance_summary
-- One row per player with all key stats + rank tier
-- Used by the Flask player search page
-- ============================================================
CREATE OR REPLACE VIEW player_performance_summary AS
SELECT
    p.userid,
    p.username,
    p.rank_tier,
    p.global_rank,
    p.country_code,
    p.profile_icon_id,
    ROUND(p.pp, 2)                          AS pp,
    ROUND(p.accuracy * 100, 4)              AS accuracy_pct,
    p.play_count,
    ROUND(p.play_time / 3600.0, 1)          AS play_hours,
    COUNT(s.score_id)                       AS scores_in_db,
    ROUND(AVG(s.pp), 2)                     AS avg_score_pp,
    ROUND(AVG(s.accuracy) * 100, 2)         AS avg_score_acc_pct,
    ROUND(MAX(s.pp), 2)                     AS top_score_pp,
    p.join_date,
    p.last_updated
FROM players p
LEFT JOIN scores s ON p.userid = s.userid
GROUP BY
    p.userid, p.username, p.rank_tier, p.global_rank,
    p.country_code, p.profile_icon_id, p.pp, p.accuracy,
    p.play_count, p.play_time, p.join_date, p.last_updated;

-- ============================================================
-- View 2: beatmap_meta_stats
-- Per-beatmap aggregated stats across all scores
-- Used by the beatmap explorer page
-- ============================================================
CREATE OR REPLACE VIEW beatmap_meta_stats AS
SELECT
    b.beatmap_id,
    b.title,
    b.artist,
    b.version,
    ROUND(b.star_rating, 2)         AS star_rating,
    b.length_seconds,
    b.bpm,
    COUNT(s.score_id)               AS total_scores,
    ROUND(AVG(s.pp), 2)             AS avg_pp,
    ROUND(MAX(s.pp), 2)             AS top_pp,
    ROUND(AVG(s.accuracy) * 100, 2) AS avg_accuracy_pct,
    ROUND(AVG(s.max_combo), 0)      AS avg_combo
FROM beatmaps b
LEFT JOIN scores s ON b.beatmap_id = s.beatmap_id
GROUP BY
    b.beatmap_id, b.title, b.artist, b.version,
    b.star_rating, b.length_seconds, b.bpm;

-- ============================================================
-- View 3: improvement_coach
-- Each player compared to their rank tier average
-- The core output for the "improvement coach" feature
-- ============================================================
CREATE OR REPLACE VIEW improvement_coach AS
SELECT
    p.userid,
    p.username,
    p.rank_tier,
    ROUND(p.pp, 2)                                      AS player_pp,
    ROUND(rta.avg_pp, 2)                                AS tier_avg_pp,
    ROUND(p.pp - rta.avg_pp, 2)                         AS pp_vs_avg,
    CASE
        WHEN p.pp > rta.avg_pp * 1.1  THEN 'Above Average'
        WHEN p.pp < rta.avg_pp * 0.9  THEN 'Needs Work'
        ELSE 'Rank Average'
    END                                                 AS pp_status,

    ROUND(p.accuracy * 100, 2)                          AS player_acc_pct,
    ROUND(rta.avg_accuracy * 100, 2)                    AS tier_avg_acc_pct,
    ROUND((p.accuracy - rta.avg_accuracy) * 100, 2)     AS acc_vs_avg,
    CASE
        WHEN p.accuracy > rta.avg_accuracy * 1.02  THEN 'Above Average'
        WHEN p.accuracy < rta.avg_accuracy * 0.98  THEN 'Needs Work'
        ELSE 'Rank Average'
    END                                                 AS acc_status,

    p.play_count,
    ROUND(rta.avg_play_count, 0)                        AS tier_avg_play_count,
    CASE
        WHEN p.play_count > rta.avg_play_count * 1.2   THEN 'Above Average'
        WHEN p.play_count < rta.avg_play_count * 0.8   THEN 'Needs Work'
        ELSE 'Rank Average'
    END                                                 AS play_count_status
FROM players p
INNER JOIN rank_tier_averages rta ON p.rank_tier = rta.rank_tier;
