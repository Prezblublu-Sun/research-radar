/* Shared, DOM-safe paper-card renderer for lazy data views. */
(function () {
  "use strict";

  function text(value) {
    return value == null ? "" : String(value);
  }

  function element(tag, className, value) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (value != null) node.textContent = text(value);
    return node;
  }

  function classToken(value) {
    return text(value).toLowerCase().replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  function fallbackAnchor(identity) {
    var source = text(identity) || "paper";
    var hash = 2166136261;
    for (var index = 0; index < source.length; index += 1) {
      hash ^= source.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return "p-" + (hash >>> 0).toString(16);
  }

  function addTextRow(parent, label, value, keepEmpty) {
    if (!keepEmpty && !value) return;
    var row = element("div");
    row.appendChild(element("b", "", label + "\u00b7 "));
    row.appendChild(document.createTextNode(text(value)));
    parent.appendChild(row);
  }

  function addExternalLink(parent, record) {
    var wrapper = element("span", "doi");
    var link = null;
    if (record.doi) {
      link = element("a", "", record.doi);
      link.href = "https://doi.org/" + text(record.doi)
        .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "");
    } else if (record.url) {
      try {
        var parsed = new URL(text(record.url), document.baseURI);
        if (parsed.protocol === "http:" || parsed.protocol === "https:") {
          link = element("a", "", "link");
          link.href = parsed.href;
        }
      } catch (error) {
        /* Invalid or unsafe source URL: render no clickable link. */
      }
    }
    if (link) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      wrapper.appendChild(link);
    }
    parent.appendChild(wrapper);
  }

  var visualImageHosts = {
    "arxiv.org": true,
    "export.arxiv.org": true,
    "pmc-oa-opendata.s3.amazonaws.com": true
  };

  function safeVisualUrl(value, imageAsset) {
    var raw = text(value).trim();
    if (!raw || raw.charAt(0) === "#" || /^\/\//.test(raw)) return "";
    var hasScheme = /^[a-z][a-z0-9+.-]*:/i.test(raw);
    try {
      var parsed = new URL(raw, document.baseURI);
      if (parsed.origin === window.location.origin &&
          (!hasScheme || parsed.protocol === "https:")) {
        return parsed.href;
      }
      if (parsed.protocol === "https:" &&
          (!imageAsset || visualImageHosts[parsed.hostname.toLowerCase()])) {
        return parsed.href;
      }
    } catch (error) {
      /* Invalid or unsafe visual URL: use the explicit empty state. */
    }
    return "";
  }

  function positiveDimension(value) {
    var number = Number(value);
    return Number.isFinite(number) && number > 0 && number <= 10000 ?
      Math.round(number) : 0;
  }

  function usefulVisualAlt(value) {
    var rendered = text(value).trim();
    if (/^(?:(?:refer|see)\s+(?:to\s+)?(?:the\s+)?caption|(?:figure|image|graphic))[.!]?$/i.test(rendered)) {
      return "";
    }
    return rendered;
  }

  function visualRecord(record) {
    var visual = record.visual;
    if (!visual || typeof visual !== "object" || Array.isArray(visual)) {
      visual = record.figure;
    }
    return visual && typeof visual === "object" && !Array.isArray(visual) ?
      visual : {};
  }

  function renderVisualFallback(figure) {
    figure.className = "paper-visual paper-visual--empty";
    figure.dataset.visualStatus = "unavailable";
    var frame = element("div", "paper-visual__frame paper-visual__fallback");
    var symbol = element("span", "paper-visual__symbol", "\u25a7");
    symbol.setAttribute("aria-hidden", "true");
    frame.appendChild(symbol);
    frame.appendChild(element(
      "span", "paper-visual__empty-label", "暂时没有获取到图片"
    ));
    figure.replaceChildren(frame);
  }

  function bindImageFallback(image, figure) {
    if (image.dataset.visualReady === "1") return;
    image.dataset.visualReady = "1";
    image.addEventListener("error", function () {
      renderVisualFallback(figure);
    }, { once: true });
    if (image.complete && image.naturalWidth === 0) {
      renderVisualFallback(figure);
    }
  }

  var visualViewerState = null;

  function ensureVisualViewer() {
    if (visualViewerState) return visualViewerState;
    var dialog = element("dialog", "paper-visual-viewer");
    if (typeof dialog.showModal !== "function") return null;
    dialog.setAttribute("aria-labelledby", "paper-visual-viewer-title");

    var toolbar = element("div", "paper-visual-viewer__toolbar");
    var heading = element(
      "strong", "paper-visual-viewer__title", "论文插图"
    );
    heading.id = "paper-visual-viewer-title";
    toolbar.appendChild(heading);
    var links = element("div", "paper-visual-viewer__links");
    var original = element("a", "paper-visual-viewer__link", "新窗口打开原图 ↗");
    original.target = "_blank";
    original.rel = "noopener noreferrer";
    links.appendChild(original);
    var source = element("a", "paper-visual-viewer__link", "查看论文来源 ↗");
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    links.appendChild(source);
    var close = element("button", "paper-visual-viewer__close", "关闭");
    close.type = "button";
    links.appendChild(close);
    toolbar.appendChild(links);
    dialog.appendChild(toolbar);

    var viewport = element("div", "paper-visual-viewer__viewport");
    var image = element("img", "paper-visual-viewer__image");
    image.referrerPolicy = "no-referrer";
    viewport.appendChild(image);
    dialog.appendChild(viewport);
    var caption = element("p", "paper-visual-viewer__caption");
    dialog.appendChild(caption);

    visualViewerState = {
      dialog: dialog, image: image, caption: caption,
      original: original, source: source, trigger: null
    };
    close.addEventListener("click", function () { dialog.close(); });
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", function () {
      image.removeAttribute("src");
      if (visualViewerState.trigger &&
          document.documentElement.contains(visualViewerState.trigger)) {
        visualViewerState.trigger.focus();
      }
      visualViewerState.trigger = null;
    });
    document.body.appendChild(dialog);
    return visualViewerState;
  }

  function bindVisualViewer(image, figure) {
    var link = image.closest("a.paper-visual__image-link");
    if (!link || link.dataset.visualViewerReady === "1") return;
    link.dataset.visualViewerReady = "1";
    link.addEventListener("click", function (event) {
      if (event.button !== 0 || event.metaKey || event.ctrlKey ||
          event.shiftKey || event.altKey) return;
      var viewer = ensureVisualViewer();
      if (!viewer) return;
      var imageUrl = safeVisualUrl(link.href, true);
      if (!imageUrl) return;
      event.preventDefault();
      viewer.trigger = link;
      viewer.image.src = imageUrl;
      viewer.image.alt = image.alt;
      viewer.original.href = imageUrl;
      var sourceLink = figure.querySelector("a.paper-visual__source[href]");
      var sourceUrl = sourceLink ? safeVisualUrl(sourceLink.href, false) : "";
      viewer.source.hidden = !sourceUrl;
      if (sourceUrl) viewer.source.href = sourceUrl;
      viewer.caption.textContent = text(
        (figure.querySelector(".paper-visual__caption") || {}).textContent
      ).trim();
      viewer.caption.hidden = !viewer.caption.textContent;
      viewer.dialog.showModal();
    });
  }

  function appendVisualMeta(figure, visual) {
    var sourceUrl = safeVisualUrl(visual.source_url, false);
    var sourceLabel = text(visual.source_label).trim();
    var license = text(visual.license).trim();
    if (!sourceUrl && !sourceLabel && !license) return;

    var meta = element("div", "paper-visual__meta");
    if (sourceUrl) {
      var source = element("a", "paper-visual__source", sourceLabel || "图片来源");
      source.href = sourceUrl;
      source.target = "_blank";
      source.rel = "noopener noreferrer";
      meta.appendChild(source);
    } else if (sourceLabel) {
      meta.appendChild(element("span", "paper-visual__source", sourceLabel));
    }
    if (license) {
      meta.appendChild(element("span", "paper-visual__license", license));
    }
    figure.appendChild(meta);
  }

  function buildVisual(record) {
    var visual = visualRecord(record);
    var status = text(visual.status).toLowerCase();
    var imageUrl = safeVisualUrl(visual.image_url, true);
    var figure = element("figure", "paper-visual");
    if ((status !== "available" && status !== "found") || !imageUrl) {
      renderVisualFallback(figure);
      return figure;
    }

    figure.dataset.visualStatus = "available";
    var frame = element("div", "paper-visual__frame");
    var image = element("img", "paper-visual__image");
    image.src = imageUrl;
    image.alt = usefulVisualAlt(visual.alt) ||
      (record.title ? "论文插图：" + text(record.title).slice(0, 220) :
        text(visual.caption).trim() || "论文插图");
    image.loading = "lazy";
    image.decoding = "async";
    image.referrerPolicy = "no-referrer";
    var width = positiveDimension(visual.width);
    var height = positiveDimension(visual.height);
    if (width) image.width = width;
    if (height) image.height = height;

    var imageLink = element("a", "paper-visual__image-link");
    imageLink.href = imageUrl;
    imageLink.target = "_blank";
    imageLink.rel = "noopener noreferrer";
    imageLink.setAttribute("aria-label", "查看原图");
    imageLink.title = "查看原图";
    imageLink.appendChild(image);
    frame.appendChild(imageLink);
    figure.appendChild(frame);
    if (visual.caption) {
      figure.appendChild(element(
        "figcaption", "paper-visual__caption", visual.caption
      ));
    }
    appendVisualMeta(figure, visual);
    bindImageFallback(image, figure);
    bindVisualViewer(image, figure);
    return figure;
  }

  function enhanceVisuals(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll(".paper-visual img").forEach(function (image) {
      var figure = image.closest(".paper-visual");
      if (figure) {
        bindImageFallback(image, figure);
        bindVisualViewer(image, figure);
      }
    });
  }

  function authorText(record) {
    if (record.authors_display) return text(record.authors_display);
    if (typeof record.authors === "string") return record.authors;
    var authors = Array.isArray(record.authors) ? record.authors : [];
    var rendered = authors.map(text).join(", ");
    if (record.authors_truncated && rendered) rendered += " et al.";
    return rendered;
  }

  function buildTools(anchor) {
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
      radio.name = "rui-mark-" + anchor;
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

  function appendFlags(head, flags) {
    [
      ["has_experimental_validation", "Exp. validation"],
      ["has_uncertainty_quantification", "UQ"],
      ["is_patient_specific", "Patient-specific"],
      ["is_review", "Review"]
    ].forEach(function (item) {
      if (flags && flags[item[0]]) {
        head.appendChild(element("span", "flag", item[1]));
      }
    });
  }

  function appendCorresponding(card, corresponding) {
    if (!Array.isArray(corresponding)) return;
    var entries = corresponding.filter(function (entry) {
      return entry && typeof entry === "object" && entry.affiliation;
    });
    if (!entries.length) return;
    var row = element("div", "corresponding");
    row.appendChild(element("b", "", "通讯:"));
    row.appendChild(document.createTextNode(" "));
    entries.forEach(function (entry, index) {
      if (index) row.appendChild(document.createTextNode("  |  "));
      row.appendChild(document.createTextNode(text(entry.name) + " "));
      row.appendChild(element(
        "span", "corresp-aff", "@ " + text(entry.affiliation).slice(0, 120)
      ));
      if (entry.inferred) {
        row.appendChild(document.createTextNode(" "));
        row.appendChild(element("i", "", "[推断]"));
      }
    });
    card.appendChild(row);
  }

  function appendSummary(parent, className, summary, labels) {
    var container = element("div", className);
    summary = summary && typeof summary === "object" ? summary : {};
    labels.forEach(function (item) {
      addTextRow(container, item[1], summary[item[0]], true);
    });
    parent.appendChild(container);
  }

  function appendEnglishSummary(card, record) {
    var details = element("details", "summary-en");
    details.appendChild(element("summary", "", "英文摘要与术语"));
    appendSummary(details, "summary en", record.summary_en, [
      ["motivation", "Motivation"], ["method", "Method"],
      ["result", "Result"], ["validation", "Validation"]
    ]);
    var terms = element("div", "key-terms");
    (Array.isArray(record.key_terms) ? record.key_terms : []).forEach(function (term) {
      var node = element("span", "term");
      if (term && typeof term === "object") {
        node.appendChild(element("b", "", term.en || ""));
        node.appendChild(document.createTextNode(" · " + text(term.zh)));
      } else {
        node.textContent = text(term);
      }
      terms.appendChild(node);
    });
    details.appendChild(terms);
    card.appendChild(details);
  }

  function buildCard(record, options) {
    record = record && typeof record === "object" ? record : {};
    options = options || {};
    var identity = text(record.identity_key);
    var anchor = text(record.anchor) || fallbackAnchor(identity || record.title);
    var priority = text(record.priority) || "Low";
    var priorityLabel = record.priority_label ||
      (priority === "Unscored" ? "待评分" : priority);

    var card = element("article", "paper");
    card.id = anchor;
    card.dataset.identityKey = identity;
    card.dataset.direction = text(record.direction);
    card.dataset.priority = priority;
    card.dataset.title = text(record.title);
    card.dataset.date = text(record.date);

    card.appendChild(element("h3", "paper-title", record.title || "Untitled"));
    var head = element("div", "paper-head");
    head.appendChild(element(
      "span", "priority priority--" + classToken(priority), priorityLabel
    ));
    var direction = element(
      "span", "direction-pill", record.direction_name || record.direction
    );
    if (/^#[0-9a-f]{6}$/i.test(text(record.direction_color))) {
      direction.style.color = record.direction_color;
      direction.style.backgroundColor = record.direction_color + "20";
    }
    head.appendChild(direction);
    if (record.source) head.appendChild(element("span", "source", record.source));
    if (record.relevance_level) {
      head.appendChild(element(
        "span", "relevance-level lvl-" + classToken(record.relevance_level),
        record.relevance_level
      ));
    }
    if (record.read_action) {
      head.appendChild(element(
        "span", "read-action act-" + classToken(record.read_action),
        record.read_action
      ));
    }
    if (record.validation_kind) {
      head.appendChild(element("span", "validation-kind", record.validation_kind));
    }
    appendFlags(head, record.flags || {});
    card.appendChild(head);

    var meta = element("div", "meta");
    meta.appendChild(element("span", "authors", authorText(record)));
    meta.appendChild(element("span", "venue", record.venue || ""));
    meta.appendChild(element("span", "date", record.date || ""));
    addExternalLink(meta, record);
    card.appendChild(meta);

    var body = element("div", "paper-body");
    var copy = element("div", "paper-copy");
    if (record.first_author_affiliation) {
      var affiliation = element("div", "affiliations");
      affiliation.appendChild(element("b", "", "单位:"));
      affiliation.appendChild(document.createTextNode(
        " " + text(record.first_author_affiliation).slice(0, 200)
      ));
      copy.appendChild(affiliation);
    }
    appendCorresponding(copy, record.corresponding_authors);

    var relevance = element("div", "relevance");
    relevance.appendChild(element("b", "", "相关性:"));
    relevance.appendChild(document.createTextNode(
      " " + text(record.relevance_to_user)
    ));
    copy.appendChild(relevance);
    if (record.why_not_core) {
      var boundary = element("div", "why-not-core");
      boundary.appendChild(element("b", "", "边界:"));
      boundary.appendChild(document.createTextNode(" " + text(record.why_not_core)));
      copy.appendChild(boundary);
    }

    appendSummary(copy, "summary", record.summary_zh, [
      ["motivation", "动机"], ["method", "方法"],
      ["result", "结果"], ["validation", "验证"]
    ]);
    appendEnglishSummary(copy, record);

    var tags = element("div", "tags-row");
    (Array.isArray(record.tags) ? record.tags : []).forEach(function (tag) {
      tags.appendChild(element("span", "tag", tag));
    });
    copy.appendChild(tags);

    if (options.dailyLink && /^\d{4}-\d{2}-\d{2}$/.test(text(record.date))) {
      var sourceLink = element("a", "rui-link-tool", "打开发表日期页 →");
      sourceLink.href = record.date + ".html#" + encodeURIComponent(anchor);
      copy.appendChild(sourceLink);
    }
    body.appendChild(copy);
    body.appendChild(buildVisual(record));
    card.appendChild(body);
    card.appendChild(buildTools(anchor));
    return card;
  }

  window.RadarCard = {
    buildCard: buildCard,
    enhanceVisuals: enhanceVisuals
  };
  enhanceVisuals(document);
})();
