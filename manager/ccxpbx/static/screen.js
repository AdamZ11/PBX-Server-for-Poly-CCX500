/* CCXPBX: WYSIWYG editor for the CCX500 home screen. The phone itself is the editor:
   tap an icon to hide/show it, tap or drag a key on the dock, tap + to add one. */
(function () {
  "use strict";
  const data = JSON.parse(document.getElementById("editor-data").textContent);
  const TYPES = JSON.parse(document.getElementById("key-types").textContent);
  const SHORT = { line: "Vonal", blf: "BLF", park: "Park", speeddial: "Gyorshívó", unassigned: "Üres" };
  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k === "html") n.innerHTML = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) n.setAttribute(k, v === true ? "" : v);
    }
    kids.flat().forEach((c) => c != null && n.append(c));
    return n;
  };

  // ---------------------------------------------------------------- icons (white glyphs, 24x24)
  const P = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="${d}"/></svg>`;
  const PHONE = "M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1A17 17 0 0 1 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.2.2 2.4.6 3.6.1.3 0 .7-.2 1z";
  const GLYPH = {
    newCall: P(PHONE),
    redial: P(PHONE + "M15 3a6 6 0 1 1-4.2 10.2l1.4-1.4A4 4 0 1 0 15 5v2l-3-3 3-3z"),
    messages: P("M6.5 7a5 5 0 0 1 3.9 8.1h3.2A5 5 0 1 1 17.5 17h-11a5 5 0 0 1 0-10zm0 2a3 3 0 1 0 0 6 3 3 0 0 0 0-6zm11 0a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"),
    contacts: P("M5 3h11a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5zm5.5 5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM6.5 17h8c0-2-1.8-3-4-3s-4 1-4 3zM19 6h2v3h-2zm0 4.5h2v3h-2zm0 4.5h2v3h-2z"),
    doNotDisturb: P("M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20zm-5 8.5v3h10v-3z"),
    settings: P("M19.4 13a7.6 7.6 0 0 0 0-2l2.1-1.6-2-3.5-2.5 1a7.4 7.4 0 0 0-1.7-1L15 3.3h-4L10.6 6a7.4 7.4 0 0 0-1.7 1l-2.5-1-2 3.5L6.6 11a7.6 7.6 0 0 0 0 2l-2.1 1.6 2 3.5 2.5-1c.5.4 1.1.7 1.7 1l.4 2.6h4l.4-2.6c.6-.3 1.2-.6 1.7-1l2.5 1 2-3.5zM12 15.5a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7z"),
    forward: P(PHONE + "M14 3h3V0l5 4.5L17 9V6h-3z"),
    directories: P("M6 2h12a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm1 4v2h10V6zm0 4v2h10v-2zm0 4v2h6v-2z"),
    application: P("M4 4h6v6H4zm10 0h6v6h-6zM4 14h6v6H4zm10 0h6v6h-6z"),
    bluetooth: P("M11 2h1l6 5-4.6 5 4.6 5-6 5h-1v-7.6L6.7 18.7 5.3 17.3 10.6 12 5.3 6.7l1.4-1.4L11 9.6zm2 3.4v4.2l2.4-2.1zm0 9v4.2l2.4-2.1z"),
    paging: P("M8 2h2v3h6a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zm4 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"),
    recentCalls: P("M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20zm-1 5v6l5 3 1-1.6-4-2.4V7z"),
    line: P(PHONE),
    blf: P("M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8zm0 10c4.4 0 8 2 8 4.5V20H4v-1.5C4 16 7.6 14 12 14z"),
    park: '<span class="ccx-p">P</span>',
    speeddial: P("M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8zm0 10c4.4 0 8 2 8 4.5V20H4v-1.5C4 16 7.6 14 12 14z"),
    unassigned: "",
    plus: P("M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z"),
  };

  // ---------------------------------------------------------------- state
  let keys = data.keys.map((k) => ({ type: k.type, value: k.value || "", label: k.label || "" }));
  let wallpaper = data.wallpaper;
  const hidden = new Set(data.homeHidden);
  let mode = "edit";
  let selected = null;          // null | {key: index} | {add: true}
  let page = 0;                 // 0 = home (icons + dock), 1 = list of all keys (swipe left on the phone)
  let states = {};
  let dirty = false;
  const extName = Object.fromEntries(data.exts.map((e) => [e.ext, e.name]));
  const ownExts = new Set(data.lines.map((l) => l.ext));
  const icons = data.homeIcons.filter((i) => (i.key !== "application" || data.microbrowser) && (i.key !== "paging" || data.paging));
  const toggleable = icons.filter((i) => !i.fixed);
  // Applications (the CCXPBX page) is also reachable from the ☰ menu, so it neither counts nor gets hidden automatically.
  // Bluetooth / Paging only fill free places, so they do not count either.
  const counted = (i) => i.key !== "application" && !i.fill;
  const visibleCount = () => icons.filter((i) => counted(i) && !hidden.has(i.key)).length;
  // The phone shows six icons at most; anything beyond the first six would never appear, so it starts hidden.
  (function limitIcons() {
    let shown = 0;
    icons.filter(counted).forEach((i) => { if (!hidden.has(i.key)) { shown++; if (shown > data.iconsOnScreen && !i.fixed) hidden.add(i.key); } });
  })();

  function touch() { dirty = true; $("dirty").hidden = false; }

  function lineOf(k) { return data.lines.find((l) => String(l.idx) === String(k.value)) || data.lines[0]; }
  function keyText(k) {
    if (k.type === "line") { const l = lineOf(k); return l ? `${l.ext} ${l.name}` : "Vonal"; }
    if (k.type === "blf") return k.label || extName[k.value] || k.value || "BLF";
    if (k.type === "park") return k.label || "Park";
    if (k.type === "speeddial") return k.label || extName[k.value] || k.value || "Gyorshívó";
    return "";
  }
  function keySub(k) {
    if (k.type === "line") { const l = lineOf(k); return l ? l.ext : ""; }
    if (k.type === "blf") return data.parkSlots.includes(k.value) ? `Park ${k.value}` : k.value;
    if (k.type === "park") return data.parkExt;
    if (k.type === "speeddial") return k.value;
    return "";
  }
  function keyState(k) {
    if (k.type === "blf") return data.parkSlots.includes(k.value) ? "park" : (states[k.value] || "off");
    if (k.type === "line") { const l = lineOf(k); return l ? (states[l.ext] || "off") : "off"; }
    return "";
  }
  function defaultValue(type) {
    if (type === "line") return "1";
    if (type === "blf") {
      const used = new Set(keys.filter((k) => k.type === "blf").map((k) => k.value));
      const free = data.exts.find((e) => !ownExts.has(e.ext) && !used.has(e.ext));
      return free ? free.ext : (data.exts[0] ? data.exts[0].ext : "");
    }
    return "";
  }
  // With an empty list the phone shows one key per reg.N.lineKeys
  function autoKeys() {
    const auto = [];
    data.lines.forEach((l) => { for (let n = 0; n < (l.line_keys || 1); n++) auto.push({ type: "line", value: String(l.idx), label: "" }); });
    return auto;
  }
  function materialize() { if (!keys.length) keys = autoKeys(); }

  // ---------------------------------------------------------------- the phone screen
  // Laid out after PolyOS 9.5.1 on a CCX500: page 1 = clock, six app icons, page dots and two keys at the
  // bottom (first left, second right, "›" when there are more); page 2 = the clock and every key as a list.
  function keyButton(k, i, cls, editing, kids) {
    const st = keyState(k);
    const sel = selected && selected.key === i && keys.length;
    return el("button", {
      type: "button", class: `${cls} t-${k.type} st-${st || "none"}${sel ? " sel" : ""}`, "data-i": i,
      title: `${i + 1}. gomb · ${TYPES[k.type] || ""}${editing ? " · húzd az áthelyezéshez" : ""}`,
      onpointerdown: (e) => { if (editing) startDrag(e, i); },
      onclick: () => { if (!editing || justDragged) return; materialize(); selected = { key: i }; render(); },
    }, kids);
  }
  function keyIcon(k) {
    return el("span", { class: "ccx-circle", html: GLYPH[k.type] || "" }, k.type === "line" && keyState(k) !== "off" ? el("i", { class: "ccx-reg" }) : null);
  }
  function addButton(cls) {
    return el("button", { type: "button", class: `${cls} add${selected && selected.add ? " sel" : ""}`, title: "Új gomb",
      onclick: () => { selected = { add: true }; render(); } },
      el("span", { class: "ccx-circle", html: GLYPH.plus }), el("span", { class: "ccx-cap" }, el("b", { text: "Új gomb" })));
  }

  function renderScreen() {
    const wp = wallpaper === "" ? data.siteWallpaper : (wallpaper === "none" ? "" : wallpaper);
    $("pv-screen").style.backgroundImage = wp ? `url("/wallpapers/${encodeURIComponent(wp)}")` : "none";
    const editing = mode === "edit";
    document.querySelector(".ccx-device").classList.toggle("editing", editing);
    const body = $("pv-body");
    body.replaceChildren();
    body.className = `ccx-body page-${page}`;
    const list = keys.length ? keys : autoKeys();

    if (page === 0) {
      // app icons: the first six visible ones, exactly what the phone shows
      const shown = icons.filter((i) => !hidden.has(i.key)).slice(0, data.iconsOnScreen);
      const apps = el("div", { class: "ccx-apps" });
      shown.forEach((ic) => apps.append(el("button", {
        type: "button", class: `ccx-app${ic.fixed ? " fixed" : ""}`,
        title: editing ? (ic.fixed ? `${ic.desc}: ezt a telefon mindig mutatja` : `${ic.desc}: koppints az elrejtéshez`) : ic.desc,
        onclick: (e) => {
          if (!editing || e.currentTarget.dataset.moved) return;
          if (ic.fixed) { toast(`A ${ic.label} ikont a telefon mindig mutatja, nem rejthető el.`); return; }
          hidden.add(ic.key); touch(); render();
          toast(`${ic.label} elrejtve. Visszahozni jobb oldalt, az ikonok listájában tudod.`);
        },
        onpointerdown: (e) => { const btn = e.currentTarget, x = e.clientX, y = e.clientY; delete btn.dataset.moved;
          const mv = (ev) => { if (Math.hypot(ev.clientX - x, ev.clientY - y) > 10 && !btn.dataset.moved) { btn.dataset.moved = "1";
            toast("Az ikonok sorrendjét a telefon szoftvere rögzíti, ezért nem húzhatók. Koppintással elrejtheted őket."); } };
          window.addEventListener("pointermove", mv);
          window.addEventListener("pointerup", () => window.removeEventListener("pointermove", mv), { once: true }); },
      }, el("span", { class: "ccx-circle", html: GLYPH[ic.key] }), el("span", { class: "ccx-cap", text: ic.label }))));
      body.append(apps, pageDots());

      // bottom keys: first on the left, second on the right, "›" when there are more
      const dock = el("div", { class: "ccx-dock" });
      const slot = (n) => (list[n] ? keyButton(list[n], n, "ccx-key", editing, [keyIcon(list[n]),
        el("span", { class: "ccx-cap" }, el("b", { text: keyText(list[n]) }), el("small", { text: keySub(list[n]) }))]) : el("span"));
      dock.append(slot(0), editing && keys.length < data.maxKeys ? addButton("ccx-key") : el("span"), slot(1));
      if (list.length > 2) dock.append(el("button", { type: "button", class: "ccx-more", title: "Többi gomb", text: "›", onclick: () => { page = 1; renderScreen(); } }));
      body.append(dock);
    } else {
      const rows = el("div", { class: "ccx-list" });
      list.forEach((k, i) => rows.append(keyButton(k, i, "ccx-key ccx-row", editing, [keyIcon(k),
        el("span", { class: "ccx-cap" }, el("b", { text: keyText(k) || TYPES[k.type] }), el("small", { text: keySub(k) })),
        k.type === "blf" || k.type === "speeddial" ? el("span", { class: "ccx-info", text: "i" }) : null])));
      if (editing && keys.length < data.maxKeys) rows.append(addButton("ccx-key ccx-row"));
      if (!list.length && !editing) rows.append(el("p", { class: "ccx-empty", text: "Nincs gomb" }));
      body.append(rows, pageDots());
    }

    const hiddenCount = toggleable.filter((i) => hidden.has(i.key)).length;
    $("pv-note").textContent = editing
      ? `Koppints egy ikonra az elrejtéshez, egy gombra a szerkesztéshez, húzd a gombokat az átrendezéshez. A pöttyökkel válthatsz a gomblistára.${hiddenCount ? ` Rejtett ikon: ${hiddenCount}.` : ""}`
      : (keys.length ? `${keys.length} gomb · a keretek a mellékek élő állapotát mutatják` : "Automatikus kiosztás: a telefon a vonalgombokat mutatja.");
  }

  function pageDots() {
    const box = el("div", { class: "ccx-dots" });
    [0, 1].forEach((p) => box.append(el("button", { type: "button", class: p === page ? "on" : "", "aria-label": p ? "Gomblista" : "Kezdőlap",
      onclick: () => { page = p; renderScreen(); } })));
    return box;
  }

  // Drag a key over another one to move it there; works with mouse, pen and touch.
  let justDragged = false;
  function startDrag(e, from) {
    const src = e.currentTarget, x0 = e.clientX, y0 = e.clientY;
    let ghost = null, target = null;
    try { src.setPointerCapture(e.pointerId); } catch (_) { /* synthetic events */ }
    const move = (ev) => {
      if (!ghost) {
        if (Math.hypot(ev.clientX - x0, ev.clientY - y0) < 6) return;
        const r = src.getBoundingClientRect();
        ghost = src.cloneNode(true);
        ghost.classList.add("ccx-ghost");
        ghost.style.width = `${r.width}px`;
        ghost.dataset.dx = String(x0 - r.left); ghost.dataset.dy = String(y0 - r.top);
        $("pv-screen").append(ghost);
        src.classList.add("dragging");
      }
      const scr = $("pv-screen").getBoundingClientRect();
      ghost.style.left = `${ev.clientX - scr.left - +ghost.dataset.dx}px`;
      ghost.style.top = `${ev.clientY - scr.top - +ghost.dataset.dy}px`;
      ghost.hidden = true;
      const under = document.elementFromPoint(ev.clientX, ev.clientY);
      ghost.hidden = false;
      const t = under && under.closest(".ccx-key[data-i]");
      if (target && target !== t) target.classList.remove("over");
      target = t && t !== src ? t : null;
      if (target) target.classList.add("over");
    };
    const up = () => {
      src.removeEventListener("pointermove", move);
      src.removeEventListener("pointerup", up);
      src.removeEventListener("pointercancel", up);
      if (!ghost) return;
      ghost.remove();
      src.classList.remove("dragging");
      justDragged = true;
      setTimeout(() => { justDragged = false; }, 0);
      if (!target) return;
      const to = +target.dataset.i;
      materialize();
      const [m] = keys.splice(from, 1); keys.splice(to, 0, m);
      selected = { key: to }; touch(); render();
    };
    src.addEventListener("pointermove", move);
    src.addEventListener("pointerup", up);
    src.addEventListener("pointercancel", up);
  }

  let toastTimer = 0;
  function toast(text) {
    const t = $("pv-toast");
    t.textContent = text; t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
  }

  function tick() {
    const d = new Date();
    const h = d.getHours(), m = String(d.getMinutes()).padStart(2, "0");
    $("pv-time").textContent = data.clock24 ? `${h}:${m}` : `${h % 12 || 12}:${m} ${h < 12 ? "AM" : "PM"}`;
    $("pv-date").textContent = d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  }

  // ---------------------------------------------------------------- inspector beside the phone
  function renderInspector() {
    const box = $("inspector");
    box.replaceChildren();
    if (selected && selected.add) return inspectAdd(box);
    if (selected && selected.key != null && keys[selected.key]) return inspectKey(box, selected.key);
    inspectScreen(box);
  }

  function inspectAdd(box) {
    box.append(el("h2", { text: "Új gomb" }), el("p", { class: "muted small", text: "Milyen gomb legyen? A dokk végére kerül, utána áthúzhatod." }));
    const grid = el("div", { class: "type-grid" });
    Object.keys(TYPES).forEach((t) => grid.append(el("button", { type: "button", class: "type-btn",
      onclick: () => { materialize(); keys.push({ type: t, value: defaultValue(t), label: t === "park" ? "Park" : "" });
        selected = { key: keys.length - 1 }; if (keys.length > 2) page = 1; touch(); render(); focusInspector(); } },
      el("span", { class: "ccx-circle mini", html: GLYPH[t] || "" }), el("b", { text: SHORT[t] }), el("small", { text: TYPES[t] }))));
    box.append(grid, el("div", { class: "row" }, el("button", { type: "button", class: "secondary small", text: "Mégse", onclick: () => { selected = null; render(); } })));
  }

  function inspectKey(box, i) {
    const k = keys[i];
    const rerender = () => { touch(); renderScreen(); };
    box.append(el("div", { class: "insp-head" }, el("h2", { text: `${i + 1}. gomb` }),
      el("button", { type: "button", class: "secondary small", text: "Kész", onclick: () => { selected = null; render(); } })));

    const typeRow = el("div", { class: "seg" });
    Object.keys(TYPES).forEach((t) => typeRow.append(el("button", { type: "button", class: t === k.type ? "on" : "", title: TYPES[t], text: SHORT[t],
      onclick: () => { k.type = t; k.value = defaultValue(t); touch(); render(); } })));
    box.append(el("label", { text: "Típus" }), typeRow);

    if (k.type === "line") {
      const s = el("select", { onchange: (e) => { k.value = e.target.value; rerender(); } });
      (data.lines.length ? data.lines : [{ idx: 1, ext: "", name: "1. vonal" }]).forEach((l) =>
        s.append(el("option", { value: String(l.idx), selected: String(l.idx) === String(k.value), text: `${l.idx}. vonal · ${l.ext} ${l.name}` })));
      box.append(el("label", {}, "Vonal", s));
    } else if (k.type === "blf") {
      const s = el("select", { onchange: (e) => { k.value = e.target.value; render(); touch(); } });
      const g1 = el("optgroup", { label: "Mellékek" });
      data.exts.forEach((e) => g1.append(el("option", { value: e.ext, selected: e.ext === k.value, text: `${e.ext} ${e.name}` })));
      const g2 = el("optgroup", { label: "Park helyek" });
      data.parkSlots.forEach((p) => g2.append(el("option", { value: p, selected: p === k.value, text: `Park ${p}` })));
      s.append(g1, g2);
      box.append(el("label", {}, "Kit figyeljen", s));
    } else if (k.type === "speeddial") {
      box.append(el("p", { class: "muted small", text: "A CCX500 a gyorshívót kedvencként mutatja: a telefonkönyvbe kerül, és a vonal mellett jelenik meg. A sorrendjük a gombok sorrendje." }));
      box.append(el("label", {}, "Hívószám", el("input", { value: k.value, placeholder: "pl. 112", inputmode: "tel", pattern: "[0-9*#+]{1,32}",
        oninput: (e) => { k.value = e.target.value.trim(); rerender(); } })));
    } else if (k.type === "park") {
      box.append(el("p", { class: "muted small", text: `Hívás közben megnyomva a ${data.parkExt}-ra parkolja a hívást.` }));
    } else {
      box.append(el("p", { class: "muted small", text: "Üres hely: a telefonon nem jelenik meg semmi, de a helyét megtartja." }));
    }
    if (k.type === "line") {
      box.append(el("p", { class: "muted small", text: "A vonalgombon a telefon mindig a mellék számát és nevét írja ki (a mellék nevét a Mellékek oldalon módosíthatod)." }));
    } else if (k.type !== "unassigned") {
      box.append(el("label", {}, "Felirat", el("input", { value: k.label, maxlength: "24", placeholder: keyText({ ...k, label: "" }),
        oninput: (e) => { k.label = e.target.value; rerender(); } }), el("small", { text: "Üresen hagyva a telefon a fenti szürke szöveget írja ki." })));
    }
    const move = (d) => { const j = i + d; if (j < 0 || j >= keys.length) return; [keys[i], keys[j]] = [keys[j], keys[i]];
      selected = { key: j }; touch(); render(); };
    box.append(el("div", { class: "row wrap" },
      el("button", { type: "button", class: "secondary small", text: "← Előre", disabled: i === 0, onclick: () => move(-1) }),
      el("button", { type: "button", class: "secondary small", text: "Hátra →", disabled: i === keys.length - 1, onclick: () => move(1) }),
      el("button", { type: "button", class: "danger small", text: "Gomb törlése",
        onclick: () => { keys.splice(i, 1); selected = null; touch(); render(); } })));
  }

  function inspectScreen(box) {
    box.append(el("h2", { text: "Kijelző" }),
      el("p", { class: "muted small", text: "Koppints a telefonon egy ikonra, hogy elrejtsd vagy visszahozd, vagy egy alsó gombra, hogy szerkeszd. A + csempével új gombot adsz hozzá." }));

    box.append(el("h3", { text: "Háttérkép" }));
    const wps = el("div", { class: "wallpapers compact", role: "radiogroup", "aria-label": "Háttérkép" });
    const site = data.wallpapers.find((w) => w.file === data.siteWallpaper);
    [{ v: "", label: "Telephelyi", img: site ? site.file : "" }, { v: "none", label: "Nincs", img: "" },
     ...data.wallpapers.map((w) => ({ v: w.file, label: w.label.replace(/\s*\(.*\)$/, ""), img: w.file }))].forEach((o) => {
      wps.append(el("label", { class: "wallpaper" },
        el("input", { type: "radio", name: "wp_choice", value: o.v, checked: o.v === wallpaper, onchange: () => { wallpaper = o.v; touch(); renderScreen(); } }),
        o.img ? el("img", { src: `/wallpapers/${encodeURIComponent(o.img)}`, alt: "", loading: "lazy" }) : el("span", { class: "none", text: "Nincs" }),
        el("span", { text: o.label })));
    });
    box.append(wps);

    box.append(el("h3", { text: "Ikonok a kezdőképernyőn" }));
    const list = el("div", { class: "icon-toggles" });
    const full = visibleCount() >= data.iconsOnScreen;
    list.append(el("div", { class: `icon-count${full ? " full" : ""}`, text: `${visibleCount()} / ${data.iconsOnScreen} ikon látszik` }));
    icons.forEach((ic) => {
      const on = !hidden.has(ic.key);
      list.append(el("label", { class: `check${!on && full && counted(ic) ? " blocked" : ""}` },
        el("input", { type: "checkbox", checked: on, disabled: !!ic.fixed || (!on && full && counted(ic)),
          onchange: (e) => { e.target.checked ? hidden.delete(ic.key) : hidden.add(ic.key); touch(); render(); } }),
        ` ${ic.desc}${ic.fill ? " (üres helyre kerül)" : ic.fixed ? " (mindig látszik)" : ""}`));
    });
    list.append(el("small", { class: "muted", text: `A telefon egyszerre ${data.iconsOnScreen} ikont tud mutatni, ezért többet nem lehet bekapcsolni. Ha másikat szeretnél, előbb kapcsolj ki egyet.` }));
    if (!data.microbrowser) list.append(el("small", { class: "muted", text: "Az Alkalmazások ikon a Beállításokban kapcsolható be (CCXPBX oldal)." }));
    box.append(list, el("p", { class: "muted small", text: "Az ikonok sorrendjét és feliratát a telefon szoftvere rögzíti, ezért nem húzhatók; csak elrejteni lehet őket." }));

    box.append(el("h3", { text: "Ellenőrzés a telefonon" }),
      el("p", { class: "muted small", text: "Mentés után kiolvassa a telefonból (REST API), milyen értékeket használ ténylegesen." }),
      el("div", { class: "row wrap" },
        el("button", { type: "button", class: "secondary small", id: "verify-btn", text: "Ellenőrzés most", onclick: verify }),
        el("button", { type: "button", class: "secondary small", text: "Telefon alkalmazás újraindítása", onclick: restartPhone })),
      el("div", { id: "verify-out" }));

    box.append(el("h3", { text: `Gombok (${keys.length} / ${data.maxKeys})` }), el("div", { class: "row wrap" },
      el("button", { type: "button", class: "secondary small", text: "Minden mellék BLF-re", onclick: () => {
        materialize();
        const used = new Set(keys.filter((k) => k.type === "blf").map((k) => k.value));
        data.exts.forEach((e) => { if (!ownExts.has(e.ext) && !used.has(e.ext) && keys.length < data.maxKeys) keys.push({ type: "blf", value: e.ext, label: e.name.slice(0, 24) }); });
        touch(); render(); } }),
      el("button", { type: "button", class: "danger small", text: "Gombok ürítése", onclick: () => {
        if (!keys.length || confirm("Törlöd az összes gombot? Mentés után a telefon maga rendezi a vonalgombokat.")) { keys = []; touch(); render(); } } })));
  }

  async function verify() {
    const out = $("verify-out"), btn = $("verify-btn");
    if (!out) return;
    if (dirty) { out.replaceChildren(el("p", { class: "flash warn", text: "Előbb mentsd el a változásokat, utána ellenőrizd." })); return; }
    btn.disabled = true;
    out.replaceChildren(el("p", { class: "muted small", text: "Lekérdezés a telefontól…" }));
    try {
      const d = await (await fetch(`/phones/${data.mac}/screen/verify`, { cache: "no-store" })).json();
      if (d.error) { out.replaceChildren(el("p", { class: "flash err", text: d.error })); return; }
      const t = el("table", { class: "verify" }, el("tr", {}, el("th", { text: "Ikon" }), el("th", { text: "Szerver" }), el("th", { text: "Telefon" }), el("th", { text: "Forrás" })));
      let unknown = 0, differs = 0;
      const show = (v) => v === "0" ? "rejtett" : v === "1" ? "látható" : (v == null || v === "" ? "alapérték" : `„${v}”`);
      d.rows.forEach((r) => {
        const want = r.expected || "", got = r.phone;
        let cls = "ok", text = show(got);
        if (got == null) { cls = "unknown"; text = "nem ismeri"; unknown++; }
        else if (want && want !== got && (got === "0" || got === "1")) { cls = "bad"; differs++; }
        else if (got !== "0" && got !== "1") cls = "unknown";
        const src = { config: "szerver", default: "gyári", web: "webfelület", local: "telefonon állítva", device: "eszköz" }[r.source] || r.source || "";
        if (r.source === "web" || r.source === "local") { cls = "bad"; differs++; }
        t.append(el("tr", {}, el("td", { text: r.desc }), el("td", { text: show(want) }), el("td", { class: cls, text }), el("td", { class: "muted", text: src })));
      });
      const msgs = [];
      if (unknown === d.rows.length) msgs.push(["warn", "A telefon egyik homeScreen paramétert sem ismeri, vagyis ez a CCX500 firmware nem engedi elrejteni a kezdőképernyő ikonjait."]);
      else if (differs) msgs.push(["warn", "A telefon más értéket használ, mint amit a szerver küld. Valószínűleg a telefonon vagy a webfelületén tett beállítás (override) felülírja: a telefon oldalán a Telefon oldali override-ok törlése segít, vagy nem kapta meg a konfigot (Konfig szinkronizálás)."]);
      else if (!d.rows.some((r) => r.expected === "0")) msgs.push(["ok", "A telefon ismeri a paramétereket. Most egy ikon sincs elrejtve: rejts el egyet, ments, és ellenőrizd újra; akkor a Forrás oszlopban 'szerver' és 'rejtett' kell álljon."]);
      else msgs.push(["ok", "A telefon átvette a beállításokat. Ha a kijelzőn még nem látszik a változás, indítsd újra a telefon alkalmazását."]);
      const rawBox = el("details", { class: "verify-raw" }, el("summary", { text: "A telefon nyers válasza" }), el("pre", { class: "mono small", text: d.raw || "" }));
      out.replaceChildren(t, ...msgs.map(([k, m]) => el("p", { class: `flash ${k}`, text: m })), rawBox);
    } catch (_) {
      out.replaceChildren(el("p", { class: "flash err", text: "A szerver nem válaszolt." }));
    } finally { btn.disabled = false; }
  }

  async function restartPhone() {
    if (!confirm("Újraindítod a telefon alkalmazását? Kb. fél percig nem lesz használható.")) return;
    await fetch(`/phones/${data.mac}/action/restart`, { method: "POST", body: new URLSearchParams() });
    const out = $("verify-out");
    if (out) out.replaceChildren(el("p", { class: "flash ok", text: "Újraindítás elküldve. Kb. fél perc múlva ellenőrizd újra." }));
  }

  function focusInspector() { const f = $("inspector").querySelector("select, input"); if (f) f.focus(); }
  function render() { renderScreen(); renderInspector(); }

  document.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => {
    mode = b.dataset.mode; selected = null;
    document.querySelectorAll("[data-mode]").forEach((x) => x.classList.toggle("on", x === b));
    render();
  }));

  $("screen-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const bad = keys.findIndex((k) => (k.type === "speeddial" || k.type === "blf") && !/^[0-9*#+]{1,32}$/.test(k.value));
    if (bad >= 0) {
      mode = "edit"; selected = { key: bad }; page = bad > 1 ? 1 : page; render(); focusInspector();
      alert(`${bad + 1}. gomb: adj meg egy hívószámot.`);
      return;
    }
    const box = $("hidden-fields");
    box.replaceChildren(el("input", { type: "hidden", name: "wallpaper", value: wallpaper }),
                        el("input", { type: "hidden", name: "home_hidden", value: [...hidden].join(",") }));
    keys.forEach((k, i) => {
      const n = i + 1;
      box.append(el("input", { type: "hidden", name: `key_type_${n}`, value: k.type }),
                 el("input", { type: "hidden", name: `key_value_${n}`, value: k.value }),
                 el("input", { type: "hidden", name: `key_label_${n}`, value: k.label }));
    });
    const form = $("screen-form"), btn = form.querySelector("button:not([type=button])");
    btn.disabled = true;
    showResult([["info", "Mentés és küldés a telefonra…"]]);
    try {
      const r = await fetch(form.action, { method: "POST", body: new FormData(form), headers: { Accept: "application/json" } });
      if (r.redirected && r.url.includes("/login")) { location.href = "/login"; return; }
      const d = await r.json();
      if (d.ok) { dirty = false; $("dirty").hidden = true; }
      showResult(d.messages || []);
      render();
    } catch (_) {
      showResult([["err", "A mentés nem sikerült: a szerver nem válaszolt."]]);
    } finally { btn.disabled = false; }
  });

  function showResult(messages) {
    const box = $("save-result");
    box.replaceChildren(...messages.map(([kind, msg]) => el("div", { class: `flash ${kind === "info" ? "" : kind}`, text: msg })));
  }
  window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && selected) { selected = null; render(); } });

  async function poll() {
    try {
      const r = await fetch("/api/live", { headers: { Accept: "application/json" }, cache: "no-store" });
      if (r.ok) {
        states = Object.fromEntries(((await r.json()).extensions || []).map((e) => [e.num, e.state]));
        renderScreen();
      }
    } catch (_) { /* keep the last known state */ }
  }

  render();
  tick();
  setInterval(tick, 15000);
  poll();
  setInterval(() => { if (!document.hidden) poll(); }, 5000);
})();
