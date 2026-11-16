"""Poly CCX500 (UC Software / PolyOS, base profile "Generic" = OpenSIP) provisioning files.

File layout served under /prov/ :
  000000000000.cfg              master config for unknown phones (site config only, no lines)
  <mac>.cfg                     master config for a known phone
  ccx/site.cfg                  parameters common to all phones
  ccx/<mac>-phone.cfg           per-phone lines, line keys, BLF, speed dials
  000000000000-directory.xml    shared contact directory generated from the extensions
  firmware/<file>               optional firmware (APP_FILE_PATH)
  logs/ overrides/ contacts/ calllists/   uploads from the phones (HTTP PUT)

CONFIG_FILES is evaluated left to right with the leftmost file winning, so the
per-phone file comes first.
"""
import re
from xml.sax.saxutils import escape, quoteattr

from . import config, plan

CODEC_MAP = {"opus": "Opus", "g722": "G722", "alaw": "G711_A", "ulaw": "G711_Mu", "g729": "G729_AB"}
TRANSPORT_MAP = {"udp": "UDPOnly", "tcp": "TCPOnly", "tls": "TLS"}

DST_RULES = {
    # Last Sunday of March 02:00 -> last Sunday of October 03:00
    "eu": {
        "tcpIpApp.sntp.daylightSavings.enable": "1",
        "tcpIpApp.sntp.daylightSavings.fixedDayEnable": "0",
        "tcpIpApp.sntp.daylightSavings.start.month": "3",
        "tcpIpApp.sntp.daylightSavings.start.date": "25",
        "tcpIpApp.sntp.daylightSavings.start.dayOfWeek": "1",
        "tcpIpApp.sntp.daylightSavings.start.dayOfWeek.lastInMonth": "1",
        "tcpIpApp.sntp.daylightSavings.start.time": "2",
        "tcpIpApp.sntp.daylightSavings.stop.month": "10",
        "tcpIpApp.sntp.daylightSavings.stop.date": "25",
        "tcpIpApp.sntp.daylightSavings.stop.dayOfWeek": "1",
        "tcpIpApp.sntp.daylightSavings.stop.dayOfWeek.lastInMonth": "1",
        "tcpIpApp.sntp.daylightSavings.stop.time": "3",
    },
    # Second Sunday of March -> first Sunday of November, 02:00
    "us": {
        "tcpIpApp.sntp.daylightSavings.enable": "1",
        "tcpIpApp.sntp.daylightSavings.fixedDayEnable": "0",
        "tcpIpApp.sntp.daylightSavings.start.month": "3",
        "tcpIpApp.sntp.daylightSavings.start.date": "8",
        "tcpIpApp.sntp.daylightSavings.start.dayOfWeek": "1",
        "tcpIpApp.sntp.daylightSavings.start.dayOfWeek.lastInMonth": "0",
        "tcpIpApp.sntp.daylightSavings.start.time": "2",
        "tcpIpApp.sntp.daylightSavings.stop.month": "11",
        "tcpIpApp.sntp.daylightSavings.stop.date": "1",
        "tcpIpApp.sntp.daylightSavings.stop.dayOfWeek": "1",
        "tcpIpApp.sntp.daylightSavings.stop.dayOfWeek.lastInMonth": "0",
        "tcpIpApp.sntp.daylightSavings.stop.time": "2",
    },
    "none": {"tcpIpApp.sntp.daylightSavings.enable": "0"},
}

_GROUP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


def render_cfg(params: dict, comment: str = "") -> str:
    """Render parameters as a Poly XML config file, grouped by their first segment."""
    groups: dict[str, list] = {}
    for key, value in params.items():
        head = key.split(".", 1)[0]
        groups.setdefault(head if _GROUP_RE.match(head) else "misc", []).append((key, value))
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
    if comment:
        out.append(f"<!-- {comment.replace('--', '-')} -->")
    out.append("<polycomConfig>")
    for group, items in groups.items():
        out.append(f"  <{group}")
        out.extend(f"    {key}={quoteattr(str(value))}" for key, value in items)
        out.append("  />")
    out.append("</polycomConfig>")
    return "\n".join(out) + "\n"


