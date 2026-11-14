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
  const pill = (cls, text) => `<span class="pill ${cls}">${esc(text)}</span>`;
  const empty = (cols, text) => `<tr><td colspan="${cols}" class="muted">${esc(text)}</td></tr>`;

  function amiError(msg) {
    const box = $("#ami-error");
    if (!box) return;
    box.hidden = !msg;
    setText("#ami-error span", msg || "");
  }

  const render = {
    dashboard(d) {
      setText("#t-extensions", d.counts.extensions);
      setText("#t-phones", d.counts.phones);
      setText("#t-registered", d.counts.registered);
      setText("#t-channels", d.counts.channels);

      setHTML($("#reg-body"), d.contacts.length ? d.contacts.map((c) => `<tr>
        <td>${esc(c.endpoint)}</td>
        <td>${c.mac ? `<a href="/phones/${esc(c.mac)}" class="mono">${esc(c.mac)}</a>` : ""}</td>
        <td>${pill(OK_STATES.includes(c.status) ? "ok" : "err", c.status)}</td>
        <td class="mono small">${esc(c.uri)}</td>
        <td class="small">${esc(c.ua)}</td>
        <td>${c.rtt ? esc(c.rtt) + " ms" : ""}</td></tr>`).join("") : empty(6, "Nincs regisztrált készülék."));

      setHTML($("#ch-body"), d.channels.length ? d.channels.map((ch) => `<tr>
        <td class="mono small">${esc(ch.channel)}</td><td>${esc(ch.cid_name)} &lt;${esc(ch.cid_num)}&gt;</td>
        <td>${esc(ch.exten)}</td><td>${esc(ch.state)}</td><td>${esc(ch.duration)}</td></tr>`).join("")
        : empty(5, "Nincs aktív hívás."));

      const unknown = $("#unknown-section");
      if (unknown) {
        unknown.hidden = !d.unknown.length;
        setHTML($("#unknown-body"), d.unknown.map((u) => `<tr><td class="mono">${esc(u.mac)}</td>
          <td>${esc(u.ip)}</td><td>${esc(u.model)}</td><td>${esc(u.firmware)}</td><td>${esc(u.last_seen)}</td>
          <td><a class="btn" href="/phones/new?mac=${encodeURIComponent(u.mac)}">Felvétel</a></td></tr>`).join(""));
      }
      const regs = $("#regs-section");
      if (regs) {
        regs.hidden = !d.regs.length;
        setHTML($("#regs-body"), d.regs.map((r) =>
          `<tr><td>${esc(r.name)}</td><td>${esc(r.server)}</td><td>${esc(r.status)}</td></tr>`).join(""));
      }
    },

    phones(d) {
      document.querySelectorAll("tr[data-mac]").forEach((row) => {
        const p = d.phones[row.dataset.mac];
        if (!p) return;
        setHTML($(".js-status", row), !p.ext ? pill("", "nincs vonal")
          : p.registered ? pill("ok", "regisztrált") : pill("err", "offline"));
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
        ? `${pill("ok", p.contact_status)} <span class="mono small">${esc(p.contact_uri)}</span>`
        : box.dataset.hasLines === "1" ? pill("err", "nincs regisztrálva") : pill("", "nincs vonal rendelve"));
      setHTML($(".js-ip", box), p.ip
        ? `${esc(p.ip)} <a href="https://${esc(p.ip)}" target="_blank" rel="noopener">telefon webfelülete ↗</a>` : "-");
      setHTML($(".js-model", box), `${esc(p.model)} ${esc(p.firmware)}`);
      setHTML($(".js-ua", box), esc(p.user_agent));
      setHTML($(".js-seen", box), `${esc(p.last_seen)} (${esc(p.last_file)})`);
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
      if (indicator) { indicator.textContent = "● élő · " + d.time; indicator.className = "live ok"; }
    } catch (e) {
      if (indicator) { indicator.textContent = "● nincs kapcsolat a szerverrel"; indicator.className = "live err"; }
    } finally {
      busy = false;
    }
  }

  setInterval(tick, INTERVAL);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
})();
