"""Admin web UI (Hungarian)."""
import json
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import ami, asterisk_gen, config, db, httpauth, plan, poly, polyrest, services
from .services import get_db

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals.update(plan=plan, KEY_TYPES=plan.KEY_TYPES)

_failed_logins: dict[str, list[float]] = {}


class LoginRequired(Exception):
    pass


def require_login(request: Request):
    if not request.session.get("user"):
        raise LoginRequired()
    return request.session["user"]


def flash(request: Request, message: str, kind: str = "ok"):
    request.session["flash"] = request.session.get("flash", []) + [[kind, message]]


def render(request: Request, conn, name: str, **ctx) -> HTMLResponse:
    settings = db.get_settings(conn)
    ctx.update(
        request=request,
        settings=settings,
        dirty=settings.get("dirty") == "1",
        restart_required=settings.get("restart_required") == "1",
        flashes=request.session.pop("flash", []),
        user=request.session.get("user"),
    )
    return templates.TemplateResponse(request, name, ctx)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def fval(form, key: str, default: str = "") -> str:
    value = form.get(key)
    return value.strip() if isinstance(value, str) else default


def fbool(form, key: str) -> int:
    return 1 if form.get(key) in ("1", "on", "yes", "true") else 0


def fint(form, key: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(fval(form, key, str(default)))))
    except ValueError:
        return default


def valid_dest(conn, dest: str) -> str:
    dest = dest.strip()
    if not dest:
        return ""
    target = dest[3:] if dest.startswith("vm:") else dest
    if dest.startswith("vm:"):
        ok = conn.execute("SELECT 1 FROM extensions WHERE ext=? AND vm_enabled=1", (target,)).fetchone()
    else:
        ok = (conn.execute("SELECT 1 FROM extensions WHERE ext=?", (target,)).fetchone()
              or conn.execute("SELECT 1 FROM ring_groups WHERE num=?", (target,)).fetchone()
              or target in plan.CONF_ROOMS)
    if not ok:
        raise plan.ValidationError(f"Ismeretlen cél: {dest!r} (mellék, csoport, 800-809 vagy vm:mellék)")
    return dest


def number_in_use(conn, num: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM extensions WHERE ext=?", (num,)).fetchone()
                or conn.execute("SELECT 1 FROM ring_groups WHERE num=?", (num,)).fetchone())


# ---------------------------------------------------------------- auth
@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, conn=Depends(get_db)):
    return render(request, conn, "login.html")


@router.post("/login")
async def login(request: Request, conn=Depends(get_db)):
    form = await request.form()
    ip = request.client.host if request.client else "?"
    now = time.time()
    attempts = [t for t in _failed_logins.get(ip, []) if now - t < 300]
    if len(attempts) >= 5:
        flash(request, "Túl sok sikertelen próbálkozás, várj 5 percet.", "err")
        return redirect("/login")
    stored = db.get_settings(conn).get("admin_password_hash", "")
    if fval(form, "username") == "admin" and stored and httpauth.verify_password(fval(form, "password"), stored):
        _failed_logins.pop(ip, None)
        request.session.clear()
        request.session["user"] = "admin"
        return redirect("/")
    _failed_logins[ip] = attempts + [now]
    flash(request, "Hibás felhasználónév vagy jelszó.", "err")
    return redirect("/login")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


# ---------------------------------------------------------------- dashboard
@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    def collect(a):
        return {"contacts": a.contacts(), "channels": a.channels(), "regs": a.registrations()}

    live, err = await run_in_threadpool(ami.safe_call, collect, {"contacts": [], "channels": [], "regs": []})
    phones = {r["ext"]: r["mac"] for r in conn.execute("SELECT ext, mac FROM phone_lines")}
    unknown = conn.execute(
        "SELECT * FROM seen_devices WHERE mac NOT IN (SELECT mac FROM phones) ORDER BY last_seen DESC"
    ).fetchall()
    counts = {
        "extensions": conn.execute("SELECT COUNT(*) FROM extensions").fetchone()[0],
        "phones": conn.execute("SELECT COUNT(*) FROM phones").fetchone()[0],
    }
    mismatch = services.server_host_mismatch(db.get_settings(conn)["server_host"])
    return render(request, conn, "dashboard.html", live=live, ami_error=err, phones=phones,
                  unknown=unknown, counts=counts, ip_mismatch=mismatch)


