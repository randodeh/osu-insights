-- osu! Analytics Database Schema
-- IU000282 Critical Project 2
-- Database: osuanalytics

-- ============================================================
-- Drop existing tables (safe re-run)
-- ============================================================
DROP TABLE IF EXISTS scores CASCADE;
DROP TABLE IF EXISTS beatmaps CASCADE;
DROP TABLE IF EXISTS players CASCADE;
DROP TABLE IF EXISTS rank_tier_averages CASCADE;

-- ============================================================
-- 1. players
-- One row per unique player (userid is the stable osu! ID)
-- ============================================================
CREATE TABLE players (
    userid          BIGINT PRIMARY KEY,
    username        VARCHAR(255) NOT NULL,
    global_rank     INT,
    country_rank    INT,
    pp              NUMERIC(10, 2),
    accuracy        NUMERIC(6, 4),
    play_count      INT,
    play_time       BIGINT,
    total_score     BIGINT,
    join_date       DATE,
    rank_tier       VARCHAR(20),
    country_code    VARCHAR(5),
    profile_icon_id INT,
    last_updated    TIMESTAMP DEFAULT NOW(),

    CONSTRAINT chk_pp           CHECK (pp >= 0),
    CONSTRAINT chk_accuracy     CHECK (accuracy BETWEEN 0 AND 1),
    CONSTRAINT chk_play_count   CHECK (play_count >= 0),
    CONSTRAINT chk_rank_tier    CHECK (rank_tier IN (
        'Beginner','Bronze','Silver','Gold','Platinum',
        'Emerald','Diamond','Master','Grandmaster','Ultimate'
    ))
);

-- ============================================================
-- 2. beatmaps
-- One row per unique beatmap (individual difficulty)
-- ============================================================
CREATE TABLE beatmaps (
    beatmap_id      INT PRIMARY KEY,
    beatmapset_id   INT,
    title           VARCHAR(500),
    artist          VARCHAR(255),
    version         VARCHAR(255),
    creator         VARCHAR(255),
    star_rating     NUMERIC(5, 2),
    length_seconds  INT,
    bpm             NUMERIC(7, 2),
    approach_rate   NUMERIC(5, 2),
    overall_diff    NUMERIC(5, 2),
    circle_size     NUMERIC(5, 2),
    hp_drain        NUMERIC(5, 2),
    max_combo       INT,
    ranked_status   VARCHAR(20),

    CONSTRAINT chk_star         CHECK (star_rating >= 0),
    CONSTRAINT chk_length       CHECK (length_seconds >= 0),
    CONSTRAINT chk_bpm          CHECK (bpm >= 0)
);

-- ============================================================
-- 3. scores
-- One row per score set by a player on a beatmap
-- ============================================================
CREATE TABLE scores (
    score_id        BIGINT PRIMARY KEY,
    userid          BIGINT NOT NULL REFERENCES players(userid) ON DELETE CASCADE,
    beatmap_id      INT NOT NULL REFERENCES beatmaps(beatmap_id) ON DELETE CASCADE,
    score           BIGINT,
    accuracy        NUMERIC(6, 4),
    max_combo       INT,
    count_300       INT,
    count_100       INT,
    count_50        INT,
    count_miss      INT,
    pp              NUMERIC(10, 2),
    mods            VARCHAR(50),
    rank_grade      VARCHAR(5),
    passed          BOOLEAN DEFAULT TRUE,
    play_date       TIMESTAMP,

    CONSTRAINT chk_accuracy     CHECK (accuracy BETWEEN 0 AND 1),
    CONSTRAINT chk_pp           CHECK (pp >= 0),
    CONSTRAINT chk_combo        CHECK (max_combo >= 0)
);

-- ============================================================
-- 4. rank_tier_averages
-- Pre-computed averages per rank tier for the improvement coach
-- Populated by a stored procedure, not raw ETL
-- ============================================================
CREATE TABLE rank_tier_averages (
    rank_tier       VARCHAR(20) PRIMARY KEY,
    avg_pp          NUMERIC(10, 2),
    avg_accuracy    NUMERIC(6, 4),
    avg_play_count  NUMERIC(10, 2),
    avg_play_time   NUMERIC(15, 2),
    avg_score_pp    NUMERIC(10, 2),
    avg_score_acc   NUMERIC(6, 4),
    player_count    INT,
    computed_at     TIMESTAMP DEFAULT NOW(),

    CONSTRAINT chk_rank_tier    CHECK (rank_tier IN (
        'Beginner','Bronze','Silver','Gold','Platinum',
        'Emerald','Diamond','Master','Grandmaster','Ultimate'
    ))
);

-- ============================================================
-- Indexes (query optimisation)
-- ============================================================
CREATE INDEX idx_players_rank_tier    ON players(rank_tier);
CREATE INDEX idx_players_pp           ON players(pp DESC);
CREATE INDEX idx_scores_userid        ON scores(userid);
CREATE INDEX idx_scores_beatmap_id    ON scores(beatmap_id);
CREATE INDEX idx_scores_pp            ON scores(pp DESC);
CREATE INDEX idx_scores_mods          ON scores(mods);
CREATE INDEX idx_beatmaps_star        ON beatmaps(star_rating DESC);

-- ============================================================
-- Helper function: assign rank tier from pp value
-- osu! doesn't have formal rank tiers like LoL — we bin by PP
-- Bins chosen to roughly mirror the global_rank_percent spread
-- ============================================================
CREATE OR REPLACE FUNCTION assign_rank_tier(player_pp NUMERIC)
RETURNS VARCHAR AS $$
BEGIN
    RETURN CASE
        WHEN player_pp IS NULL OR player_pp < 1000  THEN 'Beginner'
        WHEN player_pp < 2000                       THEN 'Bronze'
        WHEN player_pp < 4000                       THEN 'Silver'
        WHEN player_pp < 7000                       THEN 'Gold'
        WHEN player_pp < 10000                      THEN 'Platinum'
        WHEN player_pp < 14000                      THEN 'Emerald'
        WHEN player_pp < 18000                      THEN 'Diamond'
        WHEN player_pp < 22000                      THEN 'Master'
        WHEN player_pp < 27000                      THEN 'Grandmaster'
        ELSE                                             'Ultimate'
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
