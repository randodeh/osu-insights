-- osu! Analytics — Stored Procedures
-- IU000282 Critical Project 2

-- ============================================================
-- Procedure 1: get_player_profile
-- Returns full stats for a player + their rank tier comparison
-- Called by the Flask search page
-- ============================================================
CREATE OR REPLACE FUNCTION get_player_profile(p_username VARCHAR)
RETURNS TABLE (
    userid          BIGINT,
    username        VARCHAR,
    rank_tier       VARCHAR,
    global_rank     INT,
    country_code    VARCHAR,
    pp              NUMERIC,
    accuracy_pct    NUMERIC,
    play_count      INT,
    play_hours      NUMERIC,
    scores_in_db    BIGINT,
    avg_score_pp    NUMERIC,
    top_score_pp    NUMERIC,
    tier_avg_pp     NUMERIC,
    pp_status       VARCHAR,
    tier_avg_acc    NUMERIC,
    acc_status      VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ic.userid,
        ic.username,
        ic.rank_tier,
        p.global_rank,
        p.country_code,
        ic.player_pp,
        ic.player_acc_pct,
        p.play_count,
        ROUND(p.play_time / 3600.0, 1),
        pps.scores_in_db,
        pps.avg_score_pp,
        pps.top_score_pp,
        ic.tier_avg_pp,
        ic.pp_status,
        ic.tier_avg_acc_pct,
        ic.acc_status
    FROM improvement_coach ic
    INNER JOIN players p          ON ic.userid = p.userid
    LEFT JOIN  player_performance_summary pps ON ic.userid = pps.userid
    WHERE LOWER(ic.username) = LOWER(p_username)
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Procedure 2: get_rank_tier_stats
-- Returns the pre-computed averages for a given rank tier
-- ============================================================
CREATE OR REPLACE FUNCTION get_rank_tier_stats(p_tier VARCHAR)
RETURNS TABLE (
    rank_tier       VARCHAR,
    avg_pp          NUMERIC,
    avg_accuracy    NUMERIC,
    avg_play_count  NUMERIC,
    avg_play_hours  NUMERIC,
    player_count    INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        rta.rank_tier,
        rta.avg_pp,
        ROUND(rta.avg_accuracy * 100, 2),
        rta.avg_play_count,
        ROUND(rta.avg_play_time / 3600.0, 1),
        rta.player_count
    FROM rank_tier_averages rta
    WHERE rta.rank_tier = p_tier;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Procedure 3: refresh_rank_tier_averages
-- Recomputes the rank_tier_averages table from current player data
-- Call this after bulk inserts or API ingestion
-- ============================================================
CREATE OR REPLACE PROCEDURE refresh_rank_tier_averages()
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM rank_tier_averages;

    INSERT INTO rank_tier_averages (
        rank_tier, avg_pp, avg_accuracy, avg_play_count,
        avg_play_time, avg_score_pp, avg_score_acc, player_count, computed_at
    )
    SELECT
        p.rank_tier,
        ROUND(AVG(p.pp), 2),
        ROUND(AVG(p.accuracy), 6),
        ROUND(AVG(p.play_count), 2),
        ROUND(AVG(p.play_time), 2),
        ROUND(AVG(s.pp), 2),
        ROUND(AVG(s.accuracy), 6),
        COUNT(DISTINCT p.userid),
        NOW()
    FROM players p
    LEFT JOIN scores s ON p.userid = s.userid
    WHERE p.rank_tier IS NOT NULL
    GROUP BY p.rank_tier;

    RAISE NOTICE 'rank_tier_averages refreshed at %', NOW();
END;
$$;

-- ============================================================
-- Procedure 4: upsert_player
-- Insert a player or update their stats if they already exist
-- Called by the live API ingestion pipeline
-- ============================================================
CREATE OR REPLACE PROCEDURE upsert_player(
    p_userid        BIGINT,
    p_username      VARCHAR,
    p_global_rank   INT,
    p_country_rank  INT,
    p_pp            NUMERIC,
    p_accuracy      NUMERIC,
    p_play_count    INT,
    p_play_time     BIGINT,
    p_total_score   BIGINT,
    p_join_date     DATE,
    p_country_code  VARCHAR,
    p_icon_id       INT
)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO players (
        userid, username, global_rank, country_rank, pp, accuracy,
        play_count, play_time, total_score, join_date, rank_tier,
        country_code, profile_icon_id, last_updated
    ) VALUES (
        p_userid, p_username, p_global_rank, p_country_rank, p_pp, p_accuracy,
        p_play_count, p_play_time, p_total_score, p_join_date,
        assign_rank_tier(p_pp), p_country_code, p_icon_id, NOW()
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
        last_updated    = NOW();
END;
$$;