def render_master(settings: dict, mac: str | None) -> str:
    files = ([f"ccx/{mac}-phone.cfg"] if mac else []) + ["ccx/site.cfg"]
    fw = settings.get("firmware_file", "")
    attrs = {
        "APP_FILE_PATH": f"{config.FIRMWARE_DIR}/{fw}" if fw else "",
        "CONFIG_FILES": ", ".join(files),
        "MISC_FILES": "",
        "LOG_FILE_DIRECTORY": "logs",
        "OVERRIDES_DIRECTORY": "overrides",
        "CONTACTS_DIRECTORY": "contacts",
        "LICENSE_DIRECTORY": "",
        "USER_PROFILES_DIRECTORY": "",
        "CALL_LISTS_DIRECTORY": "calllists",
        "COREFILE_DIRECTORY": "logs",
    }
    body = " ".join(f"{k}={quoteattr(v)}" for k, v in attrs.items())
    return (
        '<?xml version="1.0" standalone="yes"?>\n'
        f"<!-- ccxpbx master config for {mac or 'unknown phones'} -->\n"
        f"<APPLICATION {body}/>\n"
    )


def _server_params(settings: dict) -> tuple[str, str, str]:
    transport = settings.get("sip_transport", "udp")
    port = settings["tls_port"] if transport == "tls" else settings["sip_port"]
    return settings["server_host"], port, TRANSPORT_MAP.get(transport, "UDPOnly")


def prov_server_name(settings: dict) -> str:
    return f"{_host_port(settings)}/prov"


def _host_port(settings: dict) -> str:
    port = settings.get("http_port", "80")
    return f"{settings['server_host']}{'' if port == '80' else ':' + port}"


def public_url(settings: dict, path: str) -> str:
    """URL the phone uses for non-provisioning resources (wallpapers, phone portal)."""
    return f"http://{_host_port(settings)}{path}"


# CCXPBX brand colours for the phone's own UI (ui.* parameters, the phone restarts to apply)
PHONE_UI_BRAND = {
    "ui.statusBar.background": "#0E1116",
    "ui.statusBar.text.color": "#F6F7F9",
    "ui.softkey.background": "#1B2129",
    "ui.softkey.text.color": "#F6F7F9",
    "ui.menu.title.background": "#0E1116",
    "ui.menu.background": "#0E1116",
    "ui.menu.item.background": "#1B2129",
    "ui.menu.item.text.color": "#F6F7F9",
    "ui.home.background": "#0E1116",
}


def _wallpaper_params(settings: dict, choice: str) -> dict:
    if choice == "none" or not choice:
        return {"bg.color.bm.1.name": ""}
    return {
        "bg.color.bm.1.name": public_url(settings, f"/wallpapers/{choice}"),
        # older UC Software selects the background with this; ignored where unknown
        "bg.color.selection": "2,1",
    }


