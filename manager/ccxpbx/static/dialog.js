// Styled confirmation dialog instead of the browser's own confirm() box.
//   await ccxConfirm("Törlöd?", { ok: "Törlés", danger: true, title: "Mellék törlése" })  -> true / false
// Forms: <form data-confirm="Törlöd?" data-ok="Törlés" data-danger> asks before submitting.
(function () {
  "use strict";
  let dlg = null, resolveFn = null;

  function finish(yes) {
    // decided by the buttons themselves: some browsers do not fire "close" reliably
    if (dlg.open) dlg.close();
    const fn = resolveFn;
    resolveFn = null;
    if (fn) fn(yes);
  }

  function build() {
    dlg = document.createElement("dialog");
    dlg.className = "ccx-dialog";
    dlg.setAttribute("aria-labelledby", "ccx-dialog-title");
    dlg.innerHTML = `
      <div class="ccx-dialog-body">
        <h2 id="ccx-dialog-title"></h2>
        <p class="ccx-dialog-msg"></p>
        <div class="ccx-dialog-actions">
          <button type="button" class="secondary" data-role="cancel">Mégse</button>
          <button type="button" data-role="ok">OK</button>
        </div>
      </div>`;
    document.body.appendChild(dlg);
    dlg.querySelector('[data-role="ok"]').addEventListener("click", () => finish(true));
    dlg.querySelector('[data-role="cancel"]').addEventListener("click", () => finish(false));
    dlg.addEventListener("cancel", (ev) => { ev.preventDefault(); finish(false); });        // Esc
    dlg.addEventListener("close", () => finish(false));                                      // any other way out
    dlg.addEventListener("click", (ev) => { if (ev.target === dlg) finish(false); });         // backdrop
  }

  window.ccxConfirm = function (message, opts = {}) {
    if (!dlg) build();
    if (typeof dlg.showModal !== "function") return Promise.resolve(window.confirm(message));   // very old browser
    if (resolveFn) { const fn = resolveFn; resolveFn = null; fn(false); }
    dlg.querySelector("h2").textContent = opts.title || (opts.danger ? "Biztos vagy benne?" : "Megerősítés");
    dlg.querySelector(".ccx-dialog-msg").textContent = message;
    const ok = dlg.querySelector('[data-role="ok"]'), cancel = dlg.querySelector('[data-role="cancel"]');
    ok.textContent = opts.ok || "Igen";
    cancel.textContent = opts.cancel || "Mégse";
    ok.classList.toggle("danger", !!opts.danger);
    dlg.showModal();
    (opts.danger ? cancel : ok).focus();   // a destructive action is never one Enter away
    return new Promise((res) => { resolveFn = res; });
  };

  document.addEventListener("submit", async (ev) => {
    const form = ev.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.confirm || form.dataset.confirmed === "1") return;
    ev.preventDefault();
    const yes = await window.ccxConfirm(form.dataset.confirm, {
      ok: form.dataset.ok, danger: "danger" in form.dataset, title: form.dataset.title });
    if (!yes) return;
    form.dataset.confirmed = "1";
    if (form.requestSubmit) form.requestSubmit(ev.submitter || undefined); else form.submit();
    delete form.dataset.confirmed;
  });
})();
