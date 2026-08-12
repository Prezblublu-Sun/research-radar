/* Lazy High/Medium queue for ADR-0027. Dependency-free DOM construction. */
(function () {
  "use strict";

  var PAGE_SIZE = 20;
  var manifest = null;
  var state = {
    priority: "High", direction: "", year: "", relevance: "",
    records: [], loadedYears: {}, cursor: 0, page: 1,
    loading: false, generation: 0
  };

  var results = document.getElementById("queue-results");
  var status = document.getElementById("queue-status");
  var pagination = document.getElementById("queue-pagination");
  var previous = document.getElementById("queue-prev");
  var pageSelect = document.getElementById("queue-page");
  var pageTotal = document.getElementById("queue-page-total");
  var next = document.getElementById("queue-next");
  var directionSelect = document.getElementById("queue-direction");
  var yearSelect = document.getElementById("queue-year");
  var relevanceSelect = document.getElementById("queue-relevance");
  if (!results || !status || !pagination || !previous || !pageSelect ||
      !pageTotal || !next || !directionSelect || !yearSelect ||
      !relevanceSelect) return;

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

  function priorityInfo() {
    return (manifest && manifest.priorities[state.priority]) || {
      total: 0, years: {}, year_facets: {}
    };
  }

  function yearMatchCount(year) {
    var info = priorityInfo();
    if (!state.direction && !state.relevance) {
      return Number((info.years || {})[year] || 0);
    }
    var facets = (info.year_facets || {})[year];
    if (!facets) return null;
    if (state.direction && state.relevance) {
      var pairs = (facets.direction_relevance || {})[state.direction] || {};
      return Number(pairs[state.relevance] || 0);
    }
    if (state.direction) {
      return Number((facets.directions || {})[state.direction] || 0);
    }
    return Number((facets.relevance || {})[state.relevance] || 0);
  }

  function knownFilteredTotal() {
    var years = state.year ? [state.year] : yearsForPriority();
    var total = 0;
    for (var index = 0; index < years.length; index += 1) {
      var count = yearMatchCount(years[index]);
      if (count == null) return null;
      total += count;
    }
    return total;
  }

  function pageCountFor(total) {
    return Math.ceil(total / PAGE_SIZE);
  }

  function clampPage(page, total) {
    var count = pageCountFor(total);
    if (!count) return 1;
    return Math.min(Math.max(1, page), count);
  }

  function renderPagination(total) {
    var count = pageCountFor(total);
    state.page = clampPage(state.page, total);
    var options = document.createDocumentFragment();
    var optionCount = Math.max(1, count);
    for (var page = 1; page <= optionCount; page += 1) {
      var option = element("option", "", "第 " + page + " 页");
      option.value = String(page);
      options.appendChild(option);
    }
    pageSelect.replaceChildren(options);
    pageSelect.value = String(state.page);
    pageSelect.disabled = state.loading || count === 0;
    previous.disabled = state.loading || state.page <= 1 || count === 0;
    next.disabled = state.loading || state.page >= count || count === 0;
    pageTotal.textContent = "共 " + count + " 页";
    pagination.hidden = false;
  }

  function render() {
    var filtered = filteredRecords();
    var knownTotal = knownFilteredTotal();
    var total = knownTotal == null ? filtered.length : knownTotal;
    state.page = clampPage(state.page, total);
    var start = (state.page - 1) * PAGE_SIZE;
    var fragment = document.createDocumentFragment();
    filtered.slice(start, start + PAGE_SIZE).forEach(function (record) {
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

    var count = pageCountFor(total);
    status.textContent = state.priority + "：当前筛选 " + total +
      " 篇 · 第 " + (total ? state.page : 0) + " / " + count +
      " 页 · 每页 " + PAGE_SIZE + " 篇";
    renderPagination(total);
    syncUrl();
  }

  function sortRecords() {
    state.records.sort(function (left, right) {
      var dateOrder = String(right.date || "").localeCompare(
        String(left.date || "")
      );
      if (dateOrder) return dateOrder;
      return String(right.title || "").localeCompare(String(left.title || ""));
    });
  }

  function loadYear(year, generation) {
    if (!year || state.loadedYears[year]) return Promise.resolve();
    var requestedPriority = state.priority;
    status.textContent = "正在加载 " + year + " 年…";
    return fetch("queue-" + requestedPriority.toLowerCase() + "-" + year + ".json")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (records) {
        if (generation !== state.generation ||
            requestedPriority !== state.priority) return;
        state.records = state.records.concat(records);
        state.loadedYears[year] = true;
        sortRecords();
      })
      .catch(function (error) {
        if (generation !== state.generation) return;
        throw new Error(year + " 年加载失败：" + error.message);
      });
  }

  function loadNextPrefixYear(generation, skipEmptyMatches) {
    var years = yearsForPriority();
    if (state.cursor >= years.length) return Promise.resolve();
    var index = state.cursor;
    var year = years[index];
    var count = yearMatchCount(year);
    if (skipEmptyMatches && count === 0) {
      state.cursor = index + 1;
      return Promise.resolve();
    }
    return loadYear(year, generation).then(function () {
      if (generation === state.generation && state.cursor === index) {
        state.cursor = index + 1;
      }
    });
  }

  function loadedPrefixMatchCount() {
    var years = yearsForPriority().slice(0, state.cursor);
    return years.reduce(function (total, year) {
      return total + Number(yearMatchCount(year) || 0);
    }, 0);
  }

  function ensurePrefixForPage(generation, total) {
    var target = Math.min(state.page * PAGE_SIZE, total);
    function step() {
      if (generation !== state.generation ||
          loadedPrefixMatchCount() >= target ||
          state.cursor >= yearsForPriority().length) {
        return Promise.resolve();
      }
      return loadNextPrefixYear(generation, true).then(step);
    }
    return step();
  }

  function loadAllYears(generation) {
    function step() {
      if (generation !== state.generation ||
          state.cursor >= yearsForPriority().length) {
        return Promise.resolve();
      }
      return loadNextPrefixYear(generation, false).then(step);
    }
    return step();
  }

  function ensureDataForView(generation) {
    if (state.year) return loadYear(state.year, generation);
    var total = knownFilteredTotal();
    if (total == null) return loadAllYears(generation);
    return ensurePrefixForPage(generation, total);
  }

  function syncUrl() {
    var params = new URLSearchParams(window.location.search);
    params.set("priority", state.priority);
    if (state.direction) params.set("direction", state.direction);
    else params.delete("direction");
    if (state.year) params.set("year", state.year);
    else params.delete("year");
    if (state.relevance) params.set("relevance", state.relevance);
    else params.delete("relevance");
    if (state.page > 1) params.set("page", String(state.page));
    else params.delete("page");
    history.replaceState(null, "", "?" + params.toString());
  }

  function setLoadingState() {
    state.loading = true;
    status.textContent = "正在准备第 " + state.page + " 页…";
    previous.disabled = true;
    pageSelect.disabled = true;
    next.disabled = true;
  }

  function loadView(page, resetRecords) {
    state.generation += 1;
    var generation = state.generation;
    if (resetRecords) {
      state.records = [];
      state.loadedYears = {};
      results.replaceChildren();
    }
    state.cursor = 0;
    state.page = Math.max(1, Number(page) || 1);
    var knownTotal = knownFilteredTotal();
    if (knownTotal != null) state.page = clampPage(state.page, knownTotal);
    setLoadingState();
    syncUrl();
    ensureDataForView(generation)
      .then(function () {
        if (generation !== state.generation) return;
        state.loading = false;
        render();
      })
      .catch(function (error) {
        if (generation !== state.generation) return;
        state.loading = false;
        status.textContent = error.message;
        renderPagination(knownFilteredTotal() || 0);
      });
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
      state.relevance = params.get("relevance") || "";
      if (state.direction && !(manifest.directions || {})[state.direction]) {
        state.direction = "";
      }
      if (["Direct", "Transferable", "Peripheral"].indexOf(
        state.relevance
      ) === -1) {
        state.relevance = "";
      }
      var initialPage = Math.max(1, Number(params.get("page")) || 1);

      Object.keys(manifest.directions || {}).forEach(function (key) {
        var option = element("option", "", manifest.directions[key].name || key);
        option.value = key;
        directionSelect.appendChild(option);
      });
      directionSelect.value = state.direction;
      relevanceSelect.value = state.relevance;

      function populateYears() {
        yearSelect.replaceChildren(element("option", "", "全部年份"));
        yearSelect.firstChild.value = "";
        yearsForPriority().forEach(function (year) {
          var option = element("option", "", year);
          option.value = year;
          yearSelect.appendChild(option);
        });
        if (state.year && yearsForPriority().indexOf(state.year) === -1) {
          state.year = "";
        }
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
          loadView(1, true);
        });
      });
      directionSelect.addEventListener("change", function () {
        state.direction = directionSelect.value;
        loadView(1, false);
      });
      yearSelect.addEventListener("change", function () {
        state.year = yearSelect.value;
        loadView(1, false);
      });
      relevanceSelect.addEventListener("change", function () {
        state.relevance = relevanceSelect.value;
        loadView(1, false);
      });
      previous.addEventListener("click", function () {
        if (!state.loading && state.page > 1) loadView(state.page - 1, false);
      });
      next.addEventListener("click", function () {
        if (!state.loading) loadView(state.page + 1, false);
      });
      pageSelect.addEventListener("change", function () {
        if (!state.loading) loadView(Number(pageSelect.value), false);
      });
      loadView(initialPage, true);
    })
    .catch(function (error) {
      status.textContent = "队列 manifest 加载失败：" + error.message;
    });
})();
