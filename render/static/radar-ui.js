/* radar-ui.js — ADR-0016 client-side curation affordances (D3, D4, D5).
 *
 * Zero dependencies, vanilla DOM. Loaded with `defer` so the DOM is parsed
 * before this IIFE runs. One bundle serves every page type; each block
 * feature-detects its anchor elements and no-ops when they are absent:
 *
 *   - daily pages:      direction tabs + priority filter (D3) + per-card
 *                       reading marks/notes (D4) + mail button (D5)
 *   - high/medium pages: same per-card controls (cards reused verbatim)
 *   - my-marks.html:    export-all-marks + listing
 *
 * localStorage keys (ADR-0016 §3):
 *   radar:filter:priority   -> ["High","Medium",...]            (D3)
 *   radar:filter:marks      -> ["to-read","read",...,"none"]    (D4)
 *   radar:mark:<idkey>      -> { state, at, note }              (D4)
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
    // The reading list shows exactly what the user marked; the daily-page
    // priority / mark filters must not hide anything there.
    if (document.querySelector("main[data-rui-no-filter]")) {
      document.querySelectorAll(".paper").forEach(function (card) {
        card.dataset.hidden = "0";
      });
      return;
    }
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

  // ---- D5: mail one card to the owner (ADR-0016 addendum 2026-09-22) ----
  //
  // The site is a static GitHub Pages artifact with no backend, so nothing
  // here can actually send mail: the button composes the message and hands
  // it to the browser's registered mail client via a `mailto:` URL. The
  // address is assembled at run time rather than written out as a literal,
  // which keeps it out of the page source for naive address scrapers (the
  // rendered page is public either way).
  var MAIL_LOCAL = "sun1139156053";
  var MAIL_DOMAIN = "163.com";
  // Conservative ceiling for the whole mailto: URL. Windows' shell handler
  // historically truncates above ~2000 characters, and one CJK character
  // costs nine after percent-encoding, so the body is filled section by
  // section until the budget runs out. The untruncated text always goes to
  // the clipboard as well, so nothing is silently lost.
  var MAIL_URL_BUDGET = 1800;

  function mailAddress() {
    return MAIL_LOCAL + "@" + MAIL_DOMAIN;
  }

  function cardText(card, selector) {
    var node = card.querySelector(selector);
    return node ? node.textContent.replace(/\s+/g, " ").trim() : "";
  }

  function cardLink(card) {
    var link = card.querySelector(".doi a");
    return link && link.href ? link.href : "";
  }

  function dayPageUrl(card) {
    var date = card.dataset.date || "";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !card.id) return "";
    try {
      return new URL(date + ".html#" + encodeURIComponent(card.id),
        window.location.href).href;
    } catch (error) {
      return "";
    }
  }

  function mailSections(card, idkey) {
    var head = [];
    var title = card.dataset.title || cardText(card, ".paper-title");
    head.push("标题：" + title);
    var meta = [
      cardText(card, ".priority"), cardText(card, ".direction-pill"),
      card.dataset.date || ""
    ].filter(Boolean).join(" · ");
    if (meta) head.push("等级/方向/日期：" + meta);
    var authors = cardText(card, ".authors");
    if (authors) head.push("作者：" + authors);
    var venue = cardText(card, ".venue");
    if (venue) head.push("来源：" + venue);
    var link = cardLink(card);
    if (link) head.push("原文：" + link);
    var page = dayPageUrl(card);
    if (page) head.push("雷达卡片：" + page);
    if (idkey) head.push("身份键：" + idkey);

    var sections = [];
    var record = idkey ? markRecord(idkey) : null;
    if (record && record.note) sections.push("我的笔记：" + record.note);
    var relevance = cardText(card, ".relevance");
    if (relevance) sections.push(relevance);
    var summary = cardText(card, ".summary");
    if (summary) sections.push("中文摘要：" + summary);
    var boundary = cardText(card, ".why-not-core");
    if (boundary) sections.push(boundary);
    return { subject: "[Radar] " + title, head: head.join("\n"), sections: sections };
  }

  function mailtoUrl(subject, body) {
    return "mailto:" + mailAddress() + "?subject=" +
      encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
  }

  var MAIL_TRUNCATED_NOTE = "\n\n（其余内容已复制到剪贴板，可直接粘贴。）";

  function sendCardByMail(card, idkey, button) {
    var parts = mailSections(card, idkey);
    var full = [parts.head].concat(parts.sections).join("\n\n");

    // Fill the mailto body up to the budget, head first. The truncation note
    // is appended after the loop, so reserve its encoded length up front or
    // the finished URL overshoots the budget by ~180 characters.
    //
    // A section that does not fit whole is cut down rather than dropped: one
    // Chinese paragraph costs ~1,000 characters once percent-encoded, so
    // dropping it would leave the mail with nothing but the title and links.
    // The reader gets the opening of the relevance note in the mail and the
    // untruncated text from the clipboard.
    var reserve = encodeURIComponent(MAIL_TRUNCATED_NOTE).length;

    function fits(candidate) {
      return mailtoUrl(parts.subject, candidate).length + reserve <= MAIL_URL_BUDGET;
    }

    var body = parts.head;
    for (var index = 0; index < parts.sections.length; index += 1) {
      var section = parts.sections[index];
      if (fits(body + "\n\n" + section)) {
        body = body + "\n\n" + section;
        continue;
      }
      var shortened = section;
      while (shortened.length > 24) {
        shortened = shortened.slice(0, Math.floor(shortened.length * 0.8));
        if (fits(body + "\n\n" + shortened + "…")) {
          body = body + "\n\n" + shortened + "…";
          break;
        }
      }
      break;
    }
    var truncated = body.length < full.length;
    if (truncated) body += MAIL_TRUNCATED_NOTE;

    var anchor = document.createElement("a");
    anchor.href = mailtoUrl(parts.subject, body);
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();

    function flash(message) {
      button.textContent = message;
      button.classList.add("rui-mailed");
      setTimeout(function () {
        button.textContent = "发送到邮箱";
        button.classList.remove("rui-mailed");
      }, 2500);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(full).then(function () {
        flash(truncated ? "✓ 已打开邮件（全文已复制）" : "✓ 已打开邮件");
      }, function () {
        flash("✓ 已打开邮件");
      });
    } else {
      flash("✓ 已打开邮件");
    }
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

    // D5 mail — hand this card to the owner's mail client (ADR-0016
    // addendum 2026-09-22, replaces the lit-system promote queue).
    var mBtn = card.querySelector(".rui-mail-btn");
    if (mBtn) {
      mBtn.addEventListener("click", function () {
        sendCardByMail(card, idk, mBtn);
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

})();