def site_params(snapshot: dict) -> dict:
    s = snapshot["settings"]
    host, port, transport = _server_params(s)
    p: dict[str, str] = {}

    # --- device.* (only applied when device.set=1 and <param>.set=1) ---
    p["device.set"] = "1"
    p["device.baseProfile.set"] = "1"
    p["device.baseProfile"] = s.get("base_profile") or "Generic"
    if s.get("phone_admin_password"):
        p["device.auth.localAdminPassword.set"] = "1"
        p["device.auth.localAdminPassword"] = s["phone_admin_password"]
    if s.get("phone_user_password"):
        p["device.auth.localUserPassword.set"] = "1"
        p["device.auth.localUserPassword"] = s["phone_user_password"]
    if s.get("lock_prov_server") == "1" and host:
        use_auth = s.get("prov_auth") != "none"
        p.update({
            "device.prov.serverType.set": "1",
            "device.prov.serverType": "HTTP",
            "device.prov.serverName.set": "1",
            "device.prov.serverName": prov_server_name(s),
            "device.prov.user.set": "1",
            "device.prov.user": s["prov_user"] if use_auth else "",
            "device.prov.password.set": "1",
            "device.prov.password": s["prov_password"] if use_auth else "",
        })

    # --- SIP server ---
    p.update({
        "voIpProt.server.1.address": host,
        "voIpProt.server.1.port": port,
        "voIpProt.server.1.transport": transport,
        "voIpProt.server.1.expires": s.get("reg_expires", "600"),
        "voIpProt.SIP.specialEvent.checkSync.alwaysReboot": "0",
        # Intercom / paging: Asterisk adds "Alert-Info: Ring Answer" -> auto answer
        "voIpProt.SIP.alertInfo.1.value": plan.INTERCOM_ALERT,
        "voIpProt.SIP.alertInfo.1.class": "autoAnswer",
        "call.autoAnswer.micMute": "0" if s.get("intercom_unmute") == "1" else "1",
    })
    if s.get("sip_transport") == "tls":
        p.update({"sec.srtp.enable": "1", "sec.srtp.offer": "1", "sec.srtp.require": "0"})
        ca = _read_ca()
        if ca:
            p["device.sec.TLS.customCaCert1.set"] = "1"
            p["device.sec.TLS.customCaCert1"] = ca

    # --- time / locale ---
    p["tcpIpApp.sntp.address"] = s.get("ntp_server") or "pool.ntp.org"
    p["tcpIpApp.sntp.gmtOffset"] = s.get("gmt_offset", "0")
    p.update(DST_RULES.get(s.get("dst_rule", "eu"), DST_RULES["none"]))
    p["lcl.datetime.time.24HourClock"] = "1" if s.get("clock_24h") == "1" else "0"
    if s.get("language"):
        p["lcl.ml.lang"] = s["language"]

    # --- codecs (order = priority, 0 = disabled) ---
    order = [c.strip() for c in s.get("codecs", "").split(",") if c.strip() in CODEC_MAP]
    for codec, poly_name in CODEC_MAP.items():
        p[f"voice.codecPref.{poly_name}"] = str(order.index(codec) + 1) if codec in order else "0"

    # --- dialling ---
    digitmap = s.get("digitmap") or plan.build_digitmap(
        snapshot["extensions"], snapshot["ring_groups"], snapshot["outbound"]
    )
    p["dialplan.digitmap"] = digitmap
    p["dialplan.digitmap.timeOut"] = "|".join("3" for _ in digitmap.split("|"))

    # --- voicemail / pickup / BLF / presence ---
    p.update({
        "up.oneTouchVoiceMail": "1",
        "feature.directedCallPickup.enabled": "1",
        "call.directedCallPickupMethod": "legacy",
        "call.directedCallPickupString": plan.FC_DIRECTED_PICKUP,
        "attendant.reg": "1",
        "attendant.uri": "",
        "attendant.behaviors.display.remoteCallerID.normal": "1",
        "attendant.behaviors.display.spontaneousCallAppearances.normal": "1",
        "attendant.behaviors.display.remoteCallerID.automata": "1",
        "feature.presence.enabled": "1",
        "voice.volume.persist.handset": "1",
        "voice.volume.persist.headset": "1",
        "voice.volume.persist.handsfree": "1",
    })

    # --- look: wallpaper, phone portal in the Applications menu, optional brand colours ---
    p.update(_wallpaper_params(s, s.get("wallpaper", "")))   # '' clears a previous background
    if s.get("microbrowser", "1") == "1" and host:
        p["homeScreen.application.enable"] = "1"
        p["mb.main.home"] = public_url(s, "/phone/")
        p["mb.main.reloadPage"] = "1"
    if s.get("phone_ui_brand") == "1":
        p.update(PHONE_UI_BRAND)

    # --- power saving: outside office hours the screen dims and shows "Off Hours"
    p["powerSaving.enable"] = "1" if s.get("power_saving", "1") == "1" else "0"
    try:
        hours = plan.parse_office_hours(s.get("office_hours", plan.DEFAULT_OFFICE_HOURS))
    except plan.ValidationError:
        hours = plan.parse_office_hours(plan.DEFAULT_OFFICE_HOURS)
    for day in plan.DAY_KEYS:
        start, end = hours.get(day, (0, 0))
        p[f"powerSaving.officeHours.startHour.{day}"] = str(start)
        p[f"powerSaving.officeHours.duration.{day}"] = str(end - start)
    p["powerSaving.idleTimeout.officeHours"] = s.get("idle_office", "40")
    p["powerSaving.idleTimeout.offHours"] = s.get("idle_off", "1")
    p["powerSaving.idleTimeout.userInputExtension"] = s.get("idle_user_ext", "10")

    # --- status LED (top right). Verified on CCX500 / PolyOS 9.5.1: incoming call flashes red.
    # The ind.pattern.* LED patterns only drive line key LEDs, which the CCX500 does not have.
    p["call.offering.led"] = "1" if s.get("led_incoming", "1") == "1" else "0"

    # --- in-call soft keys (send DTMF to Asterisk features) ---
    softkeys = []
    if s.get("softkey_park") == "1":
        softkeys.append(("Park", plan.DTMF_PARK))
    if s.get("softkey_record") == "1":
        softkeys.append(("Felvétel", plan.DTMF_RECORD))
    p["feature.enhancedFeatureKeys.enabled"] = "1"
    for i, (label, digits) in enumerate(softkeys, 1):
        p.update({
            f"softkey.{i}.label": label,
            f"softkey.{i}.action": f"{digits}$Tdtmf$",
            f"softkey.{i}.enable": "1",
            f"softkey.{i}.use.active": "1",
            f"softkey.{i}.use.idle": "0",
            f"softkey.{i}.use.alerting": "0",
            f"softkey.{i}.use.dialtone": "0",
            f"softkey.{i}.use.proceeding": "0",
            f"softkey.{i}.use.setup": "0",
            f"softkey.{i}.use.hold": "0",
        })

    # --- multicast paging (Poly group paging, no server involvement) ---
    if s.get("paging_enabled") == "1":
        p.update({
            "ptt.pageMode.enable": "1",
            "ptt.address": s.get("paging_address", "224.0.1.116"),
            "ptt.port": s.get("paging_port", "5001"),
            "ptt.pageMode.defaultGroup": "1",
            "ptt.pageMode.group.1.label": "Mindenki",
            "ptt.pageMode.group.1.available": "1",
            "ptt.pageMode.group.1.allowTransmit": "1",
        })
    else:
        p["ptt.pageMode.enable"] = "0"

    # --- management ---
    p["apps.restapi.enabled"] = "1" if s.get("rest_api") == "1" else "0"
    p["httpd.enabled"] = "1"
    p["httpd.cfg.enabled"] = "1" if s.get("web_ui") == "1" else "0"
    if s.get("prov_polling") == "1":
        p.update({
            "prov.polling.enabled": "1",
            "prov.polling.mode": "abs",
            "prov.polling.time": s.get("prov_polling_time", "03:00"),
        })

    p.update(plan.parse_params(s.get("site_overrides", "")))
    return p


