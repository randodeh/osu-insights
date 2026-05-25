"""osu!insights, Flask application"""

import sys, os, io, base64
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etl"))

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from db import (
    getPlayerByName, getPlayerCoachWithFallback, getPlayerTopScores,
    getPlayerStarRange, getPPFarmRecommendations, getAccuracyRecommendations,
    getRankTierAverages, getLeaderboard, getBeatmapStats,
    getTierDistribution, getModStats, getDbStats, getTopPlayersForCycle,
    execute, query, queryOne
)

app = Flask(__name__)
app.secret_key = "osuinsights-admin-secret-2024"
ADMIN_PASSWORD = "admin"

TIER_ORDER  = ["Beginner","Bronze","Silver","Gold","Platinum","Emerald","Diamond","Master","Grandmaster","Ultimate"]
TIER_COLORS = ["#6b7280","#b45309","#9ca3af","#d97706","#0ea5e9","#10b981","#6366f1","#8b5cf6","#ec4899","#ff66ab"]


@app.template_filter("format_number")
def formatNumber(value):
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value


def chartToBase64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", transparent=True)
    buf.seek(0)
    data = base64.b64encode(buf.read()).decode()
    plt.close(fig)
    return data


def applyStyle(ax, fig):
    fig.patch.set_facecolor("none")
    ax.set_facecolor("none")
    ax.tick_params(colors="#ffffff")
    ax.xaxis.label.set_color("#ffffff")
    ax.yaxis.label.set_color("#ffffff")
    ax.title.set_color("#ffffff")
    for spine in ax.spines.values():
        spine.set_edgecolor((1,1,1,0.2))
    ax.grid(axis="y", color=(1,1,1,0.15), linewidth=0.5)


@app.route("/improve")
def improve():
    stats   = getDbStats() or {}
    players = getTopPlayersForCycle(100)
    return render_template("improve.html", stats=stats, players=players)


@app.route("/")
def search():
    stats   = getDbStats() or {}
    players = getTopPlayersForCycle(100)
    return render_template("search.html", stats=stats, players=players)


@app.route("/rank-analysis")
def rankAnalysis():
    tierData = getRankTierAverages()
    modData  = getModStats()
    distData = getTierDistribution()
    stats    = getDbStats() or {}
    players  = getTopPlayersForCycle(100)

    charts = {}
    if tierData:
        df = pd.DataFrame(tierData)
        df["_order"] = df["rank_tier"].apply(lambda t: TIER_ORDER.index(t) if t in TIER_ORDER else 99)
        df = df.sort_values("_order").drop(columns="_order")
        colors = [TIER_COLORS[TIER_ORDER.index(t)] if t in TIER_ORDER else "#8b949e" for t in df["rank_tier"]]

        fig, ax = plt.subplots(figsize=(8,4))
        ax.bar(df["rank_tier"], df["avg_pp"], color=colors)
        ax.set_title("Average PP per Rank Tier")
        ax.set_xticklabels(df["rank_tier"], rotation=45, ha="right")
        applyStyle(ax, fig); fig.tight_layout()
        charts["pp"] = chartToBase64(fig)

        fig, ax = plt.subplots(figsize=(8,4))
        ax.bar(df["rank_tier"], df["avg_accuracy_pct"], color=colors)
        ax.set_title("Average Accuracy per Rank Tier")
        ax.set_xticklabels(df["rank_tier"], rotation=45, ha="right")
        applyStyle(ax, fig); fig.tight_layout()
        charts["acc"] = chartToBase64(fig)

    if modData:
        dfMod = pd.DataFrame(modData)
        fig, ax = plt.subplots(figsize=(8,4))
        ax.bar(dfMod["mods"], dfMod["total_scores"], color="#ff66ab", alpha=0.8)
        ax.set_title("Score Count by Mod")
        ax.set_xticklabels(dfMod["mods"], rotation=45, ha="right")
        applyStyle(ax, fig); fig.tight_layout()
        charts["mods"] = chartToBase64(fig)

    return render_template("rank_analysis.html", tierData=tierData, modData=modData,
                           charts=charts, stats=stats, players=players)


@app.route("/beatmaps")
def beatmaps():
    data    = getBeatmapStats(limit=30)
    stats   = getDbStats() or {}
    players = getTopPlayersForCycle(100)
    chart   = None
    if data:
        df = pd.DataFrame(data)
        fig, ax = plt.subplots(figsize=(10,5))
        sc = ax.scatter(df["star_rating"], df["avg_pp"], c=df["total_scores"],
                        cmap="plasma", s=60, alpha=0.8, edgecolors="#0d1117", linewidths=0.5)
        cb = plt.colorbar(sc, ax=ax)
        cb.set_label("Total Scores", color="#8b949e")
        cb.ax.yaxis.set_tick_params(color="#8b949e")
        plt.setp(plt.getp(cb.ax.axes, "yticklabels"), color="#8b949e")
        ax.set_xlabel("Star Rating"); ax.set_ylabel("Avg PP")
        ax.set_title("Star Rating vs Average PP")
        applyStyle(ax, fig); fig.tight_layout()
        chart = chartToBase64(fig)
    return render_template("beatmaps.html", beatmaps=data, chart=chart,
                           stats=stats, players=players)


