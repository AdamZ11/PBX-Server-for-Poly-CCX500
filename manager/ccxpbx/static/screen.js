/* CCXPBX: visual editor for the CCX500 home screen (line keys + wallpaper) with a live preview. */
(function () {
  "use strict";
  const data = JSON.parse(document.getElementById("editor-data").textContent);
  const TYPES = JSON.parse(document.getElementById("key-types").textContent);
  const SHORT = { line: "Vonal", blf: "BLF", park: "Park", speeddial: "Gyorshívó", unassigned: "Üres" };
  const PER_PAGE = 8;
  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) n.setAttribute(k, v === true ? "" : v);
    }
    kids.flat().forEach((c) => c != null && n.append(c));
    return n;
  };

  // ---------------------------------------------------------------- state
  let keys = data.keys.map((k) => ({ type: k.type, value: k.value || "", label: k.label || "" }));
  let wallpaper = data.wallpaper;
  let selected = -1;
  let page = 0;
  let states = {};   // ext -> free | ring | busy | off (from /api/live)
  let dirty = false;
  const extName = Object.fromEntries(data.exts.map((e) => [e.ext, e.name]));
  const ownExts = new Set(data.lines.map((l) => l.ext));

  function markDirty() {
    dirty = true;
    $("dirty").hidden = false;
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

  // What the phone shows on the key
  function keyText(k) {
    if (k.type === "line") {
      const line = data.lines.find((l) => String(l.idx) === String(k.value)) || data.lines[0];
      return line ? (k.label || `${line.ext} ${line.name}`) : (k.label || "Vonal");
    }
    if (k.type === "blf") return k.label || extName[k.value] || k.value || "BLF";
    if (k.type === "park") return k.label || "Park";
    if (k.type === "speeddial") return k.label || k.value || "Gyorshívó";
    return "";
  }

  function keyState(k) {
    if (k.type === "blf") {
      if (data.parkSlots.includes(k.value)) return "park-slot";
      return states[k.value] || "off";
    }
    if (k.type === "line") {
      const line = data.lines.find((l) => String(l.idx) === String(k.value)) || data.lines[0];
      return line ? (states[line.ext] || "off") : "off";
    }
    return "";
  }

  // Keys as the phone lays them out when the list is empty (one key per reg.N.lineKeys)
  function effectiveKeys() {
    if (keys.length) return keys.map((k, i) => ({ ...k, index: i }));
    const auto = [];
    data.lines.forEach((l) => {
      for (let n = 0; n < (l.line_keys || 1); n++) auto.push({ type: "line", value: String(l.idx), label: "", index: -1 });
    });
    return auto;
  }

  // ---------------------------------------------------------------- preview
  const ICONS = {
    line: '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1A17 17 0 0 1 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.2.2 2.4.6 3.6.1.3 0 .7-.2 1z"/></svg>',
    park: '<span class="ccx-glyph">P</span>',
    speeddial: '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M12 2l2.9 6.9 7.1.6-5.4 4.7 1.6 7L12 17.5 5.8 21.2l1.6-7L2 9.5l7.1-.6z"/></svg>',
  };

  function renderPreview() {
    const wp = wallpaper === "" ? data.siteWallpaper : (wallpaper === "none" ? "" : wallpaper);
    $("pv-screen").style.backgroundImage = wp ? `url("/wallpapers/${encodeURIComponent(wp)}")` : "none";
    const first = data.lines[0];
    $("pv-line").textContent = first ? `${first.ext} · ${first.name}` : "Nincs vonal";

    const list = effectiveKeys();
    const pages = Math.max(1, Math.ceil(list.length / PER_PAGE));
    page = Math.min(page, pages - 1);
    const box = $("pv-keys");
    box.replaceChildren();
    list.slice(page * PER_PAGE, page * PER_PAGE + PER_PAGE).forEach((k, i) => {
      const st = keyState(k);
      const icon = el("span", { class: "ccx-icon" });
      if (k.type === "blf") icon.append(el("span", { class: `ccx-dot ${st}` }));
      else icon.innerHTML = ICONS[k.type] || "";
      const tile = el("button", {
        type: "button",
        class: `ccx-key t-${k.type}${k.index === selected && k.index >= 0 ? " sel" : ""}${k.type === "line" ? " st-" + st : ""}`,
        title: `${page * PER_PAGE + i + 1}. gomb · ${TYPES[k.type] || ""}`,
        onclick: () => { if (k.index >= 0) select(k.index, true); },
      }, icon, el("span", { class: "ccx-label", text: keyText(k) }));
      box.append(tile);
    });
    if (!list.length) box.append(el("div", { class: "ccx-empty", text: "Nincs gomb. Rendelj vonalat a telefonhoz, vagy adj hozzá gombokat." }));

    const pager = $("pv-pager");
    pager.replaceChildren();
    if (pages > 1) {
      for (let p = 0; p < pages; p++) {
        pager.append(el("button", { type: "button", class: p === page ? "on" : "", "aria-label": `${p + 1}. oldal`,
          onclick: () => { page = p; renderPreview(); } }));
      }
    }
    $("pv-note").textContent = keys.length
      ? `${list.length} gomb, ${pages} oldal (oldalanként ${PER_PAGE}). A pöttyök a mellékek élő állapotát mutatják.`
      : "Automatikus kiosztás: a telefon csak a vonalgombokat mutatja.";
  }

  function tick() {
    const d = new Date();
    const h = d.getHours(), m = String(d.getMinutes()).padStart(2, "0");
    $("pv-clock").textContent = data.clock24 ? `${h}:${m}` : `${h % 12 || 12}:${m} ${h < 12 ? "de." : "du."}`;
  }

  // ---------------------------------------------------------------- editor
  function valueField(k, i) {
    const set = (v) => { k.value = v; markDirty(); renderPreview(); };
    if (k.type === "line") {
      const s = el("select", { "aria-label": "Vonal", onchange: (e) => set(e.target.value) });
      (data.lines.length ? data.lines : [{ idx: 1, ext: "", name: "1. vonal" }]).forEach((l) =>
        s.append(el("option", { value: String(l.idx), selected: String(l.idx) === String(k.value), text: `${l.idx}. ${l.ext} ${l.name}` })));
      return s;
    }
    if (k.type === "blf") {
      const s = el("select", { "aria-label": "Mellék", onchange: (e) => set(e.target.value) });
      const g1 = el("optgroup", { label: "Mellékek" });
      data.exts.forEach((e) => g1.append(el("option", { value: e.ext, selected: e.ext === k.value, text: `${e.ext} ${e.name}` })));
      const g2 = el("optgroup", { label: "Park helyek" });
      data.parkSlots.forEach((p) => g2.append(el("option", { value: p, selected: p === k.value, text: `Park ${p}` })));
      s.append(g1, g2);
      if (k.value && !extName[k.value] && !data.parkSlots.includes(k.value)) s.prepend(el("option", { value: k.value, selected: true, text: k.value }));
      return s;
    }
    if (k.type === "speeddial") {
      return el("input", { value: k.value, placeholder: "hívószám", pattern: "[0-9*#+]{1,32}", inputmode: "tel", "aria-label": "Hívószám",
        oninput: (e) => set(e.target.value.trim()) });
    }
    return el("span", { class: "muted small", text: k.type === "park" ? `hívás közben a ${data.parkExt}-ra parkol` : "üres hely" });
  }

  function labelPlaceholder(k) {
    const t = keyText({ ...k, label: "" });
    return t || "felirat";
  }

  let dragFrom = -1;
  function renderList() {
    const ol = $("key-list");
    ol.replaceChildren();
    keys.forEach((k, i) => {
      const typeSel = el("select", { "aria-label": "Típus", onchange: (e) => {
        k.type = e.target.value; k.value = defaultValue(k.type); markDirty(); renderAll(); } });
      Object.entries(TYPES).forEach(([t, label]) => typeSel.append(el("option", { value: t, selected: t === k.type, title: label, text: SHORT[t] || label })));
      const label = el("input", { value: k.label, maxlength: "24", placeholder: labelPlaceholder(k), "aria-label": "Felirat",
        oninput: (e) => { k.label = e.target.value; markDirty(); renderPreview(); } });
      const move = (d) => { const j = i + d; if (j < 0 || j >= keys.length) return; [keys[i], keys[j]] = [keys[j], keys[i]]; selected = j; markDirty(); renderAll(); };
      const li = el("li", { class: `keyrow${i === selected ? " sel" : ""}`, draggable: "true",
        onclick: (e) => { if (selected !== i) { selected = i; page = Math.floor(i / PER_PAGE); renderPreview(); markSel(); } },
        ondragstart: (e) => { dragFrom = i; li.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; },
        ondragend: () => li.classList.remove("dragging"),
        ondragover: (e) => { e.preventDefault(); li.classList.add("over"); },
        ondragleave: () => li.classList.remove("over"),
        ondrop: (e) => { e.preventDefault(); li.classList.remove("over");
          if (dragFrom < 0 || dragFrom === i) return;
          const [m] = keys.splice(dragFrom, 1); keys.splice(i, 0, m); selected = i; dragFrom = -1; markDirty(); renderAll(); },
      },
        el("span", { class: "handle", title: "Húzd az áthelyezéshez", text: "⋮⋮" }),
        el("span", { class: "pos mono", text: String(i + 1) }),
        typeSel, valueField(k, i), label,
        el("span", { class: "rowbtns" },
          el("button", { type: "button", class: "secondary small", title: "Fel", "aria-label": "Fel", onclick: () => move(-1), text: "↑" }),
          el("button", { type: "button", class: "secondary small", title: "Le", "aria-label": "Le", onclick: () => move(1), text: "↓" }),
          el("button", { type: "button", class: "danger small", title: "Törlés", "aria-label": "Törlés",
            onclick: () => { keys.splice(i, 1); selected = Math.min(selected, keys.length - 1); markDirty(); renderAll(); }, text: "✕" })));
      ol.append(li);
    });
    $("key-count").textContent = `${keys.length} / ${data.maxKeys}`;
    document.querySelectorAll("[data-add]").forEach((b) => { b.disabled = keys.length >= data.maxKeys; });
  }

  function markSel() {
    document.querySelectorAll("#key-list .keyrow").forEach((r, i) => r.classList.toggle("sel", i === selected));
  }

  function select(i, focus) {
    selected = i;
    page = Math.floor(i / PER_PAGE);
    renderAll();
    const row = document.querySelectorAll("#key-list .keyrow")[i];
    if (row) {
      row.scrollIntoView({ block: "nearest", behavior: "smooth" });
      if (focus) row.querySelector("input, select:not(:first-of-type)")?.focus();
    }
  }

  function renderWallpapers() {
    const box = $("wp-list");
    box.replaceChildren();
    const site = data.wallpapers.find((w) => w.file === data.siteWallpaper);
    const opts = [{ v: "", label: "Telephelyi", img: site ? site.file : "", sub: site ? site.label.replace(/\s*\(.*\)$/, "") : "nincs" },
                  { v: "none", label: "Nincs", img: "" },
                  ...data.wallpapers.map((w) => ({ v: w.file, label: w.label, img: w.file }))];
    opts.forEach((o) => {
      const input = el("input", { type: "radio", name: "wp_choice", value: o.v, checked: o.v === wallpaper,
        onchange: () => { wallpaper = o.v; markDirty(); renderPreview(); } });
      const pic = o.img ? el("img", { src: `/wallpapers/${encodeURIComponent(o.img)}`, alt: "", loading: "lazy" }) : el("span", { class: "none", text: "Nincs" });
      box.append(el("label", { class: "wallpaper" }, input, pic, el("span", { text: o.sub ? `${o.label}: ${o.sub}` : o.label })));
    });
  }

  function renderAll() {
    renderList();
    renderPreview();
  }

  function add(type) {
    if (keys.length >= data.maxKeys) return;
    keys.push({ type, value: defaultValue(type), label: type === "park" ? "Park" : "" });
    markDirty();
    select(keys.length - 1, true);
  }

  document.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => add(b.dataset.add)));
  $("clear-keys").addEventListener("click", () => {
    if (!keys.length || confirm("Törlöd az összes gombot? Mentés után a telefon automatikusan rendezi a vonalgombokat.")) {
      keys = []; selected = -1; markDirty(); renderAll();
    }
  });
  $("all-blf").addEventListener("click", () => {
    const used = new Set(keys.filter((k) => k.type === "blf").map((k) => k.value));
    if (!keys.length) data.lines.forEach((l) => keys.push({ type: "line", value: String(l.idx), label: "" }));
    data.exts.forEach((e) => {
      if (!ownExts.has(e.ext) && !used.has(e.ext) && keys.length < data.maxKeys) keys.push({ type: "blf", value: e.ext, label: e.name.slice(0, 24) });
    });
    markDirty(); renderAll();
  });

  $("screen-form").addEventListener("submit", (e) => {
    const bad = keys.findIndex((k) => (k.type === "speeddial" || k.type === "blf") && !/^[0-9*#+]{1,32}$/.test(k.value));
    if (bad >= 0) {
      e.preventDefault();
      select(bad, true);
      alert(`${bad + 1}. gomb: adj meg egy hívószámot.`);
      return;
    }
    const box = $("hidden-fields");
    box.replaceChildren(el("input", { type: "hidden", name: "wallpaper", value: wallpaper }));
    keys.forEach((k, i) => {
      const n = i + 1;
      box.append(el("input", { type: "hidden", name: `key_type_${n}`, value: k.type }),
                 el("input", { type: "hidden", name: `key_value_${n}`, value: k.value }),
                 el("input", { type: "hidden", name: `key_label_${n}`, value: k.label }));
    });
    dirty = false;
  });
  window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

  // ---------------------------------------------------------------- live BLF state
  async function poll() {
    try {
      const r = await fetch("/api/live", { headers: { Accept: "application/json" }, cache: "no-store" });
      if (r.ok) {
        const d = await r.json();
        states = Object.fromEntries((d.extensions || []).map((e) => [e.num, e.state]));
        renderPreview();
      }
    } catch (_) { /* keep the last known state */ }
  }

  renderWallpapers();
  renderAll();
  tick();
  setInterval(tick, 15000);
  poll();
  setInterval(() => { if (!document.hidden) poll(); }, 5000);
})();
