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

  function markState(idkey) {
    var record = markRecord(idkey);
    return record && typeof record.state === "string" ? record.state : "";
  }

  // Every mark write goes through here so listeners (the queue's "hide
  // ignored" filter, and anything added later) never have to re-derive the
  // storage rules or poll localStorage.
  function announceMarkChange(idkey) {
    document.dispatchEvent(new CustomEvent("radar:mark-changed", {
      detail: { identity_key: idkey, state: markState(idkey) }
    }));
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

  function node(tag, className, value) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (value != null) el.textContent = String(value);
    return el;
  }

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

  var MAIL_TRUNCATED_NOTE = "\n\n（完整内容见本页文本框，可直接复制粘贴。）";

  function mailtoBody(parts) {

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

    var full = [parts.head].concat(parts.sections).join("\n\n");
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
    return body.length < full.length ? body + MAIL_TRUNCATED_NOTE : body;
  }

  // A static page cannot send mail. `mailto:` only works when the machine has
  // a mail client registered for the scheme, which a webmail-only setup does
  // not — and the page has no way to detect that, so claiming "mail opened"
  // was a lie (reported 2026-09-22: the button appeared to only copy). The
  // button now opens a panel that always works: the full text sits in a
  // selected textarea, a copy is attempted, and the `mailto:` link is offered
  // as a real link the reader can choose to click.
  function buildMailPanel(card, idkey) {
    var parts = mailSections(card, idkey);
    var full = [parts.head].concat(parts.sections).join("\n\n");

    var panel = node("div", "rui-mail-wrap");
    var status = node("div", "rui-mail-status",
      "收件人 " + mailAddress() + " · 正在复制正文…");
    panel.appendChild(status);

    var area = document.createElement("textarea");
    area.className = "rui-mail-ta";
    area.readOnly = true;
    area.value = "收件人：" + mailAddress() + "\n主题：" + parts.subject +
      "\n\n" + full;
    panel.appendChild(area);

    var actions = node("div", "rui-mail-actions");
    var copy = node("button", "rui-btn rui-mail-copy", "复制全文");
    copy.type = "button";
    actions.appendChild(copy);
    var open = node("a", "rui-btn rui-secondary rui-mail-open", "用邮件客户端打开");
    open.href = mailtoUrl(parts.subject, mailtoBody(parts));
    actions.appendChild(open);
    var close = node("button", "rui-btn rui-secondary rui-mail-close", "收起");
    close.type = "button";
    actions.appendChild(close);
    panel.appendChild(actions);

    panel.appendChild(node("div", "rui-mail-note",
      "点“用邮件客户端打开”没有反应，说明本机没有注册默认邮件客户端；" +
      "直接复制上面的正文，粘贴到网页版邮箱即可。"));

    function copyAll() {
      if (!navigator.clipboard || !navigator.clipboard.writeText) {
        status.textContent = "收件人 " + mailAddress() +
          " · 浏览器不允许自动复制，请在文本框里全选复制。";
        return;
      }
      navigator.clipboard.writeText(area.value).then(function () {
        status.textContent = "收件人 " + mailAddress() + " · ✓ 正文已复制，可直接粘贴";
      }, function () {
        status.textContent = "收件人 " + mailAddress() +
          " · 自动复制被拒绝，请在文本框里全选复制。";
      });
    }
    copy.addEventListener("click", copyAll);
    close.addEventListener("click", function () {
      panel.remove();
    });
    copyAll();
    return panel;
  }

  function offerCardByMail(card, idkey) {
    var existing = card.querySelector(".rui-mail-wrap");
    if (existing) {
      existing.remove();
      return;
    }
    var panel = buildMailPanel(card, idkey);
    var tools = card.querySelector(".rui-card-tools");
    (tools || card).appendChild(panel);
    var area = panel.querySelector(".rui-mail-ta");
    if (area) area.select();
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
        announceMarkChange(idk);
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
        announceMarkChange(idk);
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
        announceMarkChange(idk);
      });
    }

    // D5 mail — hand this card to the owner's mail client (ADR-0016
    // addendum 2026-09-22, replaces the lit-system promote queue).
    var mBtn = card.querySelector(".rui-mail-btn");
    if (mBtn) {
      mBtn.addEventListener("click", function () {
        offerCardByMail(card, idk);
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
  // Years of every 忽略 mark, so the queue can load just those shards for
  // its "only ignored" view instead of the whole priority.
  function ignoredYears() {
    var years = [];
    var total = 0;
    try { total = localStorage.length; } catch (error) { total = 0; }
    for (var index = 0; index < total; index += 1) {
      var key = localStorage.key(index);
      if (!key || key.indexOf("radar:mark:") !== 0) continue;
      var record = lsGet(key, null);
      if (!record || record.state !== "ignore") continue;
      var year = typeof record.date === "string" ? record.date.slice(0, 4) : "";
      if (!/^\d{4}$/.test(year)) year = "";
      if (years.indexOf(year) === -1) years.push(year);
    }
    return years;
  }

  window.RadarUI = {
    hydrate: hydrateCards,
    markState: markState,
    ignoredYears: ignoredYears
  };

  hydrateCards(document);

  // ---- library.html: hand the marks over to the repository (ADR-0032) ----
  //
  // The site is a static artifact and holds no credential, so the browser
  // cannot write to the repository. It packages the marks instead and opens a
  // pre-filled issue that the reader submits with their own GitHub session;
  // .github/workflows/marks-sync.yml validates the body and commits it. The
  // payload is always shown in a textarea as well, because a long one does
  // not fit in a URL and because nothing here should depend on a step the
  // page cannot verify.
  var SYNC_URL_BUDGET = 6000;

  function allMarkRecords() {
    var out = {};
    var total = 0;
    try { total = localStorage.length; } catch (error) { total = 0; }
    for (var index = 0; index < total; index += 1) {
      var key = localStorage.key(index);
      if (!key || key.indexOf("radar:mark:") !== 0) continue;
      var record = lsGet(key, null);
      if (!record || typeof record !== "object") continue;
      var state = typeof record.state === "string" ? record.state : "";
      var note = typeof record.note === "string" ? record.note : "";
      if (!state && !note) continue;
      out[key.slice("radar:mark:".length)] = {
        state: state,
        at: typeof record.at === "string" ? record.at : "",
        note: note,
        title: typeof record.title === "string" ? record.title : "",
        date: typeof record.date === "string" ? record.date : "",
        direction: typeof record.direction === "string" ? record.direction : "",
        priority: typeof record.priority === "string" ? record.priority : ""
      };
    }
    return out;
  }

  function deviceId() {
    var stored = lsGet("radar:device", null);
    if (typeof stored === "string" && /^[a-z0-9][a-z0-9_-]{2,31}$/.test(stored)) {
      return stored;
    }
    var random = "";
    for (var index = 0; index < 8; index += 1) {
      random += Math.floor(Math.random() * 16).toString(16);
    }
    var fresh = "dev-" + random;
    lsSet("radar:device", fresh);
    return fresh;
  }

  function repoSlug() {
    // Published at <owner>.github.io/<repo>/; a local preview has no target.
    var match = /^([a-z0-9-]+)\.github\.io$/i.exec(window.location.hostname);
    var segment = window.location.pathname.split("/").filter(Boolean)[0];
    return match && segment ? match[1] + "/" + segment : "";
  }

  function syncBody(payload) {
    return "```json\n" + JSON.stringify(payload, null, 1) + "\n```\n";
  }

  var syncBtn = document.getElementById("rui-sync-marks");
  if (syncBtn) {
    syncBtn.addEventListener("click", function () {
      var host = document.getElementById("rui-sync-panel");
      if (!host) return;
      if (host.firstChild) {
        host.replaceChildren();
        return;
      }
      var device = deviceId();
      var marks = allMarkRecords();
      var count = Object.keys(marks).length;
      var payload = {
        schema_version: 1,
        device: device,
        updated_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
        marks: marks
      };
      var body = syncBody(payload);

      var status = node("div", "rui-mail-status",
        "设备 " + device + " · " + count + " 条标记 · 正在复制…");
      host.appendChild(status);

      var area = document.createElement("textarea");
      area.className = "rui-mail-ta";
      area.readOnly = true;
      area.value = body;
      host.appendChild(area);

      var actions = node("div", "rui-mail-actions");
      var copy = node("button", "rui-btn", "复制内容");
      copy.type = "button";
      actions.appendChild(copy);

      var slug = repoSlug();
      var title = "marks sync " + device;
      var base = slug ? "https://github.com/" + slug + "/issues/new" : "";
      var withBody = base + "?labels=marks-sync&title=" +
        encodeURIComponent(title) + "&body=" + encodeURIComponent(body);
      var withoutBody = base + "?labels=marks-sync&title=" +
        encodeURIComponent(title) + "&body=" +
        encodeURIComponent("把上一步复制的内容粘贴到这里，然后提交。\n\n");
      var fits = withBody.length <= SYNC_URL_BUDGET;

      if (base) {
        var open = node("a", "rui-btn rui-secondary",
          fits ? "打开 GitHub 提交页（已预填）" : "打开 GitHub 提交页（需粘贴）");
        open.href = fits ? withBody : withoutBody;
        open.target = "_blank";
        open.rel = "noopener noreferrer";
        actions.appendChild(open);
      }
      var close = node("button", "rui-btn rui-secondary", "收起");
      close.type = "button";
      actions.appendChild(close);
      host.appendChild(actions);

      host.appendChild(node("div", "rui-mail-note", base
        ? "提交后由 marks-sync 工作流校验并写入 data/marks/，" +
          "只接受仓库所有者本人开的 issue；完成后它会回帖并关闭该 issue。"
        : "本地预览没有对应的仓库地址；复制内容后到已发布的站点或直接在 GitHub 上新建 issue 提交。"));

      function copyAll() {
        if (!navigator.clipboard || !navigator.clipboard.writeText) {
          status.textContent = "设备 " + device + " · " + count +
            " 条标记 · 浏览器不允许自动复制，请在文本框里全选复制。";
          return;
        }
        navigator.clipboard.writeText(area.value).then(function () {
          status.textContent = "设备 " + device + " · " + count +
            " 条标记 · ✓ 已复制" + (fits ? "（提交页也已预填）" : "，请粘贴到提交页");
        }, function () {
          status.textContent = "设备 " + device + " · " + count +
            " 条标记 · 自动复制被拒绝，请在文本框里全选复制。";
        });
      }
      copy.addEventListener("click", copyAll);
      close.addEventListener("click", function () { host.replaceChildren(); });
      copyAll();
      area.select();
    });
  }

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