# ---------------------------------------------------------------- extensions
@router.get("/extensions", response_class=HTMLResponse)
def ext_list(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    rows = conn.execute(
        "SELECT e.*, GROUP_CONCAT(l.mac) AS macs FROM extensions e "
        "LEFT JOIN phone_lines l ON l.ext = e.ext GROUP BY e.ext ORDER BY e.ext"
    ).fetchall()
    return render(request, conn, "extensions.html", rows=rows)


@router.get("/extensions/new", response_class=HTMLResponse)
def ext_new(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    last = conn.execute("SELECT MAX(CAST(ext AS INTEGER)) FROM extensions").fetchone()[0]
    ext = {"ext": str((last or 2000) + 1), "name": "", "secret": "", "vm_enabled": 1, "vm_pin": db.gen_pin(),
           "email": "", "ring_time": 25, "record": 0, "pickup_group": "1", "max_contacts": 1,
           "in_directory": 1, "page_member": 1}
    return render(request, conn, "extension_form.html", ext=ext, is_new=True)


@router.get("/extensions/{ext}", response_class=HTMLResponse)
def ext_edit(ext: str, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    row = conn.execute("SELECT * FROM extensions WHERE ext=?", (ext,)).fetchone()
    if not row:
        return redirect("/extensions")
    return render(request, conn, "extension_form.html", ext=dict(row), is_new=False)


@router.post("/extensions/save")
async def ext_save(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    form = await request.form()
    is_new = fval(form, "is_new") == "1"
    try:
        ext = plan.check_ext(fval(form, "ext"))
        name = plan.clean_text(fval(form, "name"))
        if not name:
            raise plan.ValidationError("A név kötelező.")
        existing = conn.execute("SELECT * FROM extensions WHERE ext=?", (ext,)).fetchone()
        if is_new and number_in_use(conn, ext):
            raise plan.ValidationError(f"A {ext} szám már foglalt.")
        if not is_new and not existing:
            raise plan.ValidationError("Nem létező mellék.")
        secret = fval(form, "secret") or (existing["secret"] if existing else db.gen_secret(20))
        if len(secret) < 12 or not re.fullmatch(r"[A-Za-z0-9]+", secret):
            raise plan.ValidationError("A SIP jelszó legalább 12 karakter, csak betű és szám.")
        vm_pin = fval(form, "vm_pin") or db.gen_pin()
        if not re.fullmatch(r"[0-9]{4,10}", vm_pin):
            raise plan.ValidationError("A hangposta PIN 4-10 számjegy.")
        email = fval(form, "email")
        if email and not re.fullmatch(r"[^@\s;,]+@[^@\s;,]+\.[A-Za-z]{2,}", email):
            raise plan.ValidationError("Érvénytelen e-mail cím.")
        group = fval(form, "pickup_group", "1")
        if not re.fullmatch(r"[0-9]{1,2}(,[0-9]{1,2})*", group):
            raise plan.ValidationError("Felvételi csoport: számok vesszővel elválasztva (pl. 1 vagy 1,2).")
    except plan.ValidationError as exc:
        flash(request, str(exc), "err")
        return redirect("/extensions/new" if is_new else f"/extensions/{fval(form, 'ext')}")
    values = (name, secret, fbool(form, "vm_enabled"), vm_pin, email, fint(form, "ring_time", 25, 5, 120),
              fbool(form, "record"), group, fint(form, "max_contacts", 1, 1, 5),
              fbool(form, "in_directory"), fbool(form, "page_member"), ext)
    if existing:
        conn.execute("UPDATE extensions SET name=?, secret=?, vm_enabled=?, vm_pin=?, email=?, ring_time=?, "
                     "record=?, pickup_group=?, max_contacts=?, in_directory=?, page_member=? WHERE ext=?", values)
    else:
        conn.execute("INSERT INTO extensions(name, secret, vm_enabled, vm_pin, email, ring_time, record, "
                     "pickup_group, max_contacts, in_directory, page_member, ext) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     values)
    db.mark_dirty(conn)
    flash(request, f"{ext} mellék mentve.")
    return redirect("/extensions")


@router.post("/extensions/{ext}/delete")
def ext_delete(ext: str, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    conn.execute("DELETE FROM extensions WHERE ext=?", (ext,))
    db.mark_dirty(conn)
    flash(request, f"{ext} mellék törölve.")
    return redirect("/extensions")


# ---------------------------------------------------------------- phones
@router.get("/phones", response_class=HTMLResponse)
async def phone_list(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    contacts, err = await run_in_threadpool(ami.safe_call, lambda a: a.contacts(), [])
    registered = {c.get("Endpoint"): c for c in contacts or []}
    phones = []
    for row in conn.execute("SELECT * FROM phones ORDER BY label, mac"):
        p = db.load_phone(conn, row["mac"])
        seen = conn.execute("SELECT * FROM seen_devices WHERE mac=?", (row["mac"],)).fetchone()
        p["seen"] = dict(seen) if seen else None
        p["registered"] = bool(p["lines"]) and p["lines"][0]["ext"] in registered
        phones.append(p)
    return render(request, conn, "phones.html", phones=phones, ami_error=err)


def _phone_form_ctx(conn, phone: dict) -> dict:
    exts = conn.execute("SELECT ext, name FROM extensions ORDER BY ext").fetchall()
    keys = {k["pos"]: k for k in phone.get("keys", [])}
    lines = {l["idx"]: l for l in phone.get("lines", [])}
    return {"phone": phone, "exts": exts, "keys": keys, "lines": lines}


@router.get("/phones/new", response_class=HTMLResponse)
def phone_new(request: Request, mac: str = "", conn=Depends(get_db), _=Depends(require_login)):
    phone = {"mac": mac, "label": "", "model": "CCX500", "overrides": "", "notes": "", "lines": [], "keys": []}
    return render(request, conn, "phone_form.html", is_new=True, **_phone_form_ctx(conn, phone))


@router.get("/phones/{mac}", response_class=HTMLResponse)
async def phone_edit(mac: str, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    phone = db.load_phone(conn, mac)
    if not phone:
        return redirect("/phones")
    contacts, err = await run_in_threadpool(ami.safe_call, lambda a: a.contacts(), [])
    ext = phone["lines"][0]["ext"] if phone["lines"] else None
    contact = next((c for c in contacts or [] if c.get("Endpoint") == ext), None)
    seen = conn.execute("SELECT * FROM seen_devices WHERE mac=?", (mac,)).fetchone()
    return render(request, conn, "phone_form.html", is_new=False, contact=contact, ami_error=err,
                  seen=seen, ip=services.phone_ip(conn, mac, contacts or []),
                  files=services.uploaded_files(mac), **_phone_form_ctx(conn, phone))


@router.post("/phones/save")
async def phone_save(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    form = await request.form()
    is_new = fval(form, "is_new") == "1"
    raw_mac = fval(form, "mac")
    try:
        mac = plan.normalize_mac(raw_mac)
        exists = conn.execute("SELECT 1 FROM phones WHERE mac=?", (mac,)).fetchone()
        if is_new and exists:
            raise plan.ValidationError("Ez a telefon már fel van véve.")
        lines = []
        for i in range(1, plan.MAX_LINES + 1):
            ext = fval(form, f"line_ext_{i}")
            if not ext:
                continue
            if not conn.execute("SELECT 1 FROM extensions WHERE ext=?", (ext,)).fetchone():
                raise plan.ValidationError(f"Ismeretlen mellék: {ext}")
            lines.append((len(lines) + 1, ext, fint(form, f"line_keys_{i}", 1, 1, 8)))
        keys = []
        for pos in range(1, plan.MAX_KEYS + 1):
            ktype = fval(form, f"key_type_{pos}")
            if not ktype:
                continue
            if ktype not in plan.KEY_TYPES:
                raise plan.ValidationError(f"{pos}. gomb: ismeretlen típus")
            value = fval(form, f"key_value_{pos}")
            label = plan.clean_text(fval(form, f"key_label_{pos}"), 24)
            if ktype == "line":
                if not value.isdigit() or not 1 <= int(value) <= max(len(lines), 1):
                    raise plan.ValidationError(f"{pos}. gomb: a vonal sorszáma 1..{max(len(lines), 1)}")
            elif ktype in ("blf", "speeddial"):
                if not plan.DIAL_RE.match(value):
                    raise plan.ValidationError(f"{pos}. gomb: érvénytelen hívószám ({value!r})")
            else:
                value = ""
            keys.append((pos, ktype, value, label))
        overrides = form.get("overrides") or ""
        plan.parse_params(overrides)
    except plan.ValidationError as exc:
        flash(request, str(exc), "err")
        return redirect(f"/phones/new?mac={raw_mac}" if is_new else f"/phones/{raw_mac}")

    label, notes = plan.clean_text(fval(form, "label")), (form.get("notes") or "")[:1000]
    if exists:
        conn.execute("UPDATE phones SET label=?, overrides=?, notes=? WHERE mac=?", (label, overrides, notes, mac))
    else:
        conn.execute("INSERT INTO phones(mac, label, overrides, notes) VALUES (?,?,?,?)", (mac, label, overrides, notes))
    conn.execute("DELETE FROM phone_lines WHERE mac=?", (mac,))
    conn.execute("DELETE FROM phone_keys WHERE mac=?", (mac,))
    conn.executemany("INSERT INTO phone_lines(mac, idx, ext, line_keys) VALUES (?,?,?,?)",
                     [(mac, *line) for line in lines])
    conn.executemany("INSERT INTO phone_keys(mac, pos, type, value, label) VALUES (?,?,?,?,?)",
                     [(mac, *key) for key in keys])
    db.mark_dirty(conn)
    flash(request, "Telefon mentve. A telefon a következő szinkronizáláskor (Szinkronizálás gomb) kapja meg.")
    return redirect(f"/phones/{mac}")


@router.post("/phones/{mac}/autokeys")
def phone_autokeys(mac: str, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    phone = db.load_phone(conn, mac)
    if not phone:
        return redirect("/phones")
    own = {l["ext"] for l in phone["lines"]}
    keys = [("line", str(l["idx"]), "") for l in phone["lines"]]
    keys.append(("park", "", "Park"))
    keys += [("blf", r["ext"], r["name"][:24]) for r in
             conn.execute("SELECT ext, name FROM extensions ORDER BY ext") if r["ext"] not in own]
    keys += [("blf", slot, f"Park {slot}") for slot in plan.PARK_SLOTS[:3]]
    conn.execute("DELETE FROM phone_keys WHERE mac=?", (mac,))
    conn.executemany("INSERT INTO phone_keys(mac, pos, type, value, label) VALUES (?,?,?,?,?)",
                     [(mac, pos, *k) for pos, k in enumerate(keys[: plan.MAX_KEYS], 1)])
    db.mark_dirty(conn)
    flash(request, "Automatikus gombkiosztás elkészült (vonalak, park, BLF minden mellékre, park helyek).")
    return redirect(f"/phones/{mac}")


@router.post("/phones/{mac}/delete")
def phone_delete(mac: str, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    conn.execute("DELETE FROM phones WHERE mac=?", (mac,))
    db.mark_dirty(conn)
    flash(request, "Telefon törölve.")
    return redirect("/phones")


@router.post("/phones/{mac}/action/{action}")
async def phone_action(mac: str, action: str, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    if not conn.execute("SELECT 1 FROM phones WHERE mac=?", (mac,)).fetchone():
        return redirect("/phones")
    settings = db.get_settings(conn)
    if action in ("resync", "reboot"):
        err = await run_in_threadpool(services.notify_phone, conn, mac, action == "reboot")
        flash(request, err or ("Szinkronizálási kérés elküldve (check-sync)." if action == "resync"
                               else "Újraindítási kérés elküldve."), "err" if err else "ok")
    elif action in ("restart", "safe-reboot"):
        ip = await run_in_threadpool(services.phone_ip, conn, mac)
        try:
            await run_in_threadpool(polyrest.run, ip, settings["phone_admin_password"],
                                    "restart" if action == "restart" else "reboot")
            flash(request, f"REST parancs elküldve a telefonnak ({ip}).")
        except polyrest.PolyRestError as exc:
            flash(request, str(exc), "err")
    elif action == "clear-overrides":
        removed = 0
        for f in (config.PROV_DIR / "overrides").glob(f"{mac}*"):
            f.unlink()
            removed += 1
        flash(request, f"{removed} telefon oldali override fájl törölve. Szinkronizáld a telefont.")
    elif action == "dial":
        form = await request.form()
        number = fval(form, "number")
        if not plan.DIAL_RE.match(number):
            flash(request, "Érvénytelen szám.", "err")
        else:
            ip = await run_in_threadpool(services.phone_ip, conn, mac)
            try:
                await run_in_threadpool(polyrest.dial, ip, settings["phone_admin_password"], number)
                flash(request, f"Hívás indítva a telefonról: {number}")
            except polyrest.PolyRestError as exc:
                flash(request, str(exc), "err")
    return redirect(f"/phones/{mac}")


@router.get("/phones/{mac}/rest/{name}", response_class=HTMLResponse)
async def phone_rest(mac: str, name: str, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    if name not in ("info", "network", "lines", "calls"):
        return redirect(f"/phones/{mac}")
    ip = await run_in_threadpool(services.phone_ip, conn, mac)
    try:
        data = await run_in_threadpool(polyrest.run, ip, db.get_settings(conn)["phone_admin_password"], name)
        text, error = json.dumps(data, indent=2, ensure_ascii=False), None
    except polyrest.PolyRestError as exc:
        text, error = "", str(exc)
    return render(request, conn, "text_view.html", title=f"{mac} - REST {name} ({ip})", text=text,
                  error=error, back=f"/phones/{mac}")


@router.get("/phones/{mac}/config", response_class=HTMLResponse)
def phone_config(mac: str, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    phone = db.load_phone(conn, mac)
    if not phone:
        return redirect("/phones")
    snap = db.snapshot(conn)
    text = (f"=== {mac}.cfg ===\n{poly.render_master(snap['settings'], mac)}\n"
            f"=== ccx/{mac}-phone.cfg ===\n{poly.render_cfg(poly.phone_params(snap, phone))}\n"
            f"=== ccx/site.cfg ===\n{poly.render_cfg(poly.site_params(snap))}")
    return render(request, conn, "text_view.html", title=f"{mac} generált konfiguráció", text=text,
                  back=f"/phones/{mac}")


@router.get("/phones/{mac}/files/{sub}/{name}", response_class=HTMLResponse)
def phone_file(mac: str, sub: str, name: str, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    if sub not in config.UPLOAD_DIRS or mac not in name or "/" in name or ".." in name:
        return redirect(f"/phones/{mac}")
    f = config.PROV_DIR / sub / name
    if not f.is_file():
        return redirect(f"/phones/{mac}")
    if f.suffix in (".gz", ".tar", ".zip"):
        return FileResponse(f, filename=name)
    data = f.read_bytes()[-200_000:].decode("utf-8", "replace")
    return render(request, conn, "text_view.html", title=f"{sub}/{name}", text=data, back=f"/phones/{mac}")


# ---------------------------------------------------------------- ring groups
@router.get("/ringgroups", response_class=HTMLResponse)
def rg_list(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    return render(request, conn, "ringgroups.html", rows=conn.execute("SELECT * FROM ring_groups ORDER BY num"))


@router.get("/ringgroups/new", response_class=HTMLResponse)
@router.get("/ringgroups/{num}", response_class=HTMLResponse)
def rg_form(request: Request, num: str | None = None, conn=Depends(get_db), _=Depends(require_login)):
    row = conn.execute("SELECT * FROM ring_groups WHERE num=?", (num,)).fetchone() if num else None
    group = dict(row) if row else {"num": "6000", "name": "", "strategy": "ringall", "ring_time": 20,
                                   "members": "", "failover": ""}
    exts = conn.execute("SELECT ext, name FROM extensions ORDER BY ext").fetchall()
    return render(request, conn, "ringgroup_form.html", group=group, exts=exts, is_new=row is None,
                  members=set(group["members"].split(",")))


@router.post("/ringgroups/save")
async def rg_save(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    form = await request.form()
    is_new = fval(form, "is_new") == "1"
    try:
        num = plan.check_ext(fval(form, "num"))
        if is_new and number_in_use(conn, num):
            raise plan.ValidationError(f"A {num} szám már foglalt.")
        name = plan.clean_text(fval(form, "name")) or num
        strategy = fval(form, "strategy")
        if strategy not in ("ringall", "hunt"):
            raise plan.ValidationError("Ismeretlen stratégia.")
        members = [m for m in form.getlist("members")
                   if conn.execute("SELECT 1 FROM extensions WHERE ext=?", (m,)).fetchone()]
        failover = valid_dest(conn, fval(form, "failover"))
        if failover == num:
            raise plan.ValidationError("A csoport nem lehet saját maga tartalék célja.")
    except plan.ValidationError as exc:
        flash(request, str(exc), "err")
        return redirect("/ringgroups")
    conn.execute(
        "INSERT INTO ring_groups(num, name, strategy, ring_time, members, failover) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(num) DO UPDATE SET name=excluded.name, strategy=excluded.strategy, "
        "ring_time=excluded.ring_time, members=excluded.members, failover=excluded.failover",
        (num, name, strategy, fint(form, "ring_time", 20, 5, 300), ",".join(members), failover))
    db.mark_dirty(conn)
    flash(request, f"{num} csoport mentve.")
    return redirect("/ringgroups")


@router.post("/ringgroups/{num}/delete")
def rg_delete(num: str, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    conn.execute("DELETE FROM ring_groups WHERE num=?", (num,))
    db.mark_dirty(conn)
    return redirect("/ringgroups")


# ---------------------------------------------------------------- trunks & routes
@router.get("/trunks", response_class=HTMLResponse)
async def trunk_list(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    regs, err = await run_in_threadpool(ami.safe_call, lambda a: a.registrations(), [])
    status = {r.get("ObjectName", "").removesuffix("-reg"): r.get("Status", "") for r in regs or []}
    return render(request, conn, "trunks.html", rows=conn.execute("SELECT * FROM trunks ORDER BY name").fetchall(),
                  status=status, ami_error=err,
                  inbound=conn.execute("SELECT * FROM inbound_routes ORDER BY did").fetchall(),
                  outbound=conn.execute("SELECT * FROM outbound_routes ORDER BY pattern").fetchall())


@router.post("/trunks/save")
async def trunk_save(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    form = await request.form()
    try:
        name = fval(form, "name").lower()
        if not plan.TRUNK_RE.match(name) or number_in_use(conn, name):
            raise plan.ValidationError("A trönk neve: kisbetű, szám, - és _ (max 32).")
        host = fval(form, "host")
        if not plan.HOST_RE.match(host):
            raise plan.ValidationError("Érvénytelen szerver cím.")
        codecs = ",".join(c for c in fval(form, "codecs", "alaw,ulaw").split(",") if c in poly.CODEC_MAP)
        existing = conn.execute("SELECT password FROM trunks WHERE name=?", (name,)).fetchone()
        password = fval(form, "password") or (existing["password"] if existing else "")
        fields = [fval(form, k) for k in ("username", "from_user", "from_domain", "callerid")]
        if any(re.search(r"[\s;\"<>]", v) for v in fields):
            raise plan.ValidationError("A felhasználónév / from / hívóazonosító mezők nem tartalmazhatnak szóközt.")
    except plan.ValidationError as exc:
        flash(request, str(exc), "err")
        return redirect("/trunks")
    conn.execute(
        "INSERT INTO trunks(name, host, port, username, password, register, from_user, from_domain, callerid, codecs) "
        "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET host=excluded.host, port=excluded.port, "
        "username=excluded.username, password=excluded.password, register=excluded.register, "
        "from_user=excluded.from_user, from_domain=excluded.from_domain, callerid=excluded.callerid, "
        "codecs=excluded.codecs",
        (name, host, fint(form, "port", 5060, 1, 65535), fields[0], password, fbool(form, "register"),
         fields[1], fields[2], fields[3], codecs or "alaw,ulaw"))
    db.mark_dirty(conn)
    flash(request, f"{name} trönk mentve.")
    return redirect("/trunks")


@router.post("/trunks/{name}/delete")
def trunk_delete(name: str, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    conn.execute("DELETE FROM trunks WHERE name=?", (name,))
    db.mark_dirty(conn)
    return redirect("/trunks")


@router.post("/routes/inbound")
async def inbound_save(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    form = await request.form()
    try:
        did = fval(form, "did")
        if not re.fullmatch(r"\+?[0-9]{2,20}", did):
            raise plan.ValidationError("A DID csak számjegyekből állhat (opcionális + előtaggal).")
        dest = valid_dest(conn, fval(form, "destination"))
        if not dest:
            raise plan.ValidationError("A cél kötelező.")
    except plan.ValidationError as exc:
        flash(request, str(exc), "err")
        return redirect("/trunks")
    conn.execute("INSERT INTO inbound_routes(did, destination) VALUES (?,?) "
                 "ON CONFLICT(did) DO UPDATE SET destination=excluded.destination", (did, dest))
    db.mark_dirty(conn)
    return redirect("/trunks")


@router.post("/routes/outbound")
async def outbound_save(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    form = await request.form()
    try:
        pattern = fval(form, "pattern")
        if not plan.PATTERN_RE.match(pattern):
            raise plan.ValidationError("Érvénytelen minta (pl. _0. vagy 112).")
        trunk = fval(form, "trunk")
        if not conn.execute("SELECT 1 FROM trunks WHERE name=?", (trunk,)).fetchone():
            raise plan.ValidationError("Előbb vegyél fel egy trönköt.")
        prepend = fval(form, "prepend")
        if prepend and not plan.DIAL_RE.match(prepend):
            raise plan.ValidationError("Érvénytelen előtag.")
    except plan.ValidationError as exc:
        flash(request, str(exc), "err")
        return redirect("/trunks")
    conn.execute("INSERT INTO outbound_routes(pattern, strip, prepend, trunk) VALUES (?,?,?,?) "
                 "ON CONFLICT(pattern) DO UPDATE SET strip=excluded.strip, prepend=excluded.prepend, "
                 "trunk=excluded.trunk", (pattern, fint(form, "strip", 0, 0, 10), prepend, trunk))
    db.mark_dirty(conn)
    return redirect("/trunks")


@router.post("/routes/{kind}/{rid}/delete")
def route_delete(kind: str, rid: int, request: Request, conn=Depends(get_db), _=Depends(require_login)):
    table = {"inbound": "inbound_routes", "outbound": "outbound_routes"}.get(kind)
    if table:
        conn.execute(f"DELETE FROM {table} WHERE id=?", (rid,))
        db.mark_dirty(conn)
    return redirect("/trunks")


# ---------------------------------------------------------------- settings
SETTING_RULES = {
    "server_host": plan.HOST_RE,
    "http_port": re.compile(r"^[0-9]{2,5}$"),
    "sip_port": re.compile(r"^[0-9]{2,5}$"),
    "tls_port": re.compile(r"^[0-9]{2,5}$"),
    "sip_transport": re.compile(r"^(udp|tcp|tls)$"),
    "reg_expires": re.compile(r"^[0-9]{2,5}$"),
    "external_ip": re.compile(r"^([0-9.]{7,15})?$"),
    "local_net": re.compile(r"^[0-9./, ]*$"),
    "codecs": re.compile(r"^(opus|g722|alaw|ulaw|g729)(,(opus|g722|alaw|ulaw|g729))*$"),
    "tone_zone": re.compile(r"^[a-z]{2,6}$"),
    "timezone_name": re.compile(r"^[A-Za-z_]+(/[A-Za-z_+\-]+)*$"),
    "prov_auth": re.compile(r"^(none|basic|digest)$"),
    "prov_user": re.compile(r"^[A-Za-z0-9._-]{3,32}$"),
    "prov_password": re.compile(r"^[A-Za-z0-9]{8,64}$"),
    "prov_polling_time": re.compile(r"^[0-2][0-9]:[0-5][0-9]$"),
    "phone_admin_password": re.compile(r"^[A-Za-z0-9]{6,32}$"),
    "phone_user_password": re.compile(r"^[A-Za-z0-9]{0,32}$"),
    "base_profile": re.compile(r"^(Generic)$"),
    "ntp_server": plan.HOST_RE,
    "gmt_offset": re.compile(r"^-?[0-9]{1,5}$"),
    "dst_rule": re.compile(r"^(eu|us|none)$"),
    "language": re.compile(r"^[A-Za-z_]{0,40}$"),
    "digitmap": re.compile(r"^[0-9xXtT.*#|\[\]\-+R]*$"),
    "paging_address": re.compile(r"^2(2[4-9]|3[0-9])\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$"),
    "paging_port": re.compile(r"^[0-9]{2,5}$"),
    "firmware_file": re.compile(r"^[A-Za-z0-9._-]{0,128}$"),
}
SETTING_BOOLS = ("lock_prov_server", "prov_polling", "clock_24h", "paging_enabled", "intercom_unmute",
                 "rest_api", "web_ui", "softkey_park", "softkey_record")


@router.get("/settings", response_class=HTMLResponse)
def settings_form(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    fw_dir = config.PROV_DIR / config.FIRMWARE_DIR
    firmware = sorted(f.name for f in fw_dir.iterdir() if f.is_file()) if fw_dir.is_dir() else []
    snap = db.snapshot(conn)
    auto_map = plan.build_digitmap(snap["extensions"], snap["ring_groups"], snap["outbound"])
    return render(request, conn, "settings.html", firmware=firmware, auto_digitmap=auto_map,
                  prov_url=f"http://{poly.prov_server_name(snap['settings'])}")


@router.post("/settings")
async def settings_save(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    form = await request.form()
    try:
        updates = {}
        for key, rule in SETTING_RULES.items():
            value = fval(form, key)
            if not rule.match(value):
                raise plan.ValidationError(f"Érvénytelen érték: {key} = {value!r}")
            updates[key] = value
        for key in SETTING_BOOLS:
            updates[key] = str(fbool(form, key))
        updates["site_overrides"] = form.get("site_overrides") or ""
        plan.parse_params(updates["site_overrides"])
        updates["inbound_default"] = valid_dest(conn, fval(form, "inbound_default"))
        if updates["sip_transport"] == "tls" and not Path(config.TLS_CERT).exists():
            raise plan.ValidationError(f"TLS-hez hiányzik a tanúsítvány: {config.TLS_CERT}")
    except plan.ValidationError as exc:
        flash(request, str(exc), "err")
        return redirect("/settings")
    for key, value in updates.items():
        db.set_setting(conn, key, value)
    db.mark_dirty(conn)
    flash(request, "Beállítások mentve. Alkalmazd a változásokat, majd szinkronizáld a telefonokat.")
    return redirect("/settings")


@router.post("/settings/firmware")
async def firmware_upload(request: Request, file: UploadFile, conn=Depends(get_db), _=Depends(require_login)):
    name = Path(file.filename or "").name
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", name) or not name.endswith((".ld", ".zip", ".bin")):
        flash(request, "Csak .ld/.zip/.bin firmware fájl tölthető fel (betű, szám, ._- a névben).", "err")
        return redirect("/settings")
    target_dir = config.PROV_DIR / config.FIRMWARE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp = target_dir / f".{name}.part"
    with open(tmp, "wb") as fh:
        while chunk := await file.read(1024 * 1024):
            fh.write(chunk)
    tmp.replace(target_dir / name)
    flash(request, f"Firmware feltöltve: {name}. Válaszd ki a beállításokban a telepítéshez.")
    return redirect("/settings")


@router.post("/settings/admin-password")
async def admin_password(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    form = await request.form()
    new = fval(form, "new_password")
    if len(new) < 10:
        flash(request, "Az admin jelszó legalább 10 karakter.", "err")
    elif new != fval(form, "new_password2"):
        flash(request, "A két jelszó nem egyezik.", "err")
    else:
        db.set_setting(conn, "admin_password_hash", httpauth.hash_password(new))
        flash(request, "Admin jelszó megváltoztatva.")
    return redirect("/settings")


# ---------------------------------------------------------------- apply / system
@router.post("/apply")
async def apply(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    result = await run_in_threadpool(services.apply_config, conn)
    if result["error"]:
        flash(request, f"Konfiguráció kiírva, de az Asterisk újratöltés nem sikerült: {result['error']}", "err")
    elif not result["changed"]:
        flash(request, "Nem volt változás az Asterisk konfigurációban.")
    else:
        flash(request, f"Alkalmazva: {', '.join(result['changed'])} (újratöltve: {', '.join(result['reloaded'])})")
    if result["restart_required"]:
        flash(request, "A SIP transport megváltozott - az Asterisk újraindítása szükséges.", "warn")
    form = await request.form()
    if fbool(form, "resync"):
        return await resync_all(request, conn)
    return redirect(request.headers.get("referer") or "/")


@router.post("/resync-all")
async def resync_all(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    macs = [r["mac"] for r in conn.execute("SELECT mac FROM phones")]
    errors = []
    for mac in macs:
        err = await run_in_threadpool(services.notify_phone, conn, mac, False)
        if err:
            errors.append(f"{mac}: {err}")
    flash(request, f"Szinkronizálás elküldve {len(macs) - len(errors)}/{len(macs)} telefonnak.")
    for e in errors:
        flash(request, e, "warn")
    return redirect(request.headers.get("referer") or "/phones")


@router.post("/restart-asterisk")
async def restart_asterisk(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    _, err = await run_in_threadpool(ami.safe_call, services.restart_asterisk)
    if err:
        flash(request, err, "err")
    else:
        db.set_setting(conn, "restart_required", "0")
        flash(request, "Az Asterisk újraindul, amint nincs aktív hívás (néhány másodperc). "
                       "Addig az AMI hibaüzenet normális, frissítsd az oldalt.")
    return redirect("/")


@router.get("/asterisk/preview", response_class=HTMLResponse)
def asterisk_preview(request: Request, conn=Depends(get_db), _=Depends(require_login)):
    files = asterisk_gen.generate(db.snapshot(conn))
    text = "\n".join(f"=== {name} ===\n{content}" for name, content in files.items())
    text = re.sub(r"(password|secret)=\S+", r"\1=********", text)
    return render(request, conn, "text_view.html", title="Generált Asterisk konfiguráció", text=text, back="/")


@router.get("/healthz")
def healthz():
    return PlainTextResponse("ok")
