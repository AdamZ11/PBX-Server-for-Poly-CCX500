// Live updates for the dashboard, the phone list and the phone page.
// Polls /api/live every 3 s while the tab is visible; no page reload needed.
(function () {
  "use strict";
  const page = document.body.dataset.live;
  if (!page) return;
  const INTERVAL = 3000;
  const OK_STATES = ["Reachable", "NonQualified", "Created"];

  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (sel, root = document) => root.querySelector(sel);
  const setHTML = (el, html) => { if (el && el.innerHTML !== html) el.innerHTML = html; };
  const setText = (sel, text) => { const el = $(sel); if (el && el.textContent !== String(text)) el.textContent = text; };
  const status = (dot, text) => `<span class="status"><span class="dot ${dot}"></span>${esc(text)}</span>`;
  const empty = (cols, text) => `<tr><td colspan="${cols}" class="muted">${esc(text)}</td></tr>`;

  function amiError(msg) {
    const box = $("#ami-error");
    if (!box) return;
    box.hidden = !msg;
    setText("#ami-error span", msg || "");
  }

  function server(s) {
    if (!s) return;
    setText("#srv-name", s.name);
    setText("#srv-meta", s.meta);
    const dot = $("#srv-dot");
    if (dot) dot.className = "dot " + (s.asterisk ? "free" : "off");
  }

  const render = {
    dashboard(d) {
      d.tiles.forEach((t) => {
        setText(`#tile-${t.id} b`, t.value);
        setText(`#tile-${t.id} small`, t.sub);
      });

      setHTML($("#ch-body"), d.channels.length ? d.channels.map((ch) => {
        const up = ch.state === "Up";
        return `<tr><td class="mono small">${esc(ch.channel)}</td>
          <td>${esc(ch.cid_name)} <span class="mono muted">${esc(ch.cid_num)}</span></td>
          <td class="mono">${esc(ch.exten)}</td><td class="mono">${esc(ch.duration)}</td>
          <td>${status(up ? "busy" : "ring", up ? "Beszélgetés" : ch.state)}</td></tr>`;
      }).join("") : empty(5, "Most nincs folyamatban lévő hívás."));

      setHTML($("#ext-list"), d.extensions.length ? d.extensions.map((e) => `
        <div class="row" style="min-height: 44px; border-bottom: 1px solid var(--ccx-divider); margin: 0">
          <a class="mono" href="/extensions/${esc(e.num)}" style="width: 48px">${esc(e.num)}</a>
          <span style="flex: 1">${esc(e.name)}</span>
          <span class="status small muted"><span class="dot ${esc(e.state)}"></span>${esc(e.label)}</span>
        </div>`).join("") : `<p class="muted">Még nincs mellék. <a href="/extensions/new">Vegyél fel egyet.</a></p>`);

      setHTML($("#reg-body"), d.contacts.length ? d.contacts.map((c) => `<tr>
        <td class="mono">${esc(c.endpoint)}</td>
        <td>${c.mac ? `<a href="/phones/${esc(c.mac)}" class="mono">${esc(c.mac)}</a>` : ""}</td>
        <td>${status(OK_STATES.includes(c.status) ? "free" : "off", c.status)}</td>
        <td class="mono small">${esc(c.uri)}</td>
        <td class="small">${esc(c.ua)}</td>
        <td class="mono">${c.rtt ? esc(c.rtt) + " ms" : ""}</td></tr>`).join("") : empty(6, "Még egy telefon sem regisztrált."));

      const unknown = $("#unknown-section");
      if (unknown) {
        unknown.hidden = !d.unknown.length;
        setHTML($("#unknown-body"), d.unknown.map((u) => `<tr><td class="mono">${esc(u.mac)}</td>
          <td class="mono">${esc(u.ip)}</td><td>${esc(u.model)}</td><td class="mono">${esc(u.firmware)}</td>
          <td class="mono">${esc(u.last_seen)}</td>
          <td class="right"><a class="btn secondary" href="/phones/new?mac=${encodeURIComponent(u.mac)}">Felvétel</a></td></tr>`).join(""));
      }
      const regs = $("#regs-section");
      if (regs) {
        regs.hidden = !d.regs.length;
        setHTML($("#regs-body"), d.regs.map((r) =>
          `<tr><td>${esc(r.name)}</td><td class="mono">${esc(r.server)}</td><td>${esc(r.status)}</td></tr>`).join(""));
      }
    },

    phones(d) {
      document.querySelectorAll("tr[data-mac]").forEach((row) => {
        const p = d.phones[row.dataset.mac];
        if (!p) return;
        setHTML($(".js-status", row), !p.ext ? status("off", "nincs vonal")
          : p.registered ? status("free", "Regisztrált") : status("off", "Offline"));
        setHTML($(".js-ip", row), esc(p.ip));
        setHTML($(".js-fw", row), esc(p.firmware));
        setHTML($(".js-seen", row), esc(p.last_seen));
      });
    },

    phone(d) {
      const box = $("#phone-live");
      if (!box) return;
      const p = d.phones[box.dataset.mac];
      if (!p) return;
      setHTML($(".js-sip", box), p.registered
        ? `${status("free", p.contact_status)} <span class="mono small">${esc(p.contact_uri)}</span>`
        : box.dataset.hasLines === "1" ? status("off", "Nincs regisztrálva") : status("off", "Nincs vonal rendelve"));
      setHTML($(".js-ip", box), p.ip
        ? `<span class="mono">${esc(p.ip)}</span> · <a href="https://${esc(p.ip)}" target="_blank" rel="noopener">telefon webfelülete</a>` : "–");
      setHTML($(".js-model", box), `${esc(p.model)} <span class="mono">${esc(p.firmware)}</span>`);
      setHTML($(".js-ua", box), esc(p.user_agent));
      setHTML($(".js-seen", box), `<span class="mono">${esc(p.last_seen)}</span> (${esc(p.last_file)})`);
    },
  };

  const indicator = $("#live-indicator");
  let busy = false;

  async function tick() {
    if (document.hidden || busy) return;
    busy = true;
    try {
      const r = await fetch("/api/live", { headers: { Accept: "application/json" }, cache: "no-store" });
      if (r.redirected || r.status === 401) { location.href = "/login"; return; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      render[page](d);
      amiError(d.ami_error);
      server(d.server);
      if (indicator) { indicator.textContent = "Élő · " + d.time; indicator.className = "live ok"; }
    } catch (e) {
      if (indicator) { indicator.textContent = "Nincs kapcsolat a szerverrel"; indicator.className = "live err"; }
    } finally {
      busy = false;
    }
  }

  setInterval(tick, INTERVAL);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
})();
