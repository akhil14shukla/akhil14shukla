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

  function groupColor(group, groups) {
    if (!group) {
      return "transparent";
    }
    const i = groups.indexOf(group);
    const varName = GROUP_COLORS[i % GROUP_COLORS.length];
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

  function render(data, meta) {
    current = { data, meta };
    svg.textContent = "";
    const { nodes, edges, width, height, detachedFrom } = data;

    fileEl.textContent = meta.file ? `Glance Map · ${meta.file}` : "Glance Map";

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
      stateEl.textContent =
        "No methods found in this file.\nOpen a file with functions or methods to map it.";
      stateEl.style.display = "";
      svg.hidden = true;
      return;
    }
    if (!edges.length && meta.semantic) {
      stateEl.textContent = "";
      stateEl.style.display = "none";
    } else {
      stateEl.style.display = "none";
    }
    svg.hidden = false;

    svg.setAttribute("viewBox", `0 0 ${svg.clientWidth || width} ${svg.clientHeight || height}`);
    const root = el("g", { id: "root" }, svg);

    // build adjacency for tracing
    adj = new Map();
    nodes.forEach((n) => adj.set(n.id, new Set()));
    edges.forEach((e) => {
      if (adj.has(e.from) && adj.has(e.to)) {
        adj.get(e.from).add(e.to);
        adj.get(e.to).add(e.from);
      }
    });

    // divider for the unconnected section
    if (detachedFrom !== undefined) {
      el("line", {
        x1: 16, y1: detachedFrom, x2: width - 16, y2: detachedFrom,
        class: "divider",
      }, root);
      el("text", {
        x: 16, y: detachedFrom + 18, class: "divider-label",
      }, root).textContent = "no resolved calls";
    }

    // edges first so nodes sit above them
    const edgeLayer = el("g", {}, root);
    edges.forEach((e, i) => {
      if (!e.points.length) {
        return; // self-call, drawn as a badge on the node
      }
      const p = el("path", {
        d: pathFor(e.points),
        class: "edge" + (e.cross ? " cross" : ""),
        "stroke-width": Math.min(3.2, 1.4 + ((e.count || 1) - 1) * 0.5),
        "data-from": e.from,
        "data-to": e.to,
        "data-i": i,
      }, edgeLayer);
      p.setAttribute("marker-end", "");

      // arrowhead at the callee
      const last = e.points[e.points.length - 1];
      const prev = e.points[e.points.length - 2] || last;
      const ang = Math.atan2(last.y - prev.y, last.x - prev.x);
      const s = 5.5;
      el("path", {
        d: `M ${last.x} ${last.y} L ${last.x - s * Math.cos(ang - 0.5)} ${last.y - s * Math.sin(ang - 0.5)} L ${last.x - s * Math.cos(ang + 0.5)} ${last.y - s * Math.sin(ang + 0.5)} Z`,
        class: "arrow",
        "data-from": e.from,
        "data-to": e.to,
      }, edgeLayer);
    });

    const selfCalls = new Set(
      edges.filter((e) => !e.points.length).map((e) => e.from)
    );

    const groups = [...new Set(nodes.map((n) => n.group).filter(Boolean))].sort();

    // nodes
    const nodeLayer = el("g", {}, root);
    nodes.forEach((n) => {
      const cls = ["node"];
      if (n.external) cls.push("external");
      if (n.severity === 2) cls.push("err");
      else if (n.severity === 1) cls.push("warn");

      const g = el("g", {
        class: cls.join(" "),
        "data-id": n.id,
        tabindex: "0",
        role: "button",
      }, nodeLayer);

      const label = n.group ? `${n.group}.${n.name || n.label}` : n.label;
      el("title", {}, g).textContent =
        `${label}${n.lines ? ` — ${n.lines} lines` : ""}` +
        (n.external ? " (defined outside this file)" : "");

      el("rect", { x: n.x, y: n.y, width: n.w, height: n.h, rx: 6 }, g);

      if (n.group) {
        el("line", {
          x1: n.x + 1.5, y1: n.y + 7, x2: n.x + 1.5, y2: n.y + n.h - 7,
          class: "rail",
          stroke: groupColor(n.group, groups),
        }, g);
      }

      const hasSub = !!n.group || !!n.lines;
      el("text", {
        x: n.x + 12,
        y: hasSub ? n.y + 16 : n.y + n.h / 2,
      }, g).textContent = truncate(n.label, n.w) + (selfCalls.has(n.id) ? " ↻" : "");

      if (hasSub) {
        const bits = [];
        if (n.group) bits.push(n.group);
        if (n.lines) bits.push(`${n.lines}L`);
        el("text", {
          x: n.x + 12, y: n.y + 30, class: "sub",
        }, g).textContent = truncate(bits.join(" · "), n.w, 5.4);
      }

      g.addEventListener("click", () => {
        if (!n.external) {
          vscode.postMessage({ type: "reveal", id: n.id });
        }
      });
      g.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          if (!n.external) {
            vscode.postMessage({ type: "reveal", id: n.id });
          }
        }
      });
      g.addEventListener("mouseenter", () => trace(n.id));
      g.addEventListener("focus", () => trace(n.id));
      g.addEventListener("mouseleave", clearTrace);
      g.addEventListener("blur", clearTrace);
    });

    fit();
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
    svg.querySelectorAll(".edge, .arrow").forEach((p) => {
      const on =
        p.getAttribute("data-from") === id || p.getAttribute("data-to") === id;
      p.classList.toggle("hot", on);
      p.classList.toggle("dim", !on);
    });
  }

  function clearTrace() {
    svg.querySelectorAll(".node").forEach((g) => g.classList.remove("hot", "dim"));
    svg.querySelectorAll(".edge, .arrow").forEach((p) => p.classList.remove("hot", "dim"));
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
  extBox.addEventListener("change", () =>
    vscode.postMessage({
      type: "relayout",
      width: Math.max(520, stage.clientWidth - 40),
      showExternal: extBox.checked,
    })
  );

  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      vscode.postMessage({
        type: "relayout",
        width: Math.max(520, stage.clientWidth - 40),
        showExternal: extBox.checked,
      });
    }, 160);
  });

  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (msg.type === "loading") {
      stateEl.textContent = "Resolving calls…";
      stateEl.style.display = "";
      svg.hidden = true;
      return;
    }
    if (msg.type === "render") {
      extBox.checked = !!msg.meta.showExternal;
      render(msg.layout, msg.meta);
    }
  });

  // ask for a first layout sized to the panel
  vscode.postMessage({
    type: "relayout",
    width: Math.max(520, stage.clientWidth - 40),
    showExternal: false,
  });
})();
