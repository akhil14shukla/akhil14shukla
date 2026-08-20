// @ts-check
/**
 * Glance Map webview: rendering and interaction only. Layout arrives already
 * computed from the extension host, so there is one tested implementation and
 * the picture is identical every time.
 */
(function () {
  const vscode = acquireVsCodeApi();
  const SVGNS = "http://www.w3.org/2000/svg";

  const stage = document.getElementById("stage");
  const svg = document.getElementById("svg");
  const stateEl = document.getElementById("state");
  const fileEl = document.getElementById("file");
  const badgeEl = document.getElementById("badge");
  const extBox = /** @type {HTMLInputElement} */ (document.getElementById("ext"));
  const viewSel = /** @type {HTMLSelectElement} */ (document.getElementById("view"));
  const captionEl = document.getElementById("caption");
  const depthSel = /** @type {HTMLSelectElement} */ (document.getElementById("depth"));
  const depthWrap = document.getElementById("depthWrap");
  const legendEl = document.getElementById("legend");

  /** @type {any} */ let current = null;
  const view = { x: 0, y: 0, k: 1 };
  /** Adjacency for hover tracing. */
  let adj = new Map();

  // Group hue comes from the theme's chart palette, so it stays in key with
  // whatever colour scheme the user runs.
  const GROUP_COLORS = [
    "--vscode-charts-blue",
    "--vscode-charts-purple",
    "--vscode-charts-green",
    "--vscode-charts-orange",
    "--vscode-charts-yellow",
    "--vscode-charts-red",
  ];
  const FALLBACK = ["#4c8bf5", "#a970d0", "#3fa46a", "#d98a3a", "#d0b23a", "#cc5f5f"];

  function groupColor(group, groups, pinned) {
    if (!group) {
      return "transparent";
    }
    // A view may pin colours where the group means something; otherwise cycle.
    const i = groups.indexOf(group);
    const varName =
      (pinned && pinned[group]) || GROUP_COLORS[i % GROUP_COLORS.length];
    const resolved = getComputedStyle(document.documentElement)
      .getPropertyValue(varName)
      .trim();
    return resolved || FALLBACK[i % FALLBACK.length];
  }

  function el(name, attrs, parent) {
    const e = document.createElementNS(SVGNS, name);
    for (const k in attrs) {
      if (attrs[k] !== undefined && attrs[k] !== null) {
        e.setAttribute(k, String(attrs[k]));
      }
    }
    if (parent) {
      parent.appendChild(e);
    }
    return e;
  }

  /** Smooth polyline through routed points. */
  function pathFor(points) {
    if (points.length === 2) {
      const [a, b] = points;
      const my = (a.y + b.y) / 2;
      return `M ${a.x} ${a.y} C ${a.x} ${my}, ${b.x} ${my}, ${b.x} ${b.y}`;
    }
    let d = `M ${points[0].x} ${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
      const p = points[i - 1];
      const q = points[i];
      const my = (p.y + q.y) / 2;
      d += ` C ${p.x} ${my}, ${q.x} ${my}, ${q.x} ${q.y}`;
    }
    return d;
  }

  /**
   * Trim to fit the box. `perChar` differs by row: the name is 12px monospace,
   * the subtitle 10px sans — using one estimate for both clipped subtitles that
   * had room to spare.
   */
  function truncate(text, width, perChar) {
    const max = Math.floor((width - 24) / (perChar || 7.1));
    return text.length > max ? text.slice(0, Math.max(1, max - 1)) + "…" : text;
  }

  function applyView() {
    const g = svg.querySelector("#root");
    if (g) {
      g.setAttribute(
        "transform",
        `translate(${view.x} ${view.y}) scale(${view.k})`
      );
    }
  }

  function render(scene, meta) {
    current = { data: scene, meta };
    svg.textContent = "";
    const { nodes, edges, width, height, lanes, dividers } = scene;

    fileEl.textContent = meta.file ? `Glance Map · ${meta.file}` : "Glance Map";
    captionEl.textContent = scene.caption || "";
    captionEl.hidden = !scene.caption;

    const notes = [];
    if (!meta.semantic) notes.push("text fallback");
    if (meta.truncated) notes.push("partial");
    if (notes.length) {
      badgeEl.textContent = notes.join(" · ");
      badgeEl.hidden = false;
      badgeEl.title = meta.semantic
        ? "Too many methods to map every call; showing the first 60."
        : "No language server answered for this file, so structure was read from text and calls could not be resolved.";
    } else {
      badgeEl.hidden = true;
    }

    if (!nodes.length) {
      renderLegend(scene);
      stateEl.textContent = scene.empty || "Nothing to show for this file.";
      stateEl.style.display = "";
      svg.setAttribute("hidden", "");
      return;
    }
    stateEl.style.display = "none";
    svg.removeAttribute("hidden");

    const root = el("g", { id: "root" }, svg);

    adj = new Map();
    nodes.forEach((n) => adj.set(n.id, new Set()));
    edges.forEach((e) => {
      if (adj.has(e.from) && adj.has(e.to)) {
        adj.get(e.from).add(e.to);
        adj.get(e.to).add(e.from);
      }
    });

    // lifelines sit behind everything
    if (lanes && lanes.length) {
      const laneLayer = el("g", {}, root);
      lanes.forEach((l) => {
        el("line", {
          x1: l.x, y1: l.top, x2: l.x, y2: l.bottom, class: "lane",
        }, laneLayer);
      });
    }

    (dividers || []).forEach((d) => {
      el("line", {
        x1: 16, y1: d.y, x2: width - 16, y2: d.y, class: "divider",
      }, root);
      el("text", { x: 16, y: d.y + 18, class: "divider-label" }, root).textContent =
        d.label;
    });

    renderLegend(scene);

    const groups = [...new Set(nodes.map((n) => n.group).filter(Boolean))].sort();

    // edges under nodes
    const edgeLayer = el("g", {}, root);
    edges.forEach((e) => {
      if (e.self || !e.points || e.points.length < 2) {
        return;
      }
      const cls = ["edge"];
      if (e.style === "dashed") cls.push("cross");
      if (e.style === "inherit") cls.push("inherit");
      if (e.style === "flow") cls.push("flow");

      el("path", {
        d: pathFor(e.points),
        class: cls.join(" "),
        "stroke-width": Math.min(3.2, 1.4 + ((e.count || 1) - 1) * 0.5),
        "data-from": e.from,
        "data-to": e.to,
      }, edgeLayer);

      const last = e.points[e.points.length - 1];
      const prev = e.points[e.points.length - 2];
      const ang = Math.atan2(last.y - prev.y, last.x - prev.x);
      const size = 5.5;
      el("path", {
        d: `M ${last.x} ${last.y} L ${last.x - size * Math.cos(ang - 0.5)} ${last.y - size * Math.sin(ang - 0.5)} L ${last.x - size * Math.cos(ang + 0.5)} ${last.y - size * Math.sin(ang + 0.5)} Z`,
        class: e.style === "inherit" ? "arrow hollow" : "arrow",
        "data-from": e.from,
        "data-to": e.to,
      }, edgeLayer);

      if (e.label || e.order) {
        const mid = e.points[Math.floor(e.points.length / 2)];
        const midPrev = e.points[Math.floor(e.points.length / 2) - 1] || mid;
        const lx = (mid.x + midPrev.x) / 2;
        const ly = (mid.y + midPrev.y) / 2;
        const text = (e.order ? `${e.order}. ` : "") + (e.label || "");
        const t = el("text", {
          x: lx, y: ly - 6, class: "edgelabel", "text-anchor": "middle",
          "data-from": e.from, "data-to": e.to,
        }, edgeLayer);
        t.textContent = text;
      }
    });

    const selfIds = new Set(edges.filter((e) => e.self).map((e) => e.from));

    // nodes
    const nodeLayer = el("g", {}, root);
    nodes.forEach((n) => {
      const cls = ["node", "role-" + (n.role || "method")];
      if (n.external) cls.push("external");
      if (n.entry) cls.push("entry");
      if (n.complexity >= 10) cls.push("complex");
      if (n.severity === 2) cls.push("err");
      else if (n.severity === 1) cls.push("warn");
      if (n.clickLine === undefined) cls.push("static");

      const g = el("g", {
        class: cls.join(" "),
        "data-id": n.id,
        tabindex: "0",
        role: n.clickLine === undefined ? "img" : "button",
      }, nodeLayer);

      el("title", {}, g).textContent = n.tip || n.label;
      el("rect", { x: n.x, y: n.y, width: n.w, height: n.h, rx: 6 }, g);

      if (n.group) {
        el("line", {
          x1: n.x + 1.5, y1: n.y + 7, x2: n.x + 1.5, y2: n.y + n.h - 7,
          class: "rail",
          stroke: groupColor(n.group, groups, scene.groupColors),
        }, g);
      }

      const hasRows = n.rows && n.rows.length;
      const hasSub = !!n.sub;
      el("text", {
        x: n.x + 12,
        y: hasSub || hasRows ? n.y + 16 : n.y + n.h / 2,
      }, g).textContent =
        (n.entry ? "\u25b6 " : "") +
        truncate(n.label, n.w - (n.entry ? 14 : 0)) +
        (selfIds.has(n.id) ? " \u21bb" : "");

      if (hasSub) {
        el("text", {
          x: n.x + 12, y: n.y + 30, class: "sub",
        }, g).textContent = truncate(n.sub, n.w, 5.4);
      }

      if (hasRows) {
        el("line", {
          x1: n.x, y1: n.y + 26, x2: n.x + n.w, y2: n.y + 26, class: "rowrule",
        }, g);
        n.rows.forEach((row, i) => {
          el("text", {
            x: n.x + 12, y: n.y + 42 + i * 16, class: "row",
          }, g).textContent = truncate(row, n.w, 6.2);
        });
      }

      const navigable = n.clickLine !== undefined;
      if (navigable) {
        g.addEventListener("click", () =>
          vscode.postMessage({ type: "reveal", id: n.id })
        );
        g.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            vscode.postMessage({ type: "reveal", id: n.id });
          }
        });
      }
      g.addEventListener("mouseenter", () => trace(n.id));
      g.addEventListener("focus", () => trace(n.id));
      g.addEventListener("mouseleave", clearTrace);
      g.addEventListener("blur", clearTrace);
    });

    fit();
  }

  /** The legend belongs to the view, so it is rebuilt with every scene. */
  function renderLegend(scene) {
    legendEl.textContent = "";
    (scene.legend || []).forEach((item) => {
      const span = document.createElement("span");
      const sw = document.createElement("i");
      sw.className = "sw " + item.swatch;
      span.appendChild(sw);
      span.appendChild(document.createTextNode(item.label));
      legendEl.appendChild(span);
    });
    if (scene.hint) {
      const hint = document.createElement("span");
      hint.className = "hint";
      hint.textContent = scene.hint;
      legendEl.appendChild(hint);
    }
  }

  /** Highlight a node, everything it touches, and the edges between. */
  function trace(id) {
    const related = new Set([id]);
    (adj.get(id) || new Set()).forEach((v) => related.add(v));

    svg.querySelectorAll(".node").forEach((g) => {
      const nid = g.getAttribute("data-id");
      g.classList.toggle("hot", nid === id);
      g.classList.toggle("dim", !related.has(nid));
    });
    svg.querySelectorAll(".edge, .arrow, .edgelabel").forEach((p) => {
      const on =
        p.getAttribute("data-from") === id || p.getAttribute("data-to") === id;
      p.classList.toggle("hot", on);
      p.classList.toggle("dim", !on);
    });
  }

  function clearTrace() {
    svg.querySelectorAll(".node").forEach((g) => g.classList.remove("hot", "dim"));
    svg.querySelectorAll(".edge, .arrow, .edgelabel").forEach((p) =>
      p.classList.remove("hot", "dim")
    );
  }

  function fit() {
    if (!current) return;
    const { width, height } = current.data;
    const vw = stage.clientWidth;
    const vh = stage.clientHeight;
    svg.setAttribute("viewBox", `0 0 ${vw} ${vh}`);
    const k = Math.min(vw / (width + 32), vh / (height + 32), 1);
    view.k = k > 0 ? k : 1;
    view.x = (vw - width * view.k) / 2;
    // Centre vertically when the whole map fits; otherwise pin to the top so
    // the entry points are the first thing on screen.
    const scaled = height * view.k;
    view.y = scaled < vh - 24 ? (vh - scaled) / 2 : 12;
    applyView();
  }

  // ---- pan & zoom ----
  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  stage.addEventListener("mousedown", (e) => {
    if (e.target.closest(".node")) return;
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    stage.classList.add("panning");
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    view.x += e.clientX - lastX;
    view.y += e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    applyView();
  });
  window.addEventListener("mouseup", () => {
    dragging = false;
    stage.classList.remove("panning");
  });
  stage.addEventListener("wheel", (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    const next = Math.max(0.2, Math.min(3, view.k * factor));
    const rect = stage.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    // keep the point under the cursor fixed while zooming
    view.x = mx - ((mx - view.x) * next) / view.k;
    view.y = my - ((my - view.y) * next) / view.k;
    view.k = next;
    applyView();
  }, { passive: false });

  // ---- controls ----
  document.getElementById("fit").addEventListener("click", fit);
  document.getElementById("reload").addEventListener("click", () =>
    vscode.postMessage({ type: "refresh" })
  );
  document.getElementById("copy").addEventListener("click", () =>
    vscode.postMessage({ type: "copyMermaid" })
  );
  function requestLayout() {
    vscode.postMessage({
      type: "relayout",
      width: Math.max(520, stage.clientWidth - 40),
      showExternal: extBox.checked,
      view: viewSel.value,
      depth: Number(depthSel.value),
    });
  }
  extBox.addEventListener("change", requestLayout);
  viewSel.addEventListener("change", requestLayout);
  depthSel.addEventListener("change", requestLayout);

  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      requestLayout();
    }, 160);
  });

  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (msg.type === "loading") {
      stateEl.textContent = "Resolving calls…";
      stateEl.style.display = "";
      svg.setAttribute("hidden", "");
      return;
    }
    if (msg.type === "render") {
      extBox.checked = !!msg.meta.showExternal;
      if (msg.meta.view) viewSel.value = msg.meta.view;
      extBox.parentElement.hidden = msg.meta.view !== "graph";
      depthWrap.hidden = msg.meta.view !== "sequence";
      render(msg.scene, msg.meta);
    }
  });

  // ask for a first layout sized to the panel
  requestLayout();
})();
