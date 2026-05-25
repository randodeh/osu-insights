"""osu! API v2 client, OAuth2 client credentials flow."""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

OSU_CLIENT_ID     = os.getenv("OSU_CLIENT_ID")
OSU_CLIENT_SECRET = os.getenv("OSU_CLIENT_SECRET")
BASE_URL          = "https://osu.ppy.sh/api/v2"
TOKEN_URL         = "https://osu.ppy.sh/oauth/token"

_token       = None
_tokenExpiry = 0


def _getToken():
    global _token, _tokenExpiry
    if _token and time.time() < _tokenExpiry - 60:
        return _token

    resp = requests.post(TOKEN_URL, json={
        "client_id":     OSU_CLIENT_ID,
        "client_secret": OSU_CLIENT_SECRET,
        "grant_type":    "client_credentials",
        "scope":         "public"
    })
    resp.raise_for_status()
    data         = resp.json()
    _token       = data["access_token"]
    _tokenExpiry = time.time() + data["expires_in"]
    return _token


def _get(endpoint, params=None):
    headers = {"Authorization": f"Bearer {_getToken()}"}
    resp    = requests.get(f"{BASE_URL}{endpoint}", headers=headers, params=params)
    if resp.status_code == 429:
        retryAfter = int(resp.headers.get("Retry-After", 10))
        print(f"  Rate limited — sleeping {retryAfter}s")
        time.sleep(retryAfter)
        return _get(endpoint, params)
    resp.raise_for_status()
    return resp.json()


def getUserById(userId):
    """Fetch a single user by their osu! user ID."""
    return _get(f"/users/{userId}/osu")


def getUserByName(username):
    """Fetch a single user by their osu! username."""
    return _get(f"/users/{username}/osu", params={"key": "username"})


def getUserScores(userId, scoreType="best", limit=100):
    """
    Fetch a user's scores.
    scoreType: 'best' (top plays), 'recent', 'firsts'
    """
    return _get(f"/users/{userId}/scores/{scoreType}", params={
        "mode":   "osu",
        "limit":  limit,
        "include_beatmapset": 1
    })


def getBeatmap(beatmapId):
    """Fetch beatmap metadata."""
    return _get(f"/beatmaps/{beatmapId}")


def getRanking(mode="osu", rankingType="performance", page=1):
    """
    Fetch the global performance ranking page.
    Each page returns 50 players.
    """
    return _get(f"/rankings/{mode}/{rankingType}", params={"page": page})


def extractPlayerData(userData):
    """Parse raw API user object into the dict we store in DB."""
    stats = userData.get("statistics") or {}
    return {
        "userId":         userData["id"],
        "username":       userData["username"],
        "globalRank":     stats.get("global_rank"),
        "countryRank":    stats.get("country_rank"),
        "pp":             stats.get("pp"),
        "accuracy":       (stats.get("hit_accuracy") or 0) / 100.0,
        "playCount":      stats.get("play_count"),
        "playTime":       stats.get("play_time"),
        "totalScore":     stats.get("total_score"),
        "joinDate":       userData.get("join_date", "")[:10] if userData.get("join_date") else None,
        "countryCode":    userData.get("country_code"),
        "profileIconId":  int(userData.get("avatar_url", "").split("/")[-1].split("?")[0].split(".")[0])
                          if userData.get("avatar_url") and
                             userData["avatar_url"].split("/")[-1].split("?")[0].split(".")[0].isdigit()
                          else None,
    }


def extractBeatmapData(bmData, bmsData=None):
    """Parse raw API beatmap object into the dict we store in DB."""
    bms = bmsData or bmData.get("beatmapset") or {}
    return {
        "beatmapId":    bmData["id"],
        "beatmapsetId": bmData.get("beatmapset_id"),
        "title":        bms.get("title") or bmData.get("version", ""),
        "artist":       bms.get("artist", ""),
        "version":      bmData.get("version", ""),
        "creator":      bms.get("creator", ""),
        "starRating":   bmData.get("difficulty_rating"),
        "lengthSeconds": bmData.get("total_length"),
        "bpm":          bmData.get("bpm"),
        "approachRate": bmData.get("ar"),
        "overallDiff":  bmData.get("accuracy"),
        "circleSize":   bmData.get("cs"),
        "hpDrain":      bmData.get("drain"),
        "maxCombo":     bmData.get("max_combo"),
        "rankedStatus": bmData.get("status"),
    }


def extractScoreData(scoreData, userId):
    """Parse raw API score object into the dict we store in DB."""
    stats = scoreData.get("statistics") or {}
    mods  = "+".join(scoreData.get("mods", [])) or "NM"
    return {
        "scoreId":    scoreData.get("id") or scoreData.get("best_id"),
        "userId":     userId,
        "beatmapId":  scoreData["beatmap"]["id"] if scoreData.get("beatmap") else None,
        "score":      scoreData.get("score"),
        "accuracy":   scoreData.get("accuracy"),
        "maxCombo":   scoreData.get("max_combo"),
        "count300":   stats.get("count_300"),
        "count100":   stats.get("count_100"),
        "count50":    stats.get("count_50"),
        "countMiss":  stats.get("count_miss"),
        "pp":         scoreData.get("pp"),
        "mods":       mods,
        "rankGrade":  scoreData.get("rank"),
        "passed":     scoreData.get("passed", True),
        "playDate":   scoreData.get("created_at"),
    }
