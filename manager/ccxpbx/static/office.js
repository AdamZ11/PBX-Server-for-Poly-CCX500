/* CCXPBX: weekly office hours editor for the phones' "Off Hours" power saving mode. */
(function () {
  "use strict";
  const data = JSON.parse(document.getElementById("oh-data").textContent);
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
  const hours = {};   // day -> [start, end] or undefined (no office hours that day)
  Object.entries(data.hours).forEach(([d, v]) => { hours[d] = [v[0], v[1]]; });
  const now = new Date();
  let previewDay = data.days[(now.getDay() + 6) % 7].key;
  let previewTime = now.getHours() + Math.floor(now.getMinutes() / 15) / 4;
  let dirty = false;
  const touch = () => { dirty = true; $("dirty").hidden = false; };
  const fmt = (h) => `${Math.floor(h)}:${String(Math.round((h % 1) * 60)).padStart(2, "0")}`;

  // ---------------------------------------------------------------- weekly grid
  const rows = {};
  function buildGrid() {
    const grid = $("oh-grid");
    data.days.forEach((d) => {
      const check = el("input", { type: "checkbox", "aria-label": `${d.name}: munkanap`, onchange: (e) => {
        hours[d.key] = e.target.checked ? [8, 17] : undefined; touch(); render(); } });
      const track = el("div", { class: "oh-track", title: "Húzd a munkaidő kijelöléséhez" });
      const bar = el("div", { class: "oh-bar" }, el("span", { class: "oh-edge l" }), el("span", { class: "oh-edge r" }));
      const nowLine = el("div", { class: "oh-now", title: "Előnézet időpontja" });
      track.append(bar, nowLine);
      const startSel = el("select", { "aria-label": `${d.name} kezdete`, onchange: (e) => setSpan(d.key, +e.target.value, null) });
      const endSel = el("select", { "aria-label": `${d.name} vége`, onchange: (e) => setSpan(d.key, null, +e.target.value) });
      for (let h = 0; h <= 23; h++) startSel.append(el("option", { value: h, text: `${h}:00` }));
      for (let h = 1; h <= 24; h++) endSel.append(el("option", { value: h, text: `${h}:00` }));
      const row = el("div", { class: "oh-row" },
        el("label", { class: "check oh-day" }, check, ` ${d.name}`), track,
        el("span", { class: "oh-times" }, startSel, "–", endSel));
      grid.append(row);
      rows[d.key] = { check, track, bar, nowLine, startSel, endSel, row };
      dragTrack(d.key, track);
    });
  }

  function setSpan(day, start, end) {
    const cur = hours[day] || [8, 17];
    let a = start == null ? cur[0] : start, b = end == null ? cur[1] : end;
    if (b <= a) { if (start != null) b = Math.min(24, a + 1); else a = Math.max(0, b - 1); }
    hours[day] = [a, b]; touch(); render();
  }

  function hourAt(track, clientX) {
    const r = track.getBoundingClientRect();
    return Math.max(0, Math.min(24, Math.round(((clientX - r.left) / r.width) * 24)));
  }

  function dragTrack(day, track) {
    let mode = null, anchor = 0;
    track.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      track.setPointerCapture(e.pointerId);
      const h = hourAt(track, e.clientX), cur = hours[day];
      if (cur && Math.abs(h - cur[0]) <= 1 && e.target.closest(".oh-edge.l, .oh-bar")) mode = "start";
      else if (cur && Math.abs(h - cur[1]) <= 1 && e.target.closest(".oh-edge.r, .oh-bar")) mode = "end";
      else { mode = "paint"; anchor = h; hours[day] = [Math.min(h, 23), Math.min(h, 23) + 1]; }
      touch(); render();
    });
    track.addEventListener("pointermove", (e) => {
      if (!mode) return;
      const h = hourAt(track, e.clientX), cur = hours[day];
      if (mode === "start") cur[0] = Math.min(h, cur[1] - 1);
      else if (mode === "end") cur[1] = Math.max(h, cur[0] + 1);
      else { const a = Math.min(anchor, h), b = Math.max(anchor, h); hours[day] = [Math.min(a, 23), Math.max(b, a + 1)]; }
      render();
    });
    const stop = () => { mode = null; };
    track.addEventListener("pointerup", stop);
    track.addEventListener("pointercancel", stop);
  }

  // ---------------------------------------------------------------- phone preview
  function isOffHours(day, t) {
    if (!$("oh-enabled").checked) return false;
    const span = hours[day];
    return !span || t < span[0] || t >= span[1];
  }

  function render() {
    const enabled = $("oh-enabled").checked;
    data.days.forEach((d) => {
      const r = rows[d.key], span = hours[d.key];
      r.check.checked = !!span;
      r.row.classList.toggle("off", !span);
      r.row.classList.toggle("disabled", !enabled);
      r.bar.hidden = !span;
      if (span) { r.bar.style.left = `${(span[0] / 24) * 100}%`; r.bar.style.width = `${((span[1] - span[0]) / 24) * 100}%`; }
      r.startSel.disabled = r.endSel.disabled = !span;
      r.startSel.value = span ? span[0] : 8;
      r.endSel.value = span ? span[1] : 17;
      r.nowLine.hidden = d.key !== previewDay;
      r.nowLine.style.left = `${(previewTime / 24) * 100}%`;
    });
    document.querySelectorAll("#oh-day-pick button").forEach((b) => b.classList.toggle("on", b.dataset.day === previewDay));
    $("oh-time").value = previewTime;
    $("oh-time-label").textContent = fmt(previewTime);
    const h = Math.floor(previewTime), m = String(Math.round((previewTime % 1) * 60)).padStart(2, "0");
    $("oh-clock").textContent = data.clock24 ? `${h}:${m}` : `${h % 12 || 12}:${m} ${h < 12 ? "AM" : "PM"}`;
    const day = data.days.find((d) => d.key === previewDay);
    $("oh-date").textContent = day.name;
    const off = isOffHours(previewDay, previewTime);
    $("oh-screen").classList.toggle("is-off", off);
    $("oh-state").innerHTML = "";
    $("oh-state").append(
      el("span", { class: "status" }, el("span", { class: `dot ${off ? "off" : "free"}` }),
        off ? `${day.name} ${fmt(previewTime)}: Off Hours, a kijelző ${document.querySelector("[name=idle_off]").value} perc után elsötétül`
            : enabled ? `${day.name} ${fmt(previewTime)}: munkaidő, a kijelző ${document.querySelector("[name=idle_office]").value} perc tétlenség után sötétül el`
                      : "Az Off Hours mód ki van kapcsolva, a kijelző nem sötétül el"));
    $("oh-value").value = data.days.filter((d) => hours[d.key]).map((d) => `${d.key}=${hours[d.key][0]}-${hours[d.key][1]}`).join(",");
  }

  // ---------------------------------------------------------------- controls
  const pick = $("oh-day-pick");
  data.days.forEach((d) => pick.append(el("button", { type: "button", "data-day": d.key, title: d.name, text: d.short,
    onclick: () => { previewDay = d.key; render(); } })));
  $("oh-time").addEventListener("input", (e) => { previewTime = +e.target.value; render(); });
  $("oh-enabled").addEventListener("change", () => { touch(); render(); });
  document.querySelectorAll("#oh-form input[type=number]").forEach((i) => i.addEventListener("input", () => { touch(); render(); }));
  document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
    const p = b.dataset.preset;
    data.days.forEach((d, i) => {
      if (p === "all") hours[d.key] = [0, 24];
      else { const [a, z] = p.split("-").map(Number); hours[d.key] = i < 5 ? [a, z] : undefined; }
    });
    touch(); render();
  }));
  const bg = data.wallpaper;
  if (bg) $("oh-screen").style.backgroundImage = `url("/wallpapers/${encodeURIComponent(bg)}")`;
  $("oh-form").addEventListener("submit", () => { render(); dirty = false; });
  window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

  buildGrid();
  render();
})();
