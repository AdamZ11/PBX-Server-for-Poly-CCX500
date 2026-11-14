"""CCXPBX page for the phone's Applications menu (Poly microbrowser, mb.main.home = /phone/).

Plain HTML + CSS, no JavaScript, large touch rows, auto refresh - so it works in the
phone's built-in browser. The phone is recognised by its IP address (SIP contact or
last provisioning request); other clients get 403, except a logged-in admin, who can
preview any phone with ?mac=<mac>.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse

from . import ami, db, plan, services
from .services import get_db
from .web import STATE_LABELS, templates

router = APIRouter()

CODES = [
    (plan.FC_VM_OWN, "Saját hangposta"),
    (plan.FC_VM_ANY, "Bármely hangposta"),
    (f"{plan.FC_INTERCOM} + mellék", "Intercom (a hívott kihangosítva felveszi)"),
    (plan.FC_PAGE_ALL, "Hangosbemondás mindenkinek"),
    (plan.FC_GROUP_PICKUP, "Csoportos hívásfelvétel"),
    (f"{plan.FC_DIRECTED_PICKUP} + mellék", "Célzott hívásfelvétel"),
    (plan.PARK_EXT, "Hívás parkolása (átkapcsolás ide)"),
    (f"{plan.PARK_SLOTS[0]}–{plan.PARK_SLOTS[-1]}", "Parkolt hívás visszavétele"),
    (f"{plan.CONF_ROOMS[0]}–{plan.CONF_ROOMS[-1]}", "Konferenciaszobák"),
    (plan.FC_ECHO, "Visszhangteszt"),
    (plan.FC_TIME, "Pontos idő"),
    (f"hívás közben {plan.DTMF_PARK}", "Parkolás"),
    (f"hívás közben {plan.DTMF_RECORD}", "Felvétel indítása / leállítása"),
]


def identify(conn, request: Request, contacts: list[dict]) -> str | None:
    """MAC of the phone asking, by client IP; admins may preview with ?mac=."""
    mac = request.query_params.get("mac", "")
    if mac and request.session.get("user"):
        return mac if conn.execute("SELECT 1 FROM phones WHERE mac=?", (mac,)).fetchone() else None
    ip = request.client.host if request.client else ""
    if not ip:
        return None
    for row in conn.execute("SELECT mac FROM phones"):
        if services.phone_ip(conn, row["mac"], contacts) == ip:
            return row["mac"]
    return None


def collect(conn, request: Request, need_parked: bool) -> dict:
    def query(a):
        return {"contacts": a.contacts(), "states": a.extension_states(),
                "parked": a.parked_calls() if need_parked else []}

    live, err = ami.safe_call(query, {"contacts": [], "states": {}, "parked": []})
    mac = identify(conn, request, live["contacts"])
    data = {"mac": mac, "ami_error": err, "live": live}
    if not mac:
        return data
    phone = db.load_phone(conn, mac)
    own = phone["lines"][0]["ext"] if phone["lines"] else None
    vm_new = vm_old = 0
    if own:
        counts, _ = ami.safe_call(lambda a: a.mailbox_count(f"{own}@default"), (0, 0))
        vm_new, vm_old = counts
    registered = {c.get("Endpoint") for c in live["contacts"]}
    extensions = []
    for r in conn.execute("SELECT ext, name FROM extensions WHERE in_directory=1 ORDER BY ext"):
        state = live["states"].get(r["ext"]) or ("free" if r["ext"] in registered else "off")
        if r["ext"] not in registered:
            state = "off"
        extensions.append({"num": r["ext"], "name": r["name"], "state": state, "label": STATE_LABELS[state],
                           "own": r["ext"] == own})
    seen = conn.execute("SELECT * FROM seen_devices WHERE mac=?", (mac,)).fetchone()
    settings = db.get_settings(conn)
    data.update(phone=phone, own=own, vm_new=vm_new, vm_old=vm_old, extensions=extensions,
                seen=dict(seen) if seen else {}, settings=settings,
                server=services.server_status(asterisk_ok=err is None),
                parked=[{"slot": p.get("ParkingSpace", ""),
                         "who": p.get("ParkeeConnectedLineName") or p.get("ParkeeCallerIDName", ""),
                         "num": p.get("ParkeeCallerIDNum", ""),
                         "secs": p.get("ParkingDuration", "")} for p in live["parked"]])
    return data


async def _page(request: Request, conn, view: str):
    data = await run_in_threadpool(collect, conn, request, view in ("home", "parked"))
    if not data["mac"]:
        return templates.TemplateResponse(request, "phone_portal.html",
                                          {"view": "denied", "title": "CCXPBX"}, status_code=403)
    titles = {"home": "CCXPBX", "directory": "Telefonkönyv", "parked": "Parkolt hívások",
              "codes": "Hasznos kódok", "system": "Rendszer"}
    preview = f"?mac={data['mac']}" if request.query_params.get("mac") else ""
    return templates.TemplateResponse(request, "phone_portal.html",
                                      {**data, "view": view, "title": titles[view], "q": preview,
                                       "codes": CODES, "refresh": view in ("home", "directory", "parked")})


@router.get("/phone", include_in_schema=False)
def phone_root():
    return RedirectResponse("/phone/", status_code=307)


@router.get("/phone/", response_class=HTMLResponse)
async def phone_home(request: Request, conn=Depends(get_db)):
    return await _page(request, conn, "home")


@router.get("/phone/{view}", response_class=HTMLResponse)
async def phone_view(view: str, request: Request, conn=Depends(get_db)):
    if view not in ("directory", "parked", "codes", "system"):
        return RedirectResponse("/phone/", status_code=303)
    return await _page(request, conn, view)