def phone_params(snapshot: dict, phone: dict) -> dict:
    s = snapshot["settings"]
    host, port, transport = _server_params(s)
    p: dict[str, str] = {}

    for line in phone["lines"]:
        i = line["idx"]
        p.update({
            f"reg.{i}.address": line["ext"],
            f"reg.{i}.auth.userId": line["ext"],
            f"reg.{i}.auth.password": line["secret"],
            f"reg.{i}.displayName": line["name"],
            f"reg.{i}.label": f"{line['ext']} {line['name']}".strip()[:32],
            f"reg.{i}.type": "private",
            f"reg.{i}.lineKeys": str(line.get("line_keys") or 1),
            f"reg.{i}.server.1.address": host,
            f"reg.{i}.server.1.port": port,
            f"reg.{i}.server.1.transport": transport,
            f"reg.{i}.server.1.expires": s.get("reg_expires", "600"),
            f"msg.mwi.{i}.callBackMode": "contact",
            f"msg.mwi.{i}.callBack": plan.FC_VM_OWN,
            f"msg.mwi.{i}.led": "1" if s.get("led_voicemail", "1") == "1" else "0",
        })
        if s.get("sip_transport") == "tls":
            p[f"reg.{i}.srtp.enable"] = "1"

    if phone["keys"]:
        p["lineKey.reassignment.enabled"] = "1"
        blf = efk = 0
        for key in phone["keys"]:
            pos, ktype, value, label = key["pos"], key["type"], key["value"], key["label"]
            if ktype == "line":
                p[f"lineKey.{pos}.category"] = "Line"
                p[f"lineKey.{pos}.index"] = value or "1"
            elif ktype in ("blf", "park"):
                blf += 1
                target = plan.PARK_EXT if ktype == "park" else value
                p[f"attendant.resourceList.{blf}.address"] = target
                p[f"attendant.resourceList.{blf}.label"] = label or ("Park" if ktype == "park" else value)
                # "automata": pressing the key during a call blind-transfers (parks) it
                p[f"attendant.resourceList.{blf}.type"] = "automata" if ktype == "park" else "normal"
                p[f"lineKey.{pos}.category"] = "BLF"
                p[f"lineKey.{pos}.index"] = str(blf)
            elif ktype == "speeddial":
                efk += 1
                p.update({
                    f"efk.efklist.{efk}.mname": f"speeddial{efk}",
                    f"efk.efklist.{efk}.status": "1",
                    f"efk.efklist.{efk}.label": label or value,
                    f"efk.efklist.{efk}.action.string": f"{value}$Tinvite$",
                    f"lineKey.{pos}.category": "EFK",
                    f"lineKey.{pos}.index": str(efk),
                })
            else:
                p[f"lineKey.{pos}.category"] = "Unassigned"
                p[f"lineKey.{pos}.index"] = "0"
    else:
        p["lineKey.reassignment.enabled"] = "0"

    # Hidden home screen icons; icons not listed keep the site / factory default
    hidden = {k for k in (phone.get("home_hidden") or "").split(",") if k in plan.HOME_ICON_KEYS}
    for key in hidden:
        p[f"homeScreen.{key}.enable"] = "0"

    if phone.get("wallpaper"):   # per-phone choice beats the site default
        p.update(_wallpaper_params(s, phone["wallpaper"]))

    p.update(plan.parse_params(phone.get("overrides", "")))
    return p


