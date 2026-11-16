// Live call map: extensions on a ring, outside numbers on the right, services on the left,
// one line per call. live.js calls CallMap.update() every 3 s; elements are kept by id so the
// line animations do not restart on every refresh.
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const W = 1000, H = 720, CX = W / 2, CY = H / 2, RX = 300, RY = 265;
  const svg = document.getElementById("cm-svg");
  if (!svg) return;

  const mk = (tag, attrs = {}, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  };
  const edgeLayer = mk("g", { class: "cm-edges" }, svg);
  const labelLayer = mk("g", { class: "cm-labels" }, svg);
  const nodeLayer = mk("g", { class: "cm-nodes" }, svg);
  const nodeEls = new Map(), edgeEls = new Map();
  let edges = [], received = Date.now(), pos = new Map();

  const STATE_TEXT = { talk: "beszélget", ring: "kicseng", dial: "tárcsáz" };
  const clock = (s) => {
    s = Math.max(0, Math.floor(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(r).padStart(2, "0");
  };

  function layout(nodes) {
    const exts = nodes.filter((n) => n.kind === "ext");
    const outs = nodes.filter((n) => n.kind === "out");
    const svcs = nodes.filter((n) => n.kind === "svc");
    const p = new Map();
    const r = Math.max(18, Math.min(36, (2 * Math.PI * RX) / Math.max(exts.length, 1) / 2.8));
    exts.forEach((n, i) => {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / exts.length;
      p.set(n.id, { x: CX + RX * Math.cos(a), y: CY + RY * Math.sin(a), a, r });
    });
    const column = (list, x) => list.forEach((n, i) => {
      const step = Math.min(110, (H - 80) / Math.max(list.length, 1));
      p.set(n.id, { x, y: CY + (i - (list.length - 1) / 2) * step, a: x > CX ? 0 : Math.PI, r: 24, box: true });
    });
    column(outs, W - 95);
    column(svcs, 95);
    return p;
  }

  function nodeEl(n) {
    let g = nodeEls.get(n.id);
    if (!g) {
      const link = n.kind === "ext" ? mk("a", { href: "/extensions/" + encodeURIComponent(n.label) }, nodeLayer) : null;
      g = mk("g", { class: "cm-node " + n.kind }, link || nodeLayer);
      g._wrap = link || g;
      if (n.kind === "ext") {
        g._shape = mk("circle", {}, g);
        g._num = mk("text", { class: "cm-num", "text-anchor": "middle", "dominant-baseline": "central" }, g);
      } else {
        g._shape = mk("rect", { rx: 10 }, g);
        g._num = mk("text", { class: "cm-num", "text-anchor": "middle" }, g);
      }
      g._name = mk("text", { class: "cm-name" }, g);
      g._tip = mk("title", {}, g);
      nodeEls.set(n.id, g);
    }
    return g;
  }

  function drawNode(n, p) {
    const g = nodeEl(n);
    g.setAttribute("class", `cm-node ${n.kind} ${n.state}`);
    g._tip.textContent = `${n.label} ${n.sub || ""}`.trim();
    if (n.kind === "ext") {
      g._shape.setAttribute("cx", p.x); g._shape.setAttribute("cy", p.y); g._shape.setAttribute("r", p.r);
      g._num.setAttribute("x", p.x); g._num.setAttribute("y", p.y);
      g._num.setAttribute("font-size", Math.max(13, p.r * 0.58));
      g._num.textContent = n.label;
      // name outside the ring, pointing away from the centre
      const out = p.r + 8, c = Math.cos(p.a), s = Math.sin(p.a);
      g._name.setAttribute("x", p.x + c * out);
      g._name.setAttribute("y", p.y + s * out + (s > 0.3 ? 10 : s < -0.3 ? -2 : 4));
      g._name.setAttribute("text-anchor", c > 0.3 ? "start" : c < -0.3 ? "end" : "middle");
      g._name.textContent = n.sub.length > 18 ? n.sub.slice(0, 17) + "…" : n.sub;
    } else {
      const w = 170, h = n.sub ? 52 : 38;
      g._shape.setAttribute("x", p.x - w / 2); g._shape.setAttribute("y", p.y - h / 2);
      g._shape.setAttribute("width", w); g._shape.setAttribute("height", h);
      g._num.setAttribute("x", p.x); g._num.setAttribute("y", p.y + (n.sub ? -4 : 6));
      g._num.textContent = n.label.length > 18 ? n.label.slice(0, 17) + "…" : n.label;
      g._name.setAttribute("x", p.x); g._name.setAttribute("y", p.y + 17);
      g._name.setAttribute("text-anchor", "middle");
      g._name.textContent = n.sub ? (n.sub.length > 22 ? n.sub.slice(0, 21) + "…" : n.sub) : "";
    }
  }

  function edgePath(a, b) {
    // a gentle curve bent towards the centre so lines across the ring do not overlap the nodes
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    const k = 0.35, qx = mx + (CX - mx) * k, qy = my + (CY - my) * k;
    const trim = (p, q, r) => { const dx = q.x - p.x, dy = q.y - p.y, d = Math.hypot(dx, dy) || 1;
      return { x: p.x + (dx / d) * r, y: p.y + (dy / d) * r }; };
    const s = trim(a, { x: qx, y: qy }, a.box ? 0 : a.r + 3), e = trim(b, { x: qx, y: qy }, b.box ? 0 : b.r + 3);
    return { d: `M${s.x.toFixed(1)},${s.y.toFixed(1)} Q${qx.toFixed(1)},${qy.toFixed(1)} ${e.x.toFixed(1)},${e.y.toFixed(1)}`,
             lx: 0.25 * s.x + 0.5 * qx + 0.25 * e.x, ly: 0.25 * s.y + 0.5 * qy + 0.25 * e.y };
  }

  function drawEdges() {
    const seen = new Set();
    edges.forEach((e) => {
      if (!e.to) return;
      const a = pos.get(e.from), b = pos.get(e.to);
      if (!a || !b) return;
      const key = e.from + ">" + e.to;
      seen.add(key);
      let el = edgeEls.get(key);
      if (!el) {
        el = { path: mk("path", {}, edgeLayer), pill: mk("g", { class: "cm-pill" }, labelLayer) };
        el.bg = mk("rect", { rx: 11, height: 22, width: 60 }, el.pill);
        el.txt = mk("text", { "text-anchor": "middle", "dominant-baseline": "central" }, el.pill);
        edgeEls.set(key, el);
      }
      const g = edgePath(a, b);
      el.path.setAttribute("d", g.d);
      el.path.setAttribute("class", "cm-edge " + e.state);
      el.bg.setAttribute("x", g.lx - 30); el.bg.setAttribute("y", g.ly - 11);
      el.txt.setAttribute("x", g.lx); el.txt.setAttribute("y", g.ly);
      el.pill.setAttribute("class", "cm-pill " + e.state);
      el.e = e;
    });
    for (const [key, el] of edgeEls) {
      if (!seen.has(key)) { el.path.remove(); el.pill.remove(); edgeEls.delete(key); }
    }
    tickClocks();
  }

  function tickClocks() {
    const elapsed = (Date.now() - received) / 1000;
    for (const el of edgeEls.values()) el.txt.textContent = clock(el.e.secs + elapsed);
    document.querySelectorAll("[data-secs]").forEach((s) => { s.textContent = clock(+s.dataset.secs + elapsed); });
  }

  function drawList(d, byId) {
    const list = document.getElementById("cm-calls");
    const name = (id) => { const n = byId.get(id); return n ? `${n.label}${n.sub && n.kind === "ext" ? " " + n.sub : ""}` : "?"; };
    const html = edges.map((e) => `<li class="${e.state}"><span class="cm-who">${esc(name(e.from))} → ${esc(e.to ? name(e.to) : e.number || "…")}</span>
      <span class="cm-meta">${STATE_TEXT[e.state] || e.state} · <span class="mono" data-secs="${e.secs}">${clock(e.secs)}</span></span></li>`).join("");
    list.innerHTML = html || '<li class="muted">Most nincs folyamatban lévő hívás.</li>';
    document.getElementById("cm-count").textContent = edges.length ? `(${d.talking} beszélget, ${d.ringing} csörög)` : "";
  }

  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function update(d) {
    if (!d) return;
    received = Date.now();
    edges = d.edges || [];
    pos = layout(d.nodes);
    const byId = new Map(d.nodes.map((n) => [n.id, n]));
    for (const [id, g] of nodeEls) {
      if (!byId.has(id)) { g._wrap.remove(); nodeEls.delete(id); }
    }
    d.nodes.forEach((n) => drawNode(n, pos.get(n.id)));
    drawEdges();
    drawList(d, byId);
    document.getElementById("cm-empty").hidden = d.nodes.some((n) => n.kind === "ext");
  }

  window.CallMap = { update };
  try { update(JSON.parse(document.getElementById("cm-data").textContent)); } catch (_) { /* first refresh fills it */ }
  setInterval(tickClocks, 1000);
})();
