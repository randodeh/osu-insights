/* osu!insights — main.js */

(function () {
  /* ── Player cycler ── */
  let cyclerIdx    = 0;
  let cyclerPaused = false;
  let cyclerTimer  = null;

  function showPlayer(p, instant) {
    if (!p) return;
    var avatar = document.getElementById("playerAvatar");
    var url = "https://a.ppy.sh/" + p.userid;
    var tmp = new Image();
    tmp.onload = function () { avatar.src = url; };
    tmp.src = url;
    if (tmp.complete) avatar.src = url;
    document.getElementById("playerName").textContent = p.username;
    document.getElementById("playerPP").textContent   = Number(p.pp).toLocaleString("en-GB", {maximumFractionDigits:0}) + "pp";
    document.getElementById("playerRank").textContent = "#" + Number(p.global_rank).toLocaleString("en-GB") + "  •  " + p.rank_tier;
  }

  function advanceCycler(dir) {
    if (!PLAYERS.length) return;
    cyclerIdx = ((cyclerIdx + dir) + PLAYERS.length) % PLAYERS.length;
    var p = PLAYERS[cyclerIdx];
    showPlayer(p);
    if (document.getElementById("searchResult")) fetchPlayer(p.username);
  }

  function startCycler() {
    clearInterval(cyclerTimer);
    cyclerTimer = setInterval(function () {
      if (!cyclerPaused) advanceCycler(1);
    }, 7000);
  }

  if (PLAYERS.length) {
    startCycler();
    /* preload avatars */
    PLAYERS.forEach(function (p) {
      var img = new Image();
      img.src = "https://a.ppy.sh/" + p.userid;
    });
    /* pre-fetch first 10 players only */
    PLAYERS.slice(0, 10).forEach(function (p, i) {
      setTimeout(function () {
        var key = p.username.toLowerCase();
        if (!playerCache[key]) {
          fetch("/api/player/" + encodeURIComponent(p.username))
            .then(function (r) { return r.json(); })
            .then(function (data) { if (!data.error) playerCache[key] = data; })
            .catch(function () {});
        }
      }, i * 800);
    });
  }

  document.getElementById("btnNext").addEventListener("click", function () { advanceCycler(1); });
  document.getElementById("btnPrev").addEventListener("click", function () { advanceCycler(-1); });
  document.getElementById("pauseImg").src = PLAY_IMG;

  document.getElementById("btnPause").addEventListener("click", function () {
    cyclerPaused = !cyclerPaused;
    document.getElementById("pauseImg").src = cyclerPaused ? PAUSE_IMG : PLAY_IMG;
  });

  /* click player card → jump to search */
  document.getElementById("playerCard").addEventListener("click", function () {
    const name = document.getElementById("playerName").textContent;
    if (name && name !== "—") loadPlayer(name);
  });

  /* ── Overlay menu ── */
  const overlay = document.getElementById("playerOverlay");
  document.getElementById("btnMenu").addEventListener("click",  function () { overlay.classList.add("open"); });
  document.getElementById("btnClose").addEventListener("click", function () { overlay.classList.remove("open"); });

  document.querySelectorAll(".overlay-item").forEach(function (item) {
    item.addEventListener("click", function () {
      const name = item.dataset.username;
      overlay.classList.remove("open");
      loadPlayer(name);
    });
  });

  /* ── Player cache ── */
  var playerCache = {};

  /* ── Player search / AJAX ── */
  function loadPlayer(username) {
    if (!username) return;

    /* navigate to search page with username pre-filled */
    if (window.location.pathname !== "/") {
      window.location.href = "/?q=" + encodeURIComponent(username);
      return;
    }

    const input = document.getElementById("searchInput");
    if (input) input.value = username;
    fetchPlayer(username);
  }

  function fetchPlayer(username) {
    const result = document.getElementById("searchResult");
    if (!result) return;
    var key = username.toLowerCase();
    if (playerCache[key]) {
      renderPlayerResult(playerCache[key], result);
      var cp = playerCache[key].player;
      showPlayer({ userid: cp.userid, username: cp.username, pp: cp.pp, global_rank: cp.global_rank, rank_tier: cp.rank_tier }, true);
      return;
    }
    fetch("/api/player/" + encodeURIComponent(username))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) {
          result.innerHTML = '<div class="placeholder"><div class="placeholder-text">Player not found</div></div>';
          return;
        }
        playerCache[key] = data;
        renderPlayerResult(data, result);
        var p = data.player;
        showPlayer({ userid: p.userid, username: p.username, pp: p.pp, global_rank: p.global_rank, rank_tier: p.rank_tier });
      })
      .catch(function (err) {
        result.innerHTML = '<div class="placeholder"><div class="placeholder-text">Error: ' + err.message + '</div></div>';
      });
  }

  /* ── Delegate inline search inside searchResult ── */
  var searchResult = document.getElementById("searchResult");
  if (searchResult) {
    searchResult.addEventListener("submit", function (e) {
      if (e.target && e.target.id === "inlineSearchForm") {
        e.preventDefault();
        var val = e.target.querySelector("#inlineSearchInput").value.trim();
        if (val) {
          cyclerPaused = true;
          document.getElementById("pauseImg").src = PAUSE_IMG;
          fetchPlayer(val);
        }
      }
    });
  }

  /* ── Search form ── */
  const searchForm = document.getElementById("searchForm");
  if (searchForm) {
    searchForm.addEventListener("submit", function (e) {
      e.preventDefault();
      const val = document.getElementById("searchInput").value.trim();
      if (val) {
        cyclerPaused = true;
        document.getElementById("pauseImg").src = PAUSE_IMG;
        fetchPlayer(val);
      }
    });

    /* auto-load from ?q= param, otherwise load mrekk by default */
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    if (q) {
      document.getElementById("searchInput").value = q;
      fetchPlayer(q);
    } else {
      fetchPlayer("mrekk");
    }
  }

  /* ── Render player result ── */
  function badgeClass(status) {
    if (status === "Above Average") return "badge-above";
    if (status === "Needs Work")    return "badge-below";
    return "badge-average";
  }

  function renderPlayerResult(data, container) {
    const p  = data.player;
    const c  = data.coach;
    const ct = data.compareTier;

    let html = '<div class="profile-header" style="position:relative">'
      + '<div class="player-bg-glow"><img src="https://a.ppy.sh/' + p.userid + '" alt=""></div>'
      + '<img src="https://a.ppy.sh/' + p.userid + '" class="profile-avatar" alt="' + p.username + '">'
      + '<div style="position:relative;z-index:2"><div class="profile-username">' + p.username + '</div>'
      + '<div class="profile-sub">' + p.country_code + '  •  Rank #' + Number(p.global_rank).toLocaleString("en-GB") + '  •  ' + p.rank_tier + '</div>'
      + '</div>'
      + '<form id="inlineSearchForm" style="margin-left:auto;display:flex;gap:8px;position:relative;z-index:2">'
      + '<div class="search-wrapper"><img class="search-icon" src="/static/img/search.png" alt=""><input id="inlineSearchInput" class="search-input" type="text" placeholder="Search player…" autocomplete="off" style="width:220px"></div>'
      + '</form>'
      + '</div>';

    /* stat cards */
    html += '<div class="grid-4" style="margin-bottom:16px">'
      + statCard("PP", Number(p.pp).toLocaleString("en-GB", {maximumFractionDigits:0}), c ? (c.pp_vs_avg >= 0 ? "+" : "") + Number(c.pp_vs_avg).toLocaleString("en-GB", {maximumFractionDigits:0}) + "pp vs tier avg" : "", c ? c.pp_status : "")
      + statCard("Accuracy", parseFloat(p.accuracy_pct || 0).toFixed(2) + "%", c ? (c.acc_vs_avg >= 0 ? "+" : "") + c.acc_vs_avg + "% vs tier avg" : "", c ? c.acc_status : "")
      + statCard("Play Count", Number(p.play_count).toLocaleString("en-GB"), "", "")
      + statCard("Rank Tier", p.rank_tier, ct !== p.rank_tier ? "compared to " + ct : "", "")
      + '</div>';

    /* radar + tabs */
    html += '<div class="tabs" id="coachTabs">'
      + '<div class="tab active" data-tab="scores">Top Scores</div>'
      + (c ? '<div class="tab" data-tab="ppfarm">PP Farm</div><div class="tab" data-tab="accuracy">Accuracy Gains</div>' : '')
      + (data.radar ? '<div class="tab" data-tab="radar">Radar Chart</div>' : '')
      + '</div>';

    /* scores panel */
    html += '<div class="tab-panel active" id="panel-scores">';
    if (data.scores && data.scores.length) {
      html += '<table class="data-table"><thead><tr>'
        + '<th>Map</th><th>PP</th><th>Acc</th><th>Stars</th><th>Mods</th><th>Grade</th><th></th>'
        + '</tr></thead><tbody>';
      data.scores.forEach(function (s) {
        html += '<tr><td><b>' + s.title + '</b><br><span style="color:rgba(255,255,255,0.7);font-size:0.78rem">' + s.artist + ' — ' + s.version + '</span></td>'
          + '<td><b>' + Number(s.pp).toLocaleString("en-GB", {maximumFractionDigits:0}) + 'pp</b></td>'
          + '<td>' + s.accuracy_pct + '%</td>'
          + '<td>' + s.star_rating + '★</td>'
          + '<td>' + (s.mods || 'NM') + '</td>'
          + '<td>' + s.rank_grade + '</td>'
          + '<td><a href="https://osu.ppy.sh/b/' + s.beatmap_id + '" target="_blank" class="btn-download">Download</a></td></tr>';
      });
      html += '</tbody></table>';
    } else {
      html += '<div class="placeholder"><div class="placeholder-text">No scores found</div></div>';
    }
    html += '</div>';

    /* pp farm panel */
    if (c) {
      html += '<div class="tab-panel" id="panel-ppfarm">';
      if (data.ppRecs && data.ppRecs.length) {
        html += '<p style="margin-bottom:12px;color:#fff;font-size:0.9rem">Maps you haven\'t played that others at your tier are farming. Tier Plays = how many players at your tier have a score on it.</p>';
        html += '<table class="data-table"><thead><tr>'
          + '<th>Map</th><th>Stars</th><th>Avg PP at Tier</th><th>Times Scored</th><th></th>'
          + '</tr></thead><tbody>';
        data.ppRecs.forEach(function (r) {
          html += '<tr><td><b>' + r.title + '</b><br><span style="color:rgba(255,255,255,0.7);font-size:0.78rem">' + r.artist + ' — ' + r.version + '</span></td>'
            + '<td>' + r.star_rating + '★</td>'
            + '<td><b>' + Number(r.avg_pp_at_tier).toLocaleString("en-GB", {maximumFractionDigits:0}) + 'pp</b></td>'
            + '<td>' + r.times_scored + '</td>'
            + '<td><a href="https://osu.ppy.sh/b/' + r.beatmap_id + '" target="_blank" class="btn-download">Download</a></td></tr>';
        });
        html += '</tbody></table>';
      } else {
        html += '<div class="placeholder"><div class="placeholder-text">No recommendations available</div></div>';
      }
      html += '</div>';

      /* accuracy panel */
      html += '<div class="tab-panel" id="panel-accuracy">';
      if (data.accRecs && data.accRecs.length) {
        html += '<p style="margin-bottom:12px;color:#fff;font-size:0.9rem">Maps you\'ve played with room to improve accuracy:</p>';
        html += '<table class="data-table"><thead><tr>'
          + '<th>Map</th><th>Your PP</th><th>Your Acc</th><th>Tier Avg PP</th><th>Potential Gain</th><th></th>'
          + '</tr></thead><tbody>';
        data.accRecs.forEach(function (r) {
          html += '<tr><td><b>' + r.title + '</b><br><span style="color:rgba(255,255,255,0.7);font-size:0.78rem">' + r.artist + ' — ' + r.version + '</span></td>'
            + '<td>' + r.current_pp + 'pp</td>'
            + '<td>' + r.current_acc_pct + '%</td>'
            + '<td>' + r.avg_pp_at_tier + 'pp</td>'
            + '<td style="color:#56d364">+' + r.potential_pp_gain + 'pp</td>'
            + '<td><a href="https://osu.ppy.sh/b/' + r.beatmap_id + '" target="_blank" class="btn-download">Download</a></td></tr>';
        });
        html += '</tbody></table>';
      } else {
        html += '<div class="placeholder"><div class="placeholder-text">No improvements found</div></div>';
      }
      html += '</div>';
    }

    /* radar panel */
    if (c) {
      html += '<div class="tab-panel" id="panel-radar">'
        + '<div style="text-align:center" id="radarContainer"><div class="loading"><div class="spinner"></div>Loading…</div></div>'
        + '</div>';
    }

    container.innerHTML = html;

    /* tab switching */
    var radarLoaded = false;
    container.querySelectorAll(".tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        container.querySelectorAll(".tab").forEach(function (t) { t.classList.remove("active"); });
        container.querySelectorAll(".tab-panel").forEach(function (p) { p.classList.remove("active"); });
        tab.classList.add("active");
        const panel = container.querySelector("#panel-" + tab.dataset.tab);
        if (panel) panel.classList.add("active");
        if (tab.dataset.tab === "radar" && !radarLoaded) {
          radarLoaded = true;
          fetch("/api/radar/" + encodeURIComponent(data.player.username))
            .then(function (r) { return r.json(); })
            .then(function (d) {
              var rc = container.querySelector("#radarContainer");
              if (rc && d.radar) rc.innerHTML = '<img src="data:image/png;base64,' + d.radar + '" style="max-width:340px;border-radius:8px">';
            });
        }
      });
    });
  }

  function statCard(label, value, sub, status) {
    let badge = "";
    if (status) badge = '<span class="badge ' + badgeClass(status) + '" style="margin-left:8px">' + status + '</span>';
    return '<div class="card"><div class="card-label">' + label + '</div>'
      + '<div class="card-value">' + value + badge + '</div>'
      + (sub ? '<div class="card-sub">' + sub + '</div>' : '')
      + '</div>';
  }

  /* ── Admin actions ── */
  const ingestBtn = document.getElementById("ingestBtn");
  if (ingestBtn) {
    ingestBtn.addEventListener("click", function () {
      const username = document.getElementById("ingestInput").value.trim();
      if (!username) return;
      const log = document.getElementById("ingestLog");
      log.textContent = "Ingesting " + username + "…";
      log.style.display = "block";
      ingestBtn.disabled = true;

      fetch("/api/ingest-player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username })
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          log.textContent = d.ok ? "Done!\n" + (d.output || "") : "Error: " + (d.error || "unknown");
          log.style.display = "block";
          ingestBtn.disabled = false;
        })
        .catch(function () { log.textContent = "Network error"; ingestBtn.disabled = false; });
    });
  }

  const refreshBtn = document.getElementById("refreshTiersBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      refreshBtn.disabled = true;
      fetch("/api/refresh-tiers", { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function () { refreshBtn.disabled = false; alert("Tiers refreshed!"); })
        .catch(function () { refreshBtn.disabled = false; });
    });
  }

  const deleteBtn = document.getElementById("deleteBtn");
  if (deleteBtn) {
    deleteBtn.addEventListener("click", function () {
      const username = document.getElementById("deleteInput").value.trim();
      if (!username || !confirm("Delete " + username + "?")) return;
      fetch("/api/delete-player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username })
      })
        .then(function (r) { return r.json(); })
        .then(function (d) { alert(d.ok ? "Deleted " + username : "Error: " + d.error); })
        .catch(function () { alert("Network error"); });
    });
  }

  window.showPlayerCard = showPlayer;
  window.pauseCycler = function() {
    cyclerPaused = true;
    document.getElementById("pauseImg").src = PAUSE_IMG;
  };

})();
