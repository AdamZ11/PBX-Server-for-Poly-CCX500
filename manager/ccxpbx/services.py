"""Operations shared by the web UI and the CLI."""
import re

from . import ami, asterisk_gen, config, db

UA_RE = re.compile(r"Polycom[A-Za-z]*-([A-Za-z0-9_]+)-UA/([0-9][0-9.]*)")


def get_db():
    """FastAPI dependency: one connection per request."""
    conn = db.connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def parse_user_agent(ua: str) -> tuple[str, str]:
    m = UA_RE.search(ua or "")
    return (m.group(1), m.group(2)) if m else ("", "")


def record_seen(conn, mac: str, ip: str, ua: str, filename: str) -> None:
    model, fw = parse_user_agent(ua)
    conn.execute(
        "INSERT INTO seen_devices(mac, ip, user_agent, model, firmware, last_file) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(mac) DO UPDATE SET ip=excluded.ip, user_agent=excluded.user_agent, "
        "model=CASE WHEN excluded.model!='' THEN excluded.model ELSE model END, "
        "firmware=CASE WHEN excluded.firmware!='' THEN excluded.firmware ELSE firmware END, "
        "last_file=excluded.last_file, last_seen=datetime('now')",
        (mac, ip, ua[:255], model, fw, filename[:128]),
    )


def apply_config(conn) -> dict:
    """Write the Asterisk include files and reload the affected modules."""
    snap = db.snapshot(conn)
    files = asterisk_gen.generate(snap)
    changed = asterisk_gen.write_files(files)
    result = {"changed": changed, "reloaded": [], "error": None, "restart_required": False}
    if asterisk_gen.TRANSPORT_FILE in changed:
        result["restart_required"] = True
        db.set_setting(conn, "restart_required", "1")

    def reload(a):
        done = []
        if any(f.startswith("pjsip") for f in changed):
            a.command("module reload res_pjsip.so")
            done.append("pjsip")
        if any(f in changed for f in ("extensions_generated.conf", "globals.conf")):
            a.command("dialplan reload")
            done.append("dialplan")
        if "voicemail_boxes.conf" in changed:
            a.command("module reload app_voicemail.so")
            done.append("voicemail")
        return done

    if changed:
        result["reloaded"], result["error"] = ami.safe_call(reload, [])
    if not result["error"]:
        db.set_setting(conn, "dirty", "0")
    return result


def primary_endpoint(conn, mac: str) -> str | None:
    row = conn.execute("SELECT ext FROM phone_lines WHERE mac=? ORDER BY idx LIMIT 1", (mac,)).fetchone()
    return row["ext"] if row else None


def phone_ip(conn, mac: str, contacts: list[dict] | None = None) -> str:
    """Best known IP of a phone: live SIP contact first, last provisioning request second."""
    ext = primary_endpoint(conn, mac)
    if ext:
        if contacts is None:
            contacts, _ = ami.safe_call(lambda a: a.contacts(), [])
        for c in contacts or []:
            if c.get("Endpoint") == ext:
                m = re.search(r"@\[?([0-9a-fA-F.:]+?)\]?(?::\d+)?(?:;|$)", c.get("Uri", ""))
                if m:
                    return m.group(1)
    row = conn.execute("SELECT ip FROM seen_devices WHERE mac=?", (mac,)).fetchone()
    return row["ip"] if row else ""


def notify_phone(conn, mac: str, reboot: bool = False) -> str | None:
    """Send check-sync to the phone. Returns an error message or None."""
    ext = primary_endpoint(conn, mac)
    if not ext:
        return "A telefonhoz nincs vonal rendelve, nem regisztrál - használd a REST újraindítást."
    event = "check-sync;reboot=true" if reboot else "check-sync"
    resp, err = ami.safe_call(lambda a: a.notify(ext, event))
    if err:
        return err
    if resp.get("Response") != "Success":
        return resp.get("Message", "NOTIFY sikertelen (a telefon nincs regisztrálva?)")
    return None


def uploaded_files(mac: str) -> list[dict]:
    files = []
    for sub in config.UPLOAD_DIRS:
        d = config.PROV_DIR / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob(f"{mac}*")):
            st = f.stat()
            files.append({"dir": sub, "name": f.name, "size": st.st_size, "mtime": st.st_mtime})
    return files
