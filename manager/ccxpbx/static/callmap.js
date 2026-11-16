// Live call map: extensions on a ring (or grid / ring-group clusters), outside numbers on the right,
// services on the left, one line per call. live.js calls CallMap.update() every 3 s; elements are kept
// by id so the line animations do not restart on every refresh. View options live in localStorage.
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const W = 1000, H = 720, CX = W / 2, CY = H / 2;
  const svg = document.getElementById("cm-svg");
  if (!svg) return;
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const GROUP_COLORS = ["#7C3AED", "#0EA5E9", "#DB2777", "#65A30D", "#CA8A04", "#0F766E", "#9333EA", "#EA580C"];
  const STATE_TEXT = { talk: "beszélget", ring: "kicseng", dial: "tárcsáz", hold: "tartva" };
  const NODE_STATE = { free: "Szabad", ring: "Csörög", busy: "Hívásban", hold: "Tartásban", off: "Offline" };

  // ------------------------------------------------------------------ options
  const DEFAULTS = { hideOffline: false, onlyActive: false, showNames: true, showDurations: true, showList: true,
                     layout: "ring", groupColors: true, me: "", confirmHangup: true, sound: false };
  const KEY = "ccx.callmap";
  let opts = { ...DEFAULTS };
  try { opts = { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch (_) { /* private mode */ }
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(opts)); } catch (_) { /* ignore */ } };

  const mk = (tag, attrs = {}, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  };
  const groupLayer = mk("g", { class: "cm-groups" }, svg);
  const edgeLayer = mk("g", { class: "cm-edges" }, svg);
  const labelLayer = mk("g", { class: "cm-labels" }, svg);
  const nodeLayer = mk("g", { class: "cm-nodes" }, svg);
  const nodeEls = new Map(), edgeEls = new Map();
  let data = null, edges = [], received = Date.now(), pos = new Map(), byId = new Map(), groupOf = new Map();
  let knownRings = null;

  const clock = (s) => {
    s = Math.max(0, Math.floor(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(r).padStart(2, "0");
  };
  const short = (t, n) => (t.length > n ? t.slice(0, n - 1) + "…" : t);

  // ------------------------------------------------------------------ layout
  function ringPositions(list, cx, cy, rx, ry, p) {
    const r = Math.max(18, Math.min(36, (2 * Math.PI * Math.min(rx, ry)) / Math.max(list.length, 1) / 2.8));
    list.forEach((n, i) => {
      const a = list.length === 1 ? -Math.PI / 2 : -Math.PI / 2 + (2 * Math.PI * i) / list.length;
      const rr = list.length === 1 ? 0 : 1;
      p.set(n.id, { x: cx + rx * rr * Math.cos(a), y: cy + ry * rr * Math.sin(a), a, r, cx, cy });
    });
  }

  function layout(exts, outs, svcs) {
    const p = new Map(), groups = [];
    if (opts.layout === "grid") {
      const cols = Math.max(1, Math.ceil(Math.sqrt(exts.length * 1.5)));
      const rows = Math.max(1, Math.ceil(exts.length / cols));
      const cw = 600 / cols, ch = 620 / rows;
      const r = Math.max(18, Math.min(36, Math.min(cw, ch) / 3.2));
      exts.forEach((n, i) => {
        const x = 200 + cw * (i % cols + 0.5), y = 50 + ch * (Math.floor(i / cols) + 0.5);
        p.set(n.id, { x, y, a: Math.PI / 2, r, cx: x, cy: y - 1 });
      });
    } else if (opts.layout === "groups") {
      const clusters = [];
      (data.groups || []).forEach((g, gi) => {
        const members = exts.filter((n) => groupOf.get(n.label) === g.num);
        if (members.length) clusters.push({ name: `${g.num} ${g.name}`, members, color: GROUP_COLORS[gi % GROUP_COLORS.length] });
      });
      const rest = exts.filter((n) => !groupOf.has(n.label));
      if (rest.length) clusters.push({ name: "Csoport nélkül", members: rest, color: "" });
      const cols = Math.max(1, Math.ceil(Math.sqrt(clusters.length)));
      const rows = Math.max(1, Math.ceil(clusters.length / cols));
      const cw = 620 / cols, ch = 640 / rows;
      clusters.forEach((c, i) => {
        const cx = 190 + cw * (i % cols + 0.5), cy = 50 + ch * (Math.floor(i / cols) + 0.5);
        const rad = Math.min(cw, ch) / 2 - 72;
        ringPositions(c.members, cx, cy + 10, Math.max(rad, 20), Math.max(rad, 20), p);
        groups.push({ ...c, x: cx, y: cy + 10, r: Math.max(rad, 20) + 62 });
      });
    } else {
      ringPositions(exts, CX, CY, 300, 265, p);
    }
    const column = (list, x) => list.forEach((n, i) => {
      const step = Math.min(110, (H - 80) / Math.max(list.length, 1));
      p.set(n.id, { x, y: CY + (i - (list.length - 1) / 2) * step, a: x > CX ? 0 : Math.PI, r: 24, box: true });
    });
    column(outs, W - 95);
    column(svcs, 95);
    return { p, groups };
  }

  function drawGroups(groups) {
    groupLayer.replaceChildren();
    if (opts.layout !== "groups") return;
    groups.forEach((g) => {
      mk("circle", { cx: g.x, cy: g.y, r: g.r, class: "cm-group", style: g.color ? `stroke:${g.color}` : "" }, groupLayer);
      const t = mk("text", { x: g.x, y: Math.min(H - 6, g.y + g.r + 22), "text-anchor": "middle", class: "cm-group-name",
                             style: g.color ? `fill:${g.color}` : "" }, groupLayer);
      t.textContent = short(g.name, 26);
    });
  }

  // ------------------------------------------------------------------ nodes
  function nodeEl(n) {
    let g = nodeEls.get(n.id);
    if (!g) {
      g = mk("g", { class: "cm-node " + n.kind, tabindex: n.kind === "ext" ? 0 : -1 }, nodeLayer);
      if (n.kind === "ext") {
        g.setAttribute("role", "button");
        g._halo = mk("circle", { class: "cm-halo" }, g);
        g._shape = mk("circle", {}, g);
        g._num = mk("text", { class: "cm-num", "text-anchor": "middle", "dominant-baseline": "central" }, g);
        g.addEventListener("click", (ev) => { ev.stopPropagation(); openMenu(n.id, g); });
        g.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openMenu(n.id, g); } });
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
    if (n.kind === "ext") {
      g.setAttribute("aria-label", `${n.label} ${n.sub}, ${NODE_STATE[n.state] || n.state}`);
      g._tip.textContent = `${n.label} ${n.sub} – ${NODE_STATE[n.state] || n.state}`;
      g._shape.setAttribute("cx", p.x); g._shape.setAttribute("cy", p.y); g._shape.setAttribute("r", p.r);
      const gi = (data.groups || []).findIndex((x) => x.num === groupOf.get(n.label));
      const halo = opts.groupColors && gi >= 0;
      g._halo.setAttribute("cx", p.x); g._halo.setAttribute("cy", p.y); g._halo.setAttribute("r", p.r + 6);
      g._halo.style.stroke = halo ? GROUP_COLORS[gi % GROUP_COLORS.length] : "transparent";
      g._num.setAttribute("x", p.x); g._num.setAttribute("y", p.y);
      g._num.setAttribute("font-size", Math.max(13, p.r * 0.58));
      g._num.textContent = n.label;
      const out = p.r + 10, ang = p.cx !== undefined && Math.hypot(p.x - p.cx, p.y - p.cy) > 1
        ? Math.atan2(p.y - p.cy, p.x - p.cx) : Math.PI / 2;
      const c = Math.cos(ang), s = Math.sin(ang);
      g._name.setAttribute("x", p.x + c * out);
      g._name.setAttribute("y", p.y + s * out + (s > 0.3 ? 12 : s < -0.3 ? -2 : 5));
      g._name.setAttribute("text-anchor", c > 0.3 ? "start" : c < -0.3 ? "end" : "middle");
      g._name.textContent = opts.showNames ? short(n.sub, 18) : "";
    } else {
      g._tip.textContent = `${n.label} ${n.sub || ""}`.trim();
      const w = 170, h = n.sub ? 52 : 38;
      g._shape.setAttribute("x", p.x - w / 2); g._shape.setAttribute("y", p.y - h / 2);
      g._shape.setAttribute("width", w); g._shape.setAttribute("height", h);
      g._num.setAttribute("x", p.x); g._num.setAttribute("y", p.y + (n.sub ? -4 : 6));
      g._num.textContent = short(n.label, 18);
      g._name.setAttribute("x", p.x); g._name.setAttribute("y", p.y + 17);
      g._name.setAttribute("text-anchor", "middle");
      g._name.textContent = n.sub ? short(n.sub, 22) : "";
    }
  }

  // ------------------------------------------------------------------ edges
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
      el.pill.style.display = opts.showDurations ? "" : "none";
      el.e = e;
    });
    for (const [key, el] of edgeEls) {
      if (!seen.has(key)) { el.path.remove(); el.pill.remove(); edgeEls.delete(key); }
    }
    tickClocks();
  }

  function tickClocks() {
    const elapsed = (Date.now() - received) / 1000;
    for (const el of edgeEls.values()) {
      el.txt.textContent = el.e.state === "hold" ? "⏸ " + clock(el.e.secs + elapsed) : clock(el.e.secs + elapsed);
    }
    document.querySelectorAll("[data-secs]").forEach((s) => { s.textContent = clock(+s.dataset.secs + elapsed); });
  }

  // ------------------------------------------------------------------ side list
  const nameOf = (id) => { const n = byId.get(id); return n ? `${n.label}${n.sub && n.kind === "ext" ? " " + n.sub : ""}` : "?"; };
  const extOf = (id) => (id && id.startsWith("ext:") ? id.slice(4) : "");

  function drawList() {
    const list = $("cm-calls");
    list.innerHTML = edges.map((e) => {
      const ext = extOf(e.from) || extOf(e.to);
      return `<li class="${e.state}"><span class="cm-who">${esc(nameOf(e.from))} → ${esc(e.to ? nameOf(e.to) : e.number || "…")}</span>
        <span class="cm-meta">${STATE_TEXT[e.state] || e.state} · <span class="mono" data-secs="${e.secs}">${clock(e.secs)}</span>
        ${ext ? `<button type="button" class="link cm-hang" data-ext="${esc(ext)}">Bontás</button>` : ""}</span></li>`;
    }).join("") || '<li class="muted">Most nincs folyamatban lévő hívás.</li>';
    const parts = [];
    if (data.talking) parts.push(`${data.talking} beszélget`);
    if (data.holding) parts.push(`${data.holding} tartva`);
    if (data.ringing) parts.push(`${data.ringing} csörög`);
    $("cm-count").textContent = parts.length ? `(${parts.join(", ")})` : "";
  }
  $("cm-calls").addEventListener("click", (ev) => {
    const b = ev.target.closest(".cm-hang");
    if (b) act("hangup", b.dataset.ext);
  });

  // ------------------------------------------------------------------ menu + actions
  const menu = $("cm-menu");
  function openMenu(id, g) {
    const n = byId.get(id);
    if (!n) return;
    const ext = n.label, involved = edges.some((e) => e.from === id || e.to === id);
    const me = opts.me && opts.me !== ext ? opts.me : "";
    const items = [];
    items.push(`<div class="cm-menu-head"><b>${esc(ext)}</b> ${esc(n.sub)}<small>${esc(NODE_STATE[n.state] || n.state)}</small></div>`);
    const btn = (action, label, hint = "", disabled = false) =>
      `<button type="button" role="menuitem" data-act="${action}"${disabled ? " disabled" : ""}>${esc(label)}${hint ? `<small>${esc(hint)}</small>` : ""}</button>`;
    if (opts.me === ext) {
      items.push('<p class="muted small">Ez a saját melléked.</p>');
    } else {
      const need = me ? `a ${me} telefonodról` : "előbb add meg a saját melléked a Beállításokban";
      items.push(btn("call", "Hívás", need, !me || n.state === "off"));
      items.push(btn("intercom", "Intercom", me ? "kihangosítva bekapcsol nála" : need, !me || n.state === "off"));
    }
    if (involved) {
      items.push(btn("hangup", "Hívás bontása"));
      if (data.spy && opts.me !== ext) {
        items.push(btn("listen", "Belehallgatás", me ? "csak te hallod őket" : need, !me));
        items.push(btn("whisper", "Súgás", "csak a mellék hall téged", !me));
        items.push(btn("barge", "Beszállás", "mindenki hall mindenkit", !me));
      }
    }
    items.push(`<a role="menuitem" href="/extensions/${encodeURIComponent(ext)}">Mellék beállításai</a>`);
    if (opts.me !== ext) items.push(btn("setme", "Ez az én mellékem"));
    menu.innerHTML = items.join("");
    menu.dataset.ext = ext;
    menu.hidden = false;
    // place it next to the node
    const stage = $("cm-stage").getBoundingClientRect(), box = g._shape.getBoundingClientRect();
    let left = box.right - stage.left + 8, top = box.top - stage.top;
    if (left + 240 > stage.width) left = box.left - stage.left - 248;
    menu.style.left = Math.max(8, left) + "px";
    menu.style.top = Math.max(8, Math.min(top, stage.height - menu.offsetHeight - 8)) + "px";
    const first = menu.querySelector("button:not([disabled]), a");
    if (first) first.focus();
  }
  const closeMenu = () => { menu.hidden = true; };
  menu.addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-act]");
    if (!b) return;
    const action = b.dataset.act, ext = menu.dataset.ext;
    closeMenu();
    if (action === "setme") { opts.me = ext; save(); syncForm(); toast(`A saját melléked: ${ext}`); render(); return; }
    act(action, ext);
  });
  document.addEventListener("click", (ev) => { if (!menu.hidden && !menu.contains(ev.target)) closeMenu(); });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") { closeMenu(); if (wall) setWall(false); } });

  const CONFIRM = {
    hangup: (x) => ({ title: "Hívás bontása", ok: "Bontás", danger: true,
                      text: `A(z) ${x} mellék hívása azonnal megszakad.` }),
    barge: (x) => ({ title: "Beszállás a hívásba", ok: "Beszállás",
                     text: `Beszállsz a(z) ${x} hívásába. Mindkét fél hallani fog téged.` }),
  };
  async function act(action, ext) {
    if (action === "hangup" && opts.confirmHangup || action === "barge") {
      const c = CONFIRM[action](ext);
      if (!(await ccxConfirm(c.text, c))) return;
    }
    try {
      const r = await fetch("/callmap/action", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
                                                 body: JSON.stringify({ action, target: ext, me: opts.me }) });
      if (r.redirected || r.status === 401) { location.href = "/login"; return; }
      const d = await r.json();
      toast(d.message || (d.ok ? "Kész." : "Nem sikerült."), !d.ok);
    } catch (_) {
      toast("A szerver nem válaszolt.", true);
    }
  }

  let toastTimer = 0;
  function toast(msg, err = false) {
    const t = $("cm-toast");
    t.textContent = msg;
    t.className = "cm-toast" + (err ? " err" : "");
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 5000);
  }

  // ------------------------------------------------------------------ sound
  let audio = null;
  function beep() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.25].forEach((t) => {
        const o = audio.createOscillator(), g = audio.createGain();
        o.frequency.value = 880; o.connect(g); g.connect(audio.destination);
        g.gain.setValueAtTime(0.0001, audio.currentTime + t);
        g.gain.exponentialRampToValueAtTime(0.25, audio.currentTime + t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + t + 0.18);
        o.start(audio.currentTime + t); o.stop(audio.currentTime + t + 0.2);
      });
    } catch (_) { /* no audio */ }
  }
  function checkIncoming() {
    const rings = new Set(edges.filter((e) => e.state === "ring" && e.from.startsWith("out:")).map((e) => e.from + ">" + e.to));
    if (knownRings && opts.sound && [...rings].some((k) => !knownRings.has(k))) beep();
    knownRings = rings;
  }

  // ------------------------------------------------------------------ wall display
  let wall = false;
  function setWall(on) {
    wall = on;
    document.body.classList.toggle("cm-wall-mode", on);
    try {
      if (on && !document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {});
      if (!on && document.fullscreenElement) document.exitFullscreen().catch(() => {});
    } catch (_) { /* no fullscreen API */ }
    const url = new URL(location.href);
    on ? url.searchParams.set("wall", "1") : url.searchParams.delete("wall");
    history.replaceState(null, "", url);
    if (on && opts.sound && audio === null) beep();   // unlocks audio with this click
  }
  $("cm-wall-btn").addEventListener("click", () => setWall(true));
  $("cm-wall-exit").addEventListener("click", () => setWall(false));
  document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement && wall) setWall(false); });

  // ------------------------------------------------------------------ settings panel
  const panel = $("cm-settings"), panelBtn = $("cm-settings-btn");
  panelBtn.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    panelBtn.setAttribute("aria-expanded", String(!panel.hidden));
  });
  function syncForm() {
    panel.querySelectorAll("[data-opt]").forEach((inp) => {
      const k = inp.dataset.opt;
      if (inp.type === "checkbox") inp.checked = !!opts[k];
      else if (inp.type === "radio") inp.checked = inp.value === opts[k];
      else inp.value = opts[k];
    });
  }
  panel.addEventListener("change", (ev) => {
    const inp = ev.target.closest("[data-opt]");
    if (!inp) return;
    const k = inp.dataset.opt;
    opts[k] = inp.type === "checkbox" ? inp.checked : inp.value;
    if (k === "sound" && inp.checked) beep();   // test tone, and unlocks audio
    save();
    render();
  });
  function fillMe(d) {
    const sel = $("cm-me"), exts = d.nodes.filter((n) => n.kind === "ext");
    const want = exts.map((n) => n.label).join(",");
    if (sel.dataset.list === want) return;
    sel.dataset.list = want;
    sel.innerHTML = '<option value="">– válassz –</option>' +
      exts.map((n) => `<option value="${esc(n.label)}">${esc(n.label)} ${esc(n.sub)}</option>`).join("");
    sel.value = opts.me;
  }

  // ------------------------------------------------------------------ render
  function render() {
    if (!data) return;
    edges = data.edges || [];
    groupOf = new Map();
    (data.groups || []).forEach((g) => g.members.forEach((m) => { if (!groupOf.has(m)) groupOf.set(m, g.num); }));
    const involved = new Set(edges.flatMap((e) => [e.from, e.to]).filter(Boolean));
    const all = data.nodes;
    let exts = all.filter((n) => n.kind === "ext");
    if (opts.onlyActive) exts = exts.filter((n) => involved.has(n.id) || ["ring", "busy", "hold"].includes(n.state));
    if (opts.hideOffline) exts = exts.filter((n) => n.state !== "off" || involved.has(n.id));
    const outs = all.filter((n) => n.kind === "out"), svcs = all.filter((n) => n.kind === "svc");
    const visible = [...exts, ...outs, ...svcs];
    byId = new Map(all.map((n) => [n.id, n]));
    const { p, groups } = layout(exts, outs, svcs);
    pos = p;
    const keep = new Set(visible.map((n) => n.id));
    for (const [id, g] of nodeEls) {
      if (!keep.has(id)) { g.remove(); nodeEls.delete(id); }
    }
    drawGroups(groups);
    visible.forEach((n) => drawNode(n, pos.get(n.id)));
    drawEdges();
    drawList();
    $("cm-wrap").classList.toggle("no-list", !opts.showList);
    const empty = $("cm-empty");
    const hasExt = all.some((n) => n.kind === "ext");
    empty.hidden = exts.length > 0;
    empty.textContent = !hasExt ? "Még nincs mellék. Vegyél fel mellékeket, és itt látszanak."
      : "Most senki nincs hívásban (a beállításokban a „Csak a hívásban lévők” szűrő be van kapcsolva).";
    if (!menu.hidden && !byId.has("ext:" + menu.dataset.ext)) closeMenu();
  }

  function update(d) {
    if (!d) return;
    data = d;
    received = Date.now();
    fillMe(d);
    render();
    checkIncoming();
  }

  window.CallMap = { update };
  syncForm();
  try { update(JSON.parse($("cm-data").textContent)); } catch (_) { /* first refresh fills it */ }
  if (new URLSearchParams(location.search).get("wall") === "1") {
    document.body.classList.add("cm-wall-mode");   // fullscreen needs a click, the layout does not
    wall = true;
  }
  setInterval(tickClocks, 1000);
})();
