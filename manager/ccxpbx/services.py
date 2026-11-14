"""Operations shared by the web UI and the CLI."""
import os
import re
import socket

from . import ami, asterisk_gen, config, db

# UC Software:  "FileTransport PolycomCCX-CCX_500-UA/8.1.3.1301"
# PolyOS 9.x and upload names: "...-9.5.1.0067-CCX500-core..." - so match loosely.
MODEL_RE = re.compile(r"(?<![A-Za-z])(CCX|VVX|Trio|Edge)[ _-]?([0-9]{2,4}[A-Za-z]?)", re.I)
VERSION_RE = re.compile(r"(?<![0-9.])([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{3,5})(?![0-9])")


def get_db():
    """FastAPI dependency: one connection per request."""
    conn = db.connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def parse_user_agent(ua: str) -> tuple[str, str]:
    """(model, firmware) such as ("CCX500", "9.5.1.0130"); empty strings when unknown."""
    m = MODEL_RE.search(ua or "")
    v = VERSION_RE.search(ua or "")
    model = f"{m.group(1).upper() if m.group(1).lower() != 'trio' else 'Trio'}{m.group(2).upper()}" if m else ""
    return model, (v.group(1) if v else "")


def record_seen(conn, mac: str, ip: str, ua: str, filename: str) -> None:
    model, fw = parse_user_agent(ua)
    if not model or not fw:
        f_model, f_fw = parse_user_agent(filename)
        model, fw = model or f_model, fw or f_fw
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
    # Transports are only read at startup. If Asterisk is not running (e.g. during
    # installation) it will pick them up when it starts, so no restart is needed.
    if asterisk_gen.TRANSPORT_FILE in changed and not result["error"]:
        result["restart_required"] = True
        db.set_setting(conn, "restart_required", "1")
    if not result["error"]:
        db.set_setting(conn, "dirty", "0")
    return result


def server_status(asterisk_ok: bool | None = None) -> dict:
    """Sidebar card: host name, uptime and load (Linux /proc; best effort elsewhere)."""
    name = socket.gethostname().split(".")[0] or "ccxpbx"
    parts = []
    try:
        seconds = float(open("/proc/uptime").read().split()[0])
        days, rest = divmod(int(seconds), 86400)
        parts.append(f"uptime {days}n {rest // 3600:02d}ó" if days else f"uptime {rest // 3600}ó {rest % 3600 // 60:02d}p")
    except (OSError, ValueError, IndexError):
        pass
    try:
        load = os.getloadavg()[0]
        parts.append(f"terhelés {load:.2f}")
    except (OSError, AttributeError):
        pass
    if asterisk_ok is None:
        asterisk_ok = _asterisk_reachable()
    parts.append("Asterisk fut" if asterisk_ok else "Asterisk nem elérhető")
    return {"name": name, "meta": " · ".join(parts), "asterisk": asterisk_ok}


def _asterisk_reachable() -> bool:
    try:
        with socket.create_connection((config.AMI_HOST, config.AMI_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def local_ips() -> set[str]:
    """IPv4 addresses of this host (best effort, no external traffic is sent)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # UDP connect only picks the outgoing interface
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    ips.discard("127.0.0.1")
    ips.discard("127.0.1.1")
    return ips


def server_host_mismatch(server_host: str) -> list[str] | None:
    """If server_host is an IPv4 address that this host does not have, return the real IPs."""
    if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", server_host or ""):
        return None
    ips = local_ips()
    if not ips or server_host in ips:
        return None
    return sorted(ips)


def restart_asterisk(a) -> None:
    """Asterisk drops the AMI connection when it restarts - that means success."""
    try:
        a.command("core restart gracefully")
    except ami.AMIError as exc:
        if "lezárult" not in str(exc) and "olvasási hiba" not in str(exc):
            raise


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
        for f in sorted(d.glob(f"*{mac}*")):
            if f.name.startswith("."):
                continue
            st = f.stat()
            files.append({"dir": sub, "name": f.name, "size": st.st_size, "mtime": st.st_mtime})
    return files