@app.route("/admin-login", methods=["GET", "POST"])
def adminLogin():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "Incorrect password"
    stats   = getDbStats() or {}
    players = getTopPlayersForCycle(100)
    return render_template("admin_login.html", error=error, stats=stats, players=players)


@app.route("/admin-logout")
def adminLogout():
    session.pop("admin", None)
    return redirect(url_for("search"))


@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect(url_for("adminLogin"))
    stats    = getDbStats() or {}
    players  = getTopPlayersForCycle(100)
    tierData = query("SELECT rank_tier, avg_pp, ROUND(avg_accuracy*100,2) AS avg_acc, player_count FROM rank_tier_averages ORDER BY avg_pp")
    return render_template("admin.html", stats=stats, players=players, tierData=tierData)


@app.route("/api/player/<username>")
def apiPlayer(username):
    player = getPlayerByName(username)
    if not player:
        return jsonify({"error": "Player not found"}), 404
    coach  = getPlayerCoachWithFallback(username)
    scores = getPlayerTopScores(player["userid"], limit=10)
    minStar, maxStar = getPlayerStarRange(player["userid"])
    compareTier = coach.get("compare_tier") or player.get("rank_tier", "Platinum") if coach else "Platinum"
    ppRecs  = getPPFarmRecommendations(player["userid"], compareTier, minStar, maxStar + 0.5)
    accRecs = getAccuracyRecommendations(player["userid"], compareTier)

    return jsonify({
        "player":      dict(player),
        "coach":       dict(coach) if coach else None,
        "scores":      [dict(s) for s in scores],
        "ppRecs":      [dict(r) for r in ppRecs],
        "accRecs":     [dict(r) for r in accRecs],
        "radar":       None,
        "compareTier": compareTier,
        "hasScores":   len(scores) > 0,
    })


@app.route("/api/radar/<username>")
def apiRadar(username):
    import numpy as np
    coach = getPlayerCoachWithFallback(username)
    if not coach:
        return jsonify({"error": "No data"}), 404
    labels     = ["PP", "Accuracy", "Play Count"]
    tierAvgs   = [float(coach.get("tier_avg_pp") or 1), float(coach.get("tier_avg_acc_pct") or 1), float(coach.get("tier_avg_play_count") or 1)]
    playerVals = [float(coach.get("player_pp") or 0), float(coach.get("player_acc_pct") or 0), float(coach.get("play_count") or 0)]
    if not any(t > 0 for t in tierAvgs):
        return jsonify({"error": "No data"}), 404
    norm   = [p/t if t else 0 for p,t in zip(playerVals, tierAvgs)]
    N      = len(labels)
    angles = [n/float(N)*2*np.pi for n in range(N)] + [0]
    pn = norm + [norm[0]]
    tn = [1.0]*N + [1.0]
    fig, ax = plt.subplots(figsize=(4,4), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor("#1a0a1e")
    ax.set_facecolor("#1a0a1e")
    ax.plot(angles, tn, color="#e3b341", linewidth=1.5, linestyle="--", alpha=0.6)
    ax.fill(angles, tn, color="#e3b341", alpha=0.05)
    ax.plot(angles, pn, color="#ff66ab", linewidth=2)
    ax.fill(angles, pn, color="#ff66ab", alpha=0.15)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, color="#8b949e", size=9)
    ax.set_yticklabels([])
    ax.grid(color="#30363d")
    ax.spines["polar"].set_color("#30363d")
    return jsonify({"radar": chartToBase64(fig)})


@app.route("/api/ingest-player", methods=["POST"])
def apiIngestPlayer():
    username = request.json.get("username", "")
    if not username:
        return jsonify({"error": "No username"}), 400
    import subprocess
    result = subprocess.run(
        [sys.executable, "etl/ingest_players.py", "--user", username, "--scores-only"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0:
        return jsonify({"ok": True, "output": result.stdout[-500:]})
    return jsonify({"error": result.stderr[-500:]}), 500


@app.route("/api/refresh-tiers", methods=["POST"])
def apiRefreshTiers():
    execute("CALL refresh_rank_tier_averages()")
    return jsonify({"ok": True})


@app.route("/api/delete-player", methods=["POST"])
def apiDeletePlayer():
    username = request.json.get("username", "")
    rows = query("SELECT userid FROM players WHERE LOWER(username)=LOWER(%s)", (username,))
    if not rows:
        return jsonify({"error": "Not found"}), 404
    execute("DELETE FROM players WHERE LOWER(username)=LOWER(%s)", (username,))
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
