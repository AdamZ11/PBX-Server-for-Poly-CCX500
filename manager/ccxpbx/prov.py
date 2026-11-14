"""Provisioning server for the Poly CCX500 (HTTP GET for config, HTTP PUT for uploads)."""
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response

from . import config, db, httpauth, poly, wallpapers
from .services import get_db, record_seen

router = APIRouter()

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAC_IN_NAME = re.compile(r"^([0-9a-fA-F]{12})")
# Core dumps are named e.g. "encl.<mac>-9.5.1.0067-CCX500-core....tar.gz"
_MAC_ANYWHERE = re.compile(r"(?<![0-9a-fA-F])((?!000000000000)[0-9a-fA-F]{12})(?![0-9a-fA-F])")
_auth: httpauth.Authenticator | None = None


def authenticator() -> httpauth.Authenticator:
    global _auth
    if _auth is None:
        _auth = httpauth.Authenticator(config.SECRET_KEY or db.gen_secret(32))
    return _auth


def _split(path: str) -> tuple[str, str] | None:
    """('', name) or (subdir, name); None if the path is not acceptable."""
    parts = [p for p in path.split("/") if p]
    if len(parts) == 1 and _SAFE_NAME.match(parts[0]):
        return "", parts[0]
    if len(parts) == 2 and _SAFE_NAME.match(parts[0]) and _SAFE_NAME.match(parts[1]):
        return parts[0], parts[1]
    return None


def _check_auth(request: Request, settings: dict) -> Response | None:
    mode = settings.get("prov_auth", "digest")
    state = authenticator().check(mode, request.headers.get("authorization"), request.method,
                                  request.url.path, settings["prov_user"], settings["prov_password"])
    if state == "ok":
        return None
    return PlainTextResponse("Unauthorized", status_code=401,
                             headers={"WWW-Authenticate": authenticator().challenge(mode, stale=state == "stale")})


def _xml(content: str) -> Response:
    return Response(content, media_type="application/xml", headers={"Cache-Control": "no-store"})


def _seen(conn, request: Request, name: str) -> str | None:
    m = _MAC_IN_NAME.match(name)
    if not m or m.group(1) == "000000000000":
        return None
    mac = m.group(1).lower()
    ip = request.client.host if request.client else ""
    record_seen(conn, mac, ip, request.headers.get("user-agent", ""), name)
    return mac


_ITEM_RE = re.compile(r"<item>.*?</item>", re.S)
_CT_RE = re.compile(r"<ct>\s*([^<]*?)\s*</ct>")
_SD_RE = re.compile(r"\s*<sd>[^<]*</sd>")


def strip_extension_speed_dials(xml: str, exts: set[str]) -> str:
    """Drop <sd> from contacts that are PBX extensions. Older versions numbered every extension, and PolyOS
    shows speed dial contacts as favourites next to the line keys. Other contacts keep their speed dial."""
    def fix(m):
        item = m.group(0)
        ct = _CT_RE.search(item)
        return _SD_RE.sub("", item) if ct and ct.group(1) in exts else item
    return _ITEM_RE.sub(fix, xml)


@router.api_route("/prov/{path:path}", methods=["GET", "HEAD"])
def prov_get(path: str, request: Request, conn=Depends(get_db)):
    settings = db.get_settings(conn)
    denied = _check_auth(request, settings)
    if denied:
        return denied
    split = _split(path)
    if not split:
        return PlainTextResponse("Not found", status_code=404)
    sub, name = split
    lname = name.lower()
    mac = _seen(conn, request, lname)

    if not sub and lname == "000000000000.cfg":
        return _xml(poly.render_master(settings, None))
    if not sub and mac and lname == f"{mac}.cfg":
        known = conn.execute("SELECT 1 FROM phones WHERE mac=?", (mac,)).fetchone()
        return _xml(poly.render_master(settings, mac if known else None))
    if lname == "000000000000-directory.xml" and sub in ("", "contacts"):
        return _xml(poly.render_directory(db.snapshot(conn)))
    if sub == "ccx":
        if lname == "site.cfg":
            return _xml(poly.render_cfg(poly.site_params(db.snapshot(conn)), "ccxpbx site config"))
        if mac and lname == f"{mac}-phone.cfg":
            phone = db.load_phone(conn, mac)
            if phone:
                return _xml(poly.render_cfg(poly.phone_params(db.snapshot(conn), phone),
                                            f"ccxpbx phone config {mac}"))
        return PlainTextResponse("Not found", status_code=404)
    if sub in (config.FIRMWARE_DIR, *config.UPLOAD_DIRS):
        f = config.PROV_DIR / sub / name
        if f.is_file():
            if sub == "contacts" and lname.endswith("-directory.xml"):
                exts = {r["ext"] for r in conn.execute("SELECT ext FROM extensions")}
                return _xml(strip_extension_speed_dials(f.read_text(encoding="utf-8", errors="replace"), exts))
            return FileResponse(f)
    return PlainTextResponse("Not found", status_code=404)


@router.get("/wallpapers/{name}")
def wallpaper(name: str):
    """Public on purpose: phones fetch bg.color.bm.1.name without provisioning credentials."""
    f = wallpapers.path(name)
    if not f:
        return PlainTextResponse("Not found", status_code=404)
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@router.put("/prov/{path:path}")
async def prov_put(path: str, request: Request, conn=Depends(get_db)):
    settings = db.get_settings(conn)
    denied = _check_auth(request, settings)
    if denied:
        return denied
    split = _split(path)
    if not split or split[0] not in config.UPLOAD_DIRS:
        return PlainTextResponse("Forbidden", status_code=403)
    sub, name = split
    mac_match = _MAC_ANYWHERE.search(name)
    if not mac_match:
        return PlainTextResponse("Forbidden", status_code=403)
    _seen(conn, request, mac_match.group(1).lower() + "-" + name.lower())

    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > config.MAX_UPLOAD:
            return PlainTextResponse("Too large", status_code=413)

    target_dir = config.PROV_DIR / sub
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name
    if sub == "logs" and name.endswith(".log"):
        # Poly uploads new log chunks; append and rotate at MAX_LOG_SIZE
        if target.exists() and target.stat().st_size > config.MAX_LOG_SIZE:
            target.replace(target.with_suffix(".log.1"))
        with open(target, "ab") as fh:
            fh.write(body)
    else:
        tmp = target.with_name(f".{name}.tmp")
        tmp.write_bytes(body)
        tmp.replace(target)
    return Response(status_code=201)