def _dir_item(fn: str, ln: str, ct: str, sd: int | None = None) -> str:
    sd_tag = f"<sd>{sd}</sd>" if sd else ""
    return f"    <item><fn>{escape(fn)}</fn><ln>{escape(ln)}</ln><ct>{escape(ct)}</ct>{sd_tag}<bw>0</bw><bb>0</bb></item>"


def _split_name(name: str) -> tuple[str, str]:
    parts = name.rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (name, "")


_ITEM_RE = re.compile(r"<item>.*?</item>", re.S)
_CT_RE = re.compile(r"<ct>\s*([^<]*?)\s*</ct>")
_SD_RE = re.compile(r"<sd>\s*(\d+)\s*</sd>")


def render_directory(snapshot: dict, phone: dict | None = None, uploaded: str = "") -> str:
    """The contact directory a phone downloads.

    PolyOS on the CCX500 shows contacts with a speed dial index (<sd>) as favourites next to the line keys
    (verified on 9.5.1; EFK speed dial line keys are not shown at all). So:
      * extensions are listed without <sd>, they must not turn into keys by themselves;
      * with a phone, its "speed dial" keys become favourites, numbered in key order;
      * contacts the user added on the phone (its uploaded copy) are kept, their favourites after ours;
      * the phone's own extensions are left out of its directory.
    """
    exts = {e["ext"]: e for e in snapshot["extensions"]}
    own = {line["ext"] for line in (phone or {}).get("lines", [])}
    favourites = []   # (number, label) in key order
    if phone:
        for key in phone.get("keys", []):
            if key["type"] == "speeddial" and key["value"]:
                favourites.append((key["value"], key.get("label") or ""))
    fav_sd = {}
    items = []
    for n, (number, label) in enumerate(favourites, 1):
        ext = exts.get(number)
        name = label or (ext["name"] if ext else number)
        fav_sd.setdefault(number, (n, name))
    for ext in snapshot["extensions"]:
        if ext["ext"] in own or (not ext["in_directory"] and ext["ext"] not in fav_sd):
            continue
        sd, name = fav_sd.pop(ext["ext"], (None, ext["name"]))
        items.append(_dir_item(*_split_name(name), ext["ext"], sd))
    for number, (sd, name) in fav_sd.items():   # favourites that are not extensions (external numbers)
        items.append(_dir_item(*_split_name(name), number, sd))

    # contacts added on the phone: keep them, minus extensions and our favourites, renumbering their <sd>
    next_sd = len(favourites) + 1
    taken = set(exts) | {n for n, _ in favourites}
    for raw in _ITEM_RE.findall(uploaded or ""):
        ct = _CT_RE.search(raw)
        if not ct or ct.group(1) in taken:
            continue
        taken.add(ct.group(1))
        if _SD_RE.search(raw):
            raw = _SD_RE.sub(f"<sd>{next_sd}</sd>", raw, count=1)
            next_sd += 1
        items.append("    " + raw.strip())

    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<directory>", "  <item_list>", *items,
           "  </item_list>", "</directory>"]
    return "\n".join(out) + "\n"


def _read_ca() -> str:
    try:
        return config.TLS_CA_CERT.read_text().strip()
    except OSError:
        return ""
