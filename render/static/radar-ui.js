/* radar-ui.js — ADR-0016 client-side curation affordances (D3, D4, D5).
 *
 * Zero dependencies, vanilla DOM. Loaded with `defer` so the DOM is parsed
 * before this IIFE runs. One bundle serves every page type; each block
 * feature-detects its anchor elements and no-ops when they are absent:
 *
 *   - daily pages:      direction tabs + priority filter (D3) + per-card
 *                       reading marks/notes (D4) + promote button (D5)
 *   - high/medium pages: same per-card controls (cards reused verbatim)
 *   - my-marks.html:    export-all-marks + listing
 *   - my-promotes.html: queue listing + copy-to-clipboard
 *
 * localStorage keys (ADR-0016 §3):
 *   radar:filter:priority   -> ["High","Medium",...]            (D3)
 *   radar:filter:marks      -> ["to-read","read",...,"none"]    (D4)
 *   radar:mark:<idkey>      -> { state, at, note }              (D4)
 *   radar:promote-queue     -> [{identity_key,title,date,...}]  (D5)
 *
 * All state is single-browser and ephemeral by design (ADR-0016 §2 D4
 * limitations the user accepted). No sync, no write-back.
 */
(function () {
  "use strict";

  function lsGet(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }
  function lsSet(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      /* private mode / quota — degrade silently */
    }
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  var PRIORITY_DEFAULT = ["High", "Medium", "Unscored"];
  var MARKS_DEFAULT = ["to-read", "read", "interesting", "ignore", "none"];

  function priorityFilter() {
    var v = lsGet("radar:filter:priority", PRIORITY_DEFAULT);
    return Array.isArray(v) ? v : PRIORITY_DEFAULT.slice();
  }
  function marksFilter() {
    var v = lsGet("radar:filter:marks", MARKS_DEFAULT);
    return Array.isArray(v) ? v : MARKS_DEFAULT.slice();
  }
  function markRecord(idkey) {
    return lsGet("radar:mark:" + idkey, null);
  }

  // ---- combined visibility: direction AND priority AND mark ----
  var dirFilter = "all";

  function applyFilters() {
    var prios = priorityFilter();
    var marks = marksFilter();
    document.querySelectorAll(".paper").forEach(function (card) {
      var d = card.dataset.direction || "";
      var pr = card.dataset.priority || "Low";
      var idk = card.dataset.identityKey || "";
      var rec = idk ? markRecord(idk) : null;
      var state = rec && rec.state ? rec.state : "none";
      var dirOk = dirFilter === "all" || dirFilter === d;
      var prOk = prios.indexOf(pr) >= 0;
      var mkOk = marks.indexOf(state) >= 0;
      card.dataset.hidden = dirOk && prOk && mkOk ? "0" : "1";
    });
  }

  // ---- direction tabs (ported from the old inline build_pages JS) ----
  var tabs = document.querySelectorAll(".tab");
  tabs.forEach(function (t) {
    t.addEventListener("click", function () {
      tabs.forEach(function (x) {
        x.classList.remove("active");
      });
      t.classList.add("active");
      dirFilter = t.dataset.filter;
      applyFilters();
    });
  });

  // ---- D3: priority checkbox bar ----
  var prioCbs = document.querySelectorAll(".rui-pf-cb");
  function collect(cbs) {
    var sel = [];
    cbs.forEach(function (c) {
      if (c.checked) sel.push(c.value);
    });
    return sel;
  }
  (function syncPrio() {
    var prios = priorityFilter();
    prioCbs.forEach(function (cb) {
      cb.checked = prios.indexOf(cb.value) >= 0;
    });
  })();
  prioCbs.forEach(function (cb) {
    cb.addEventListener("change", function () {
      lsSet("radar:filter:priority", collect(prioCbs));
      applyFilters();
    });
  });

  // ---- D4: marks filter checkbox bar ----
  var markCbs = document.querySelectorAll(".rui-mf-cb");
  (function syncMarks() {
    var marks = marksFilter();
    markCbs.forEach(function (cb) {
      cb.checked = marks.indexOf(cb.value) >= 0;
    });
  })();
  markCbs.forEach(function (cb) {
    cb.addEventListener("change", function () {
      lsSet("radar:filter:marks", collect(markCbs));
      applyFilters();
    });
  });

  function cardMeta(card) {
    return {
      title: card.dataset.title || "",
      date: card.dataset.date || "",
      direction: card.dataset.direction || "",
      priority: card.dataset.priority || ""
    };
  }

  function mergeMeta(record, card) {
    var meta = cardMeta(card);
    Object.keys(meta).forEach(function (key) {
      if (meta[key]) record[key] = meta[key];
    });
    return record;
  }

  // ---- D4 + D5: per-card controls (also hydrates lazy queue cards) ----
  function hydrateCard(card) {
    if (card.dataset.ruiReady === "1") return;
    var idk = card.dataset.identityKey;
    if (!idk) return;
    card.dataset.ruiReady = "1";
    var rec = markRecord(idk);
    if (rec && rec.state) card.dataset.mark = rec.state;

    // D4 mark radios — 4-state to-read / read / interesting / ignore.
    // CHANGE B1: re-clicking the already-selected radio clears the mark
    // entirely. The click handler runs before `change` and reads the prior
    // state from localStorage (the source of truth, not the DOM): if the
    // clicked value already is the stored state, we deselect instead of
    // re-affirming — uncheck the radio, drop the mark, refresh the stripe.
    card.querySelectorAll(".rui-mark-radio").forEach(function (r) {
      if (rec && rec.state === r.value) r.checked = true;
      r.addEventListener("click", function (ev) {
        var prior = markRecord(idk);
        var priorState = prior && prior.state ? prior.state : "none";
        if (priorState !== r.value) return; // not a re-click: let `change` save
        // Re-click on the current mark: clear it. Standard radios don't
        // toggle off, so undo the default and unset explicitly.
        ev.preventDefault();
        r.checked = false;
        if (prior && typeof prior.note === "string" && prior.note !== "") {
          // Preserve a note the user wrote; only the mark state is cleared.
          prior.state = "";
          prior.at = new Date().toISOString();
          lsSet("radar:mark:" + idk, prior);
        } else {
          localStorage.removeItem("radar:mark:" + idk);
        }
        delete card.dataset.mark; // back to the neutral .paper stripe
        applyFilters();
      });
      r.addEventListener("change", function () {
        var cur = mergeMeta(markRecord(idk) ||
          { state: "", at: "", note: "" }, card);
        cur.state = r.value;
        cur.at = new Date().toISOString();
        if (typeof cur.note !== "string") cur.note = "";
        lsSet("radar:mark:" + idk, cur);
        card.dataset.mark = r.value;
        applyFilters();
      });
    });

    // D4 note — toggle textarea, prefilled, auto-save on blur (merge)
    var noteBtn = card.querySelector(".rui-note-btn");
    var noteWrap = card.querySelector(".rui-note-wrap");
    var ta = card.querySelector(".rui-note-ta");
    if (ta) ta.value = rec && rec.note ? rec.note : "";
    if (noteBtn && noteWrap) {
      noteBtn.addEventListener("click", function () {
        noteWrap.style.display =
          noteWrap.style.display === "block" ? "none" : "block";
      });
    }
    if (ta) {
      ta.addEventListener("blur", function () {
        var cur = mergeMeta(markRecord(idk) ||
          { state: "", at: "", note: "" }, card);
        cur.note = ta.value;
        if (!cur.at) cur.at = new Date().toISOString();
        lsSet("radar:mark:" + idk, cur);
      });
    }

    // D5 promote — append to localStorage queue, dedup on identity_key
    var pBtn = card.querySelector(".rui-promote-btn");
    if (pBtn) {
      var queued = (lsGet("radar:promote-queue", []) || []).some(function (q) {
        return q && q.identity_key === idk;
      });
      if (queued) {
        pBtn.textContent = "✓ 已加入";
        pBtn.classList.add("rui-queued");
      }
      pBtn.addEventListener("click", function () {
        var q = lsGet("radar:promote-queue", []);
        if (!Array.isArray(q)) q = [];
        if (q.some(function (x) { return x && x.identity_key === idk; })) return;
        q.push({
          identity_key: idk,
          title: card.dataset.title || "",
          date: card.dataset.date || "",
          direction: card.dataset.direction || "",
          priority: card.dataset.priority || "",
          queued_at: new Date().toISOString()
        });
        lsSet("radar:promote-queue", q);
        pBtn.textContent = "✓ 已加入";
        pBtn.classList.add("rui-queued");
      });
    }
  }

  function hydrateCards(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll(".paper").forEach(hydrateCard);
    applyFilters();
  }

  document.addEventListener("radar:content-ready", function (event) {
    hydrateCards(event.detail && event.detail.root);
  });
  window.RadarUI = { hydrate: hydrateCards };

  hydrateCards(document);

  // ---- my-marks.html: export-all + listing ----
  var exportBtn = document.getElementById("rui-export-marks");
  if (exportBtn) {
    function collectMarks() {
      var out = {};
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (k && k.indexOf("radar:mark:") === 0) {
          try {
            out[k] = JSON.parse(localStorage.getItem(k));
          } catch (e) {
            out[k] = localStorage.getItem(k);
          }
        }
      }
      return out;
    }
    exportBtn.addEventListener("click", function () {
      var data = collectMarks();
      var blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json"
      });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "radar-marks-" + new Date().toISOString().slice(0, 10) + ".json";
      document.body.appendChild(a);
      a.click();
      a.remove();
    });
    var listEl = document.getElementById("rui-marks-list");
    if (listEl) {
      var marks = collectMarks();
      var keys = Object.keys(marks);
      if (!keys.length) {
        listEl.innerHTML = "<p>当前浏览器还没有阅读标记。</p>";
      } else {
        var rows = keys.map(function (k) {
          var r = marks[k] || {};
          var title = esc(r.title || k.replace("radar:mark:", ""));
          var titleCell = /^\d{4}-\d{2}-\d{2}$/.test(r.date || "") ?
            '<a href="' + esc(r.date) + '.html">' + title + "</a>" : title;
          return "<tr><td>" + titleCell + "</td><td>" + esc(r.date || "") +
            "</td><td>" + esc(r.state || "") + "</td><td>" +
            esc(r.note || "") + "</td><td><code>" + esc(r.at || "") +
            "</code></td></tr>";
        });
        listEl.innerHTML =
          '<div class="table-scroll"><table class="rui-table"><thead><tr><th>论文</th>' +
          "<th>日期</th><th>标记</th><th>笔记</th><th>更新时间</th></tr></thead><tbody>" +
          rows.join("") + "</tbody></table></div>";
      }
    }
  }

  // ---- my-promotes.html: queue listing + copy / clear ----
  var copyBtn = document.getElementById("rui-copy-promotes");
  if (copyBtn) {
    var qEl = document.getElementById("rui-promote-list");
    function renderQueue() {
      var q = lsGet("radar:promote-queue", []);
      if (!Array.isArray(q)) q = [];
      if (!qEl) return;
      if (!q.length) {
        qEl.innerHTML = "<p>待导入队列为空。</p>";
        return;
      }
      var rows = q.map(function (x) {
        return "<tr><td>" + esc(x.date) + "</td><td>" + esc(x.priority) +
          "</td><td><code>" + esc(x.identity_key) + "</code></td><td>" +
          esc(x.title) + "</td></tr>";
      });
      qEl.innerHTML =
        '<div class="table-scroll"><table class="rui-table"><thead><tr><th>日期</th><th>等级</th>' +
        "<th>身份键</th><th>标题</th></tr></thead><tbody>" +
        rows.join("") + "</tbody></table></div>";
    }
    renderQueue();
    copyBtn.addEventListener("click", function () {
      var q = lsGet("radar:promote-queue", []);
      navigator.clipboard.writeText(JSON.stringify(q, null, 2)).then(
        function () {
          copyBtn.textContent = "✓ 已复制";
          setTimeout(function () {
            copyBtn.textContent = "复制全部 JSON";
          }, 1500);
        }
      );
    });
    var clearBtn = document.getElementById("rui-clear-promotes");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        if (confirm("确定清空待导入队列？此操作无法撤销。")) {
          lsSet("radar:promote-queue", []);
          renderQueue();
        }
      });
    }
  }
})();
