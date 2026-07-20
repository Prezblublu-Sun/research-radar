/* Lazy High/Medium queue for ADR-0027. Dependency-free DOM construction. */
(function () {
  "use strict";

  var PAGE_SIZE = 25;
  var manifest = null;
  var state = {
    priority: "High", direction: "", year: "", relevance: "",
    records: [], loadedYears: {}, cursor: 0, shown: PAGE_SIZE, loading: false
  };

  var results = document.getElementById("queue-results");
  var status = document.getElementById("queue-status");
  var more = document.getElementById("queue-more");
  var directionSelect = document.getElementById("queue-direction");
  var yearSelect = document.getElementById("queue-year");
  var relevanceSelect = document.getElementById("queue-relevance");
  if (!results || !status || !more) return;

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function addTextRow(parent, label, value) {
    if (!value) return;
    var row = element("div", "");
    row.appendChild(element("b", "", label + "· "));
    row.appendChild(document.createTextNode(value));
    parent.appendChild(row);
  }

  function buildTools(record) {
    var tools = element("div", "rui-card-tools");
    var group = element("span", "rui-mark-group");
    group.appendChild(element("b", "", "标记："));
    [
      ["to-read", "待阅读"], ["read", "已阅读"],
      ["interesting", "有启发"], ["ignore", "忽略"]
    ].forEach(function (item) {
      var label = element("label", "m-" + item[0]);
      var radio = element("input", "rui-mark-radio");
      radio.type = "radio";
      radio.name = "rui-mark-" + record.anchor;
      radio.value = item[0];
      label.appendChild(radio);
      label.appendChild(document.createTextNode(item[1]));
      group.appendChild(label);
    });
    tools.appendChild(group);

    var noteButton = element("button", "rui-note-btn", "笔记");
    noteButton.type = "button";
    tools.appendChild(noteButton);
    var promoteButton = element("button", "rui-promote-btn", "发送到 lit-system");
    promoteButton.type = "button";
    tools.appendChild(promoteButton);

    var noteWrap = element("div", "rui-note-wrap");
    var textarea = element("textarea", "rui-note-ta");
    textarea.placeholder = "私人笔记（失焦自动保存，仅限当前浏览器）";
    noteWrap.appendChild(textarea);
    tools.appendChild(noteWrap);
    return tools;
  }

  function buildCard(record) {
    var card = element("article", "paper");
    card.id = record.anchor;
    card.dataset.identityKey = record.identity_key || "";
    card.dataset.direction = record.direction || "";
    card.dataset.priority = record.priority || "";
    card.dataset.title = record.title || "";
    card.dataset.date = record.date || "";

    card.appendChild(element("h3", "paper-title", record.title || "Untitled"));
    var head = element("div", "paper-head");
    head.appendChild(element("span", "priority priority--" +
      String(record.priority || "low").toLowerCase(), record.priority));
    var direction = element("span", "direction-pill", record.direction_name || record.direction);
    if (/^#[0-9a-f]{6}$/i.test(record.direction_color || "")) {
      direction.style.color = record.direction_color;
      direction.style.backgroundColor = record.direction_color + "20";
    }
    head.appendChild(direction);
    if (record.relevance_level) {
      head.appendChild(element("span", "relevance-level lvl-" +
        record.relevance_level.toLowerCase(), record.relevance_level));
    }
    if (record.read_action) {
      head.appendChild(element("span", "read-action", record.read_action));
    }
    card.appendChild(head);

    var meta = element("div", "meta");
    var authors = (record.authors || []).join(", ");
    [authors, record.venue, record.date, record.source].filter(Boolean)
      .forEach(function (value) { meta.appendChild(element("span", "", value)); });
    card.appendChild(meta);

    if (record.relevance_to_user) {
      var relevance = element("div", "relevance");
      relevance.appendChild(element("b", "", "相关性："));
      relevance.appendChild(document.createTextNode(record.relevance_to_user));
      card.appendChild(relevance);
    }
    if (record.why_not_core) {
      var boundary = element("div", "why-not-core");
      boundary.appendChild(element("b", "", "边界："));
      boundary.appendChild(document.createTextNode(record.why_not_core));
      card.appendChild(boundary);
    }

    var summary = element("div", "summary");
    var zh = record.summary_zh || {};
    addTextRow(summary, "动机", zh.motivation);
    addTextRow(summary, "方法", zh.method);
    addTextRow(summary, "结果", zh.result);
    addTextRow(summary, "验证", zh.validation);
    card.appendChild(summary);

    if ((record.tags || []).length) {
      var tags = element("div", "tags-row");
      record.tags.forEach(function (tag) {
        tags.appendChild(element("span", "tag", tag));
      });
      card.appendChild(tags);
    }
    var sourceLink = element("a", "rui-link-tool", "打开发表日期页 →");
    sourceLink.href = record.date + ".html#" + record.anchor;
    card.appendChild(sourceLink);
    card.appendChild(buildTools(record));
    return card;
  }

  function yearsForPriority() {
    if (!manifest) return [];
    var info = manifest.priorities[state.priority] || { years: {} };
    return Object.keys(info.years || {}).sort().reverse();
  }

  function filteredRecords() {
    return state.records.filter(function (record) {
      return (!state.direction || record.direction === state.direction) &&
        (!state.relevance || record.relevance_level === state.relevance) &&
        (!state.year || record.date.slice(0, 4) === state.year);
    });
  }

  function render() {
    var filtered = filteredRecords();
    var fragment = document.createDocumentFragment();
    filtered.slice(0, state.shown).forEach(function (record) {
      fragment.appendChild(buildCard(record));
    });
    results.replaceChildren(fragment);
    if (window.RadarUI && window.RadarUI.hydrate) {
      window.RadarUI.hydrate(results);
    } else {
      document.dispatchEvent(new CustomEvent("radar:content-ready", {
        detail: { root: results }
      }));
    }

    var total = (manifest.priorities[state.priority] || {}).total || 0;
    status.textContent = "已载入 " + state.records.length + " / " + total +
      " 篇 " + state.priority + "，当前筛选 " + filtered.length + " 篇";
    var hasMoreVisible = state.shown < filtered.length;
    var hasMoreYears = state.year ? false : state.cursor < yearsForPriority().length;
    more.hidden = !(hasMoreVisible || hasMoreYears);
    more.textContent = hasMoreVisible ? "加载更多" : "加载更早年份";
  }

  function loadYear(year) {
    if (!year || state.loadedYears[year]) return Promise.resolve();
    state.loading = true;
    more.disabled = true;
    status.textContent = "正在加载 " + year + " 年…";
    return fetch("queue-" + state.priority.toLowerCase() + "-" + year + ".json")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (records) {
        state.records = state.records.concat(records);
        state.loadedYears[year] = true;
      })
      .catch(function (error) {
        status.textContent = year + " 年加载失败：" + error.message;
      })
      .then(function () {
        state.loading = false;
        more.disabled = false;
      });
  }

  function loadNextYear() {
    var years = yearsForPriority();
    if (state.year) return loadYear(state.year);
    if (state.cursor >= years.length) return Promise.resolve();
    var year = years[state.cursor++];
    return loadYear(year);
  }

  function syncUrl() {
    var params = new URLSearchParams(window.location.search);
    params.set("priority", state.priority);
    if (state.direction) params.set("direction", state.direction);
    else params.delete("direction");
    if (state.year) params.set("year", state.year);
    else params.delete("year");
    history.replaceState(null, "", "?" + params.toString());
  }

  function resetAndLoad() {
    state.records = [];
    state.loadedYears = {};
    state.cursor = 0;
    state.shown = PAGE_SIZE;
    results.replaceChildren();
    syncUrl();
    var task = state.year ? loadYear(state.year) : loadNextYear();
    task.then(render);
  }

  fetch("queue-manifest.json")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (data) {
      manifest = data;
      var params = new URLSearchParams(window.location.search);
      if (params.get("priority") === "Medium") state.priority = "Medium";
      state.direction = params.get("direction") || "";
      state.year = params.get("year") || "";

      Object.keys(manifest.directions || {}).forEach(function (key) {
        var option = element("option", "", manifest.directions[key].name || key);
        option.value = key;
        directionSelect.appendChild(option);
      });
      directionSelect.value = state.direction;

      function populateYears() {
        yearSelect.replaceChildren(element("option", "", "全部年份"));
        yearSelect.firstChild.value = "";
        yearsForPriority().forEach(function (year) {
          var option = element("option", "", year);
          option.value = year;
          yearSelect.appendChild(option);
        });
        yearSelect.value = state.year;
      }
      populateYears();

      document.querySelectorAll("#queue-priority button").forEach(function (button) {
        button.classList.toggle("is-active", button.dataset.priority === state.priority);
        button.addEventListener("click", function () {
          state.priority = button.dataset.priority;
          state.year = "";
          document.querySelectorAll("#queue-priority button").forEach(function (item) {
            item.classList.toggle("is-active", item === button);
          });
          populateYears();
          resetAndLoad();
        });
      });
      directionSelect.addEventListener("change", function () {
        state.direction = directionSelect.value;
        state.shown = PAGE_SIZE;
        syncUrl();
        render();
      });
      yearSelect.addEventListener("change", function () {
        state.year = yearSelect.value;
        resetAndLoad();
      });
      relevanceSelect.addEventListener("change", function () {
        state.relevance = relevanceSelect.value;
        state.shown = PAGE_SIZE;
        render();
      });
      more.addEventListener("click", function () {
        var visible = filteredRecords();
        if (state.shown < visible.length) {
          state.shown += PAGE_SIZE;
          render();
          return;
        }
        state.shown += PAGE_SIZE;
        loadNextYear().then(render);
      });
      resetAndLoad();
    })
    .catch(function (error) {
      status.textContent = "队列 manifest 加载失败：" + error.message;
    });
})();
