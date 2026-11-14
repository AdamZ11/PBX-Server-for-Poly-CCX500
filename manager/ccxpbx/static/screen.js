/* CCXPBX: WYSIWYG editor for the CCX500 home screen. The phone itself is the editor:
   tap an icon to hide/show it, tap or drag a key on the dock, tap + to add one. */
(function () {
  "use strict";
  const data = JSON.parse(document.getElementById("editor-data").textContent);
  const TYPES = JSON.parse(document.getElementById("key-types").textContent);
  const SHORT = { line: "Vonal", blf: "BLF", park: "Park", speeddial: "Gyorshívó", unassigned: "Üres" };
  const APPS_PER_PAGE = 6;
  const DOCK_PER_PAGE = 8;
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
    line: P(PHONE),
    blf: P("M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8zm0 10c4.4 0 8 2 8 4.5V20H4v-1.5C4 16 7.6 14 12 14z"),
    park: '<span class="ccx-p">P</span>',
    speeddial: P("M12 2l2.9 6.9 7.1.6-5.4 4.7 1.6 7L12 17.5 5.8 21.2l1.6-7L2 9.5l7.1-.6z"),
    unassigned: "",
    plus: P("M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z"),
  };

  // ---------------------------------------------------------------- state
  let keys = data.keys.map((k) => ({ type: k.type, value: k.value || "", label: k.label || "" }));
  let wallpaper = data.wallpaper;
  const hidden = new Set(data.homeHidden);
  let mode = "edit";
  let selected = null;          // null | {key: index} | {add: true}
  let appPage = 0, dockPage = 0;
  let states = {};
  let dirty = false;
  let dragFrom = -1;
  const extName = Object.fromEntries(data.exts.map((e) => [e.ext, e.name]));
  const ownExts = new Set(data.lines.map((l) => l.ext));
  const icons = data.homeIcons.filter((i) => i.key !== "application" || data.microbrowser);

  function touch() { dirty = true; $("dirty").hidden = false; }

  function lineOf(k) { return data.lines.find((l) => String(l.idx) === String(k.value)) || data.lines[0]; }
  function keyText(k) {
    if (k.type === "line") { const l = lineOf(k); return k.label || (l ? l.ext : "Vonal"); }
    if (k.type === "blf") return k.label || extName[k.value] || k.value || "BLF";
    if (k.type === "park") return k.label || "Park";
    if (k.type === "speeddial") return k.label || k.value || "Gyorshívó";
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
  function renderScreen() {
    const wp = wallpaper === "" ? data.siteWallpaper : (wallpaper === "none" ? "" : wallpaper);
    $("pv-screen").style.backgroundImage = wp ? `url("/wallpapers/${encodeURIComponent(wp)}")` : "none";
    const first = data.lines[0];
    $("pv-status").textContent = first ? `${first.ext} ${first.name}` : "";
    const editing = mode === "edit";
    document.querySelector(".ccx-device").classList.toggle("editing", editing);

    // app icons
    const shown = editing ? icons : icons.filter((i) => !hidden.has(i.key));
    const appPages = Math.max(1, Math.ceil(shown.length / APPS_PER_PAGE));
    appPage = Math.min(appPage, appPages - 1);
    const apps = $("pv-apps");
    apps.replaceChildren();
    shown.slice(appPage * APPS_PER_PAGE, (appPage + 1) * APPS_PER_PAGE).forEach((ic) => {
      const off = hidden.has(ic.key);
      apps.append(el("button", {
        type: "button", class: `ccx-app${off ? " off" : ""}`,
        title: editing ? `${ic.desc}: koppints az ${off ? "megjelenítéshez" : "elrejtéshez"}` : ic.desc,
        "aria-pressed": editing ? String(!off) : false,
        onclick: () => { if (!editing) return; off ? hidden.delete(ic.key) : hidden.add(ic.key); touch(); render(); },
      }, el("span", { class: "ccx-circle", html: GLYPH[ic.key] }), el("span", { class: "ccx-cap", text: ic.label }),
         editing && off ? el("span", { class: "ccx-badge", text: "rejtve" }) : null));
    });
    dots($("pv-app-dots"), appPages, appPage, (p) => { appPage = p; renderScreen(); });

    // line keys dock
    const list = keys.length ? keys : autoKeys();
    const tiles = list.map((k, i) => ({ k, i }));
    if (editing && keys.length < data.maxKeys) tiles.push({ add: true });
    const dockPages = Math.max(1, Math.ceil(tiles.length / DOCK_PER_PAGE));
    dockPage = Math.min(dockPage, dockPages - 1);
    const dock = $("pv-dock");
    dock.replaceChildren();
    tiles.slice(dockPage * DOCK_PER_PAGE, (dockPage + 1) * DOCK_PER_PAGE).forEach((t) => {
      if (t.add) {
        dock.append(el("button", { type: "button", class: `ccx-key add${selected && selected.add ? " sel" : ""}`, title: "Új gomb",
          onclick: () => { selected = { add: true }; render(); } },
          el("span", { class: "ccx-circle", html: GLYPH.plus }), el("span", { class: "ccx-cap", text: "Új gomb" })));
        return;
      }
      const { k, i } = t;
      const st = keyState(k);
      const sel = selected && selected.key === i && keys.length;
      dock.append(el("button", {
        type: "button", class: `ccx-key t-${k.type} st-${st || "none"}${sel ? " sel" : ""}`, draggable: editing ? "true" : false,
        title: `${i + 1}. gomb · ${TYPES[k.type] || ""}`,
        onclick: () => { if (!editing) return; materialize(); selected = { key: i }; render(); },
        ondragstart: (e) => { dragFrom = i; e.dataTransfer.effectAllowed = "move"; e.currentTarget.classList.add("dragging"); },
        ondragend: (e) => e.currentTarget.classList.remove("dragging"),
        ondragover: (e) => { if (dragFrom >= 0) { e.preventDefault(); e.currentTarget.classList.add("over"); } },
        ondragleave: (e) => e.currentTarget.classList.remove("over"),
        ondrop: (e) => {
          e.preventDefault(); e.currentTarget.classList.remove("over");
          if (dragFrom < 0 || dragFrom === i) return;
          materialize();
          const [m] = keys.splice(dragFrom, 1); keys.splice(i, 0, m);
          selected = { key: i }; dragFrom = -1; touch(); render();
        },
      }, el("span", { class: "ccx-circle", html: GLYPH[k.type] || "" }), el("span", { class: "ccx-cap", text: keyText(k) })));
    });
    dots($("pv-dock-dots"), dockPages, dockPage, (p) => { dockPage = p; renderScreen(); });

    $("pv-note").textContent = editing
      ? "Koppints egy ikonra az elrejtéshez, egy gombra a szerkesztéshez, húzd a gombokat az átrendezéshez."
      : (keys.length ? `${keys.length} gomb · a pöttyök és keretek a mellékek élő állapotát mutatják` : "Automatikus kiosztás: a telefon a vonalgombokat mutatja.");
  }

  function dots(box, pages, current, go) {
    box.replaceChildren();
    if (pages < 2) return;
    for (let p = 0; p < pages; p++) box.append(el("button", { type: "button", class: p === current ? "on" : "", "aria-label": `${p + 1}. oldal`, onclick: () => go(p) }));
  }

  function tick() {
    const d = new Date();
    const h = d.getHours(), m = String(d.getMinutes()).padStart(2, "0");
    $("pv-time").textContent = data.clock24 ? `${h}:${m}` : `${h % 12 || 12}:${m} ${h < 12 ? "AM" : "PM"}`;
    $("pv-date").textContent = `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}/${d.getFullYear()}`;
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
        selected = { key: keys.length - 1 }; dockPage = Math.floor(keys.length / DOCK_PER_PAGE); touch(); render(); focusInspector(); } },
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
      box.append(el("label", {}, "Hívószám", el("input", { value: k.value, placeholder: "pl. 112", inputmode: "tel", pattern: "[0-9*#+]{1,32}",
        oninput: (e) => { k.value = e.target.value.trim(); rerender(); } })));
    } else if (k.type === "park") {
      box.append(el("p", { class: "muted small", text: `Hívás közben megnyomva a ${data.parkExt}-ra parkolja a hívást.` }));
    } else {
      box.append(el("p", { class: "muted small", text: "Üres hely: a telefonon nem jelenik meg semmi, de a helyét megtartja." }));
    }
    if (k.type !== "unassigned") {
      box.append(el("label", {}, "Felirat", el("input", { value: k.label, maxlength: "24", placeholder: keyText({ ...k, label: "" }),
        oninput: (e) => { k.label = e.target.value; rerender(); } }), el("small", { text: "Üresen hagyva a telefon a fenti szürke szöveget írja ki." })));
    }
    const move = (d) => { const j = i + d; if (j < 0 || j >= keys.length) return; [keys[i], keys[j]] = [keys[j], keys[i]];
      selected = { key: j }; dockPage = Math.floor(j / DOCK_PER_PAGE); touch(); render(); };
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
    icons.forEach((ic) => list.append(el("label", { class: "check" },
      el("input", { type: "checkbox", checked: !hidden.has(ic.key), onchange: (e) => { e.target.checked ? hidden.delete(ic.key) : hidden.add(ic.key); touch(); renderScreen(); } }),
      ` ${ic.desc}`)));
    if (!data.microbrowser) list.append(el("small", { class: "muted", text: "Az Alkalmazások ikon a Beállításokban kapcsolható be (CCXPBX oldal)." }));
    box.append(list, el("p", { class: "muted small", text: "Az ikonok sorrendjét és feliratát a telefon szabja meg, csak elrejteni lehet őket." }));

    box.append(el("h3", { text: `Gombok (${keys.length} / ${data.maxKeys})` }), el("div", { class: "row wrap" },
      el("button", { type: "button", class: "secondary small", text: "Minden mellék BLF-re", onclick: () => {
        materialize();
        const used = new Set(keys.filter((k) => k.type === "blf").map((k) => k.value));
        data.exts.forEach((e) => { if (!ownExts.has(e.ext) && !used.has(e.ext) && keys.length < data.maxKeys) keys.push({ type: "blf", value: e.ext, label: e.name.slice(0, 24) }); });
        touch(); render(); } }),
      el("button", { type: "button", class: "danger small", text: "Gombok ürítése", onclick: () => {
        if (!keys.length || confirm("Törlöd az összes gombot? Mentés után a telefon maga rendezi a vonalgombokat.")) { keys = []; touch(); render(); } } })));
  }

  function focusInspector() { const f = $("inspector").querySelector("select, input"); if (f) f.focus(); }
  function render() { renderScreen(); renderInspector(); }

  document.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => {
    mode = b.dataset.mode; selected = null;
    document.querySelectorAll("[data-mode]").forEach((x) => x.classList.toggle("on", x === b));
    render();
  }));

  $("screen-form").addEventListener("submit", (e) => {
    const bad = keys.findIndex((k) => (k.type === "speeddial" || k.type === "blf") && !/^[0-9*#+]{1,32}$/.test(k.value));
    if (bad >= 0) {
      e.preventDefault();
      mode = "edit"; selected = { key: bad }; dockPage = Math.floor(bad / DOCK_PER_PAGE); render(); focusInspector();
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
    dirty = false;
  });
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
