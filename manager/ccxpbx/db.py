"""SQLite storage. One small file, no ORM, so it runs fine on a Raspberry Pi."""
import secrets
import sqlite3
import string
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extensions (
    ext          TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    secret       TEXT NOT NULL,
    vm_enabled   INTEGER NOT NULL DEFAULT 1,
    vm_pin       TEXT NOT NULL DEFAULT '',
    email        TEXT NOT NULL DEFAULT '',
    ring_time    INTEGER NOT NULL DEFAULT 25,
    record       INTEGER NOT NULL DEFAULT 0,
    pickup_group TEXT NOT NULL DEFAULT '1',
    max_contacts INTEGER NOT NULL DEFAULT 1,
    in_directory INTEGER NOT NULL DEFAULT 1,
    page_member  INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS phones (
    mac       TEXT PRIMARY KEY,
    label     TEXT NOT NULL DEFAULT '',
    model     TEXT NOT NULL DEFAULT 'CCX500',
    overrides TEXT NOT NULL DEFAULT '',
    notes     TEXT NOT NULL DEFAULT '',
    created   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS phone_lines (
    mac       TEXT NOT NULL REFERENCES phones(mac) ON DELETE CASCADE,
    idx       INTEGER NOT NULL,
    ext       TEXT NOT NULL REFERENCES extensions(ext) ON DELETE CASCADE,
    line_keys INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (mac, idx)
);
CREATE TABLE IF NOT EXISTS phone_keys (
    mac   TEXT NOT NULL REFERENCES phones(mac) ON DELETE CASCADE,
    pos   INTEGER NOT NULL,
    type  TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (mac, pos)
);
CREATE TABLE IF NOT EXISTS seen_devices (
    mac        TEXT PRIMARY KEY,
    ip         TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    model      TEXT NOT NULL DEFAULT '',
    firmware   TEXT NOT NULL DEFAULT '',
    last_file  TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ring_groups (
    num       TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    strategy  TEXT NOT NULL DEFAULT 'ringall',
    ring_time INTEGER NOT NULL DEFAULT 20,
    members   TEXT NOT NULL DEFAULT '',
    failover  TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS trunks (
    name        TEXT PRIMARY KEY,
    host        TEXT NOT NULL,
    port        INTEGER NOT NULL DEFAULT 5060,
    username    TEXT NOT NULL DEFAULT '',
    password    TEXT NOT NULL DEFAULT '',
    register    INTEGER NOT NULL DEFAULT 1,
    from_user   TEXT NOT NULL DEFAULT '',
    from_domain TEXT NOT NULL DEFAULT '',
    callerid    TEXT NOT NULL DEFAULT '',
    codecs      TEXT NOT NULL DEFAULT 'alaw,ulaw,g722'
);
CREATE TABLE IF NOT EXISTS inbound_routes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    did         TEXT NOT NULL UNIQUE,
    destination TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbound_routes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    strip   INTEGER NOT NULL DEFAULT 0,
    prepend TEXT NOT NULL DEFAULT '',
    trunk   TEXT NOT NULL REFERENCES trunks(name) ON DELETE CASCADE
);
"""

# Every setting the system knows about, with its default value.
DEFAULT_SETTINGS = {
    # --- server / SIP ---
    "server_host": "",            # IP or DNS name the phones use for SIP + provisioning
    "http_port": "80",
    "sip_port": "5060",
    "tls_port": "5061",
    "sip_transport": "udp",       # udp | tcp | tls (tls also enables SRTP)
    "reg_expires": "600",
    "external_ip": "",            # public IP for trunks behind NAT
    "local_net": "",              # e.g. 192.168.1.0/24 (comma separated)
    "codecs": "g722,alaw,ulaw",   # order = priority (opus,g722,alaw,ulaw,g729)
    "tone_zone": "hu",
    "timezone_name": "Europe/Budapest",
    # --- provisioning ---
    "prov_auth": "digest",        # none | basic | digest
    "prov_user": "ccxprov",
    "prov_password": "",
    "lock_prov_server": "1",      # write device.prov.* so the phone keeps this server
    "firmware_file": "",          # file in prov/firmware, empty = no upgrade
    "prov_polling": "1",          # nightly config check by phones
    "prov_polling_time": "03:00",
    # --- phone defaults ---
    "phone_admin_password": "",
    "phone_user_password": "",
    "base_profile": "Generic",
    "ntp_server": "pool.ntp.org",
    "gmt_offset": "3600",
    "dst_rule": "eu",             # eu | us | none
    "language": "",               # e.g. English_United_Kingdom, German_Germany
    "clock_24h": "1",
    "digitmap": "",               # empty = generated from the numbering plan
    "paging_enabled": "1",
    "paging_address": "224.0.1.116",
    "paging_port": "5001",
    "intercom_unmute": "1",
    "rest_api": "1",
    "web_ui": "1",
    "softkey_park": "1",
    "softkey_record": "1",
    "site_overrides": "",         # extra Poly parameters for all phones (key=value lines)
    # --- PBX ---
    "inbound_default": "",        # default destination for unmatched DIDs
    # --- admin ---
    "admin_password_hash": "",
    # --- internal state ---
    "dirty": "0",
    "restart_required": "0",
}

SECRET_SETTINGS = ("prov_password", "phone_admin_password")


def gen_secret(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def gen_pin(length: int = 4) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    # One connection per request; FastAPI may create it in a worker thread and use it
    # in the event loop thread, never concurrently.
    conn = sqlite3.connect(str(path or config.DB_PATH), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
    for key in SECRET_SETTINGS:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if not row["value"]:
            conn.execute("UPDATE settings SET value=? WHERE key=?", (gen_secret(14), key))
    conn.commit()


def get_settings(conn: sqlite3.Connection) -> dict:
    values = dict(DEFAULT_SETTINGS)
    values.update({r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")})
    return values


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def mark_dirty(conn: sqlite3.Connection) -> None:
    set_setting(conn, "dirty", "1")


def load_phone(conn: sqlite3.Connection, mac: str) -> dict | None:
    row = conn.execute("SELECT * FROM phones WHERE mac=?", (mac,)).fetchone()
    if not row:
        return None
    phone = dict(row)
    phone["lines"] = [
        dict(r)
        for r in conn.execute(
            "SELECT l.idx, l.ext, l.line_keys, e.name, e.secret FROM phone_lines l "
            "JOIN extensions e ON e.ext = l.ext WHERE l.mac=? ORDER BY l.idx",
            (mac,),
        )
    ]
    phone["keys"] = [
        dict(r) for r in conn.execute("SELECT pos, type, value, label FROM phone_keys WHERE mac=? ORDER BY pos", (mac,))
    ]
    return phone


def snapshot(conn: sqlite3.Connection) -> dict:
    """Everything the config generators need, as plain dicts."""
    macs = [r["mac"] for r in conn.execute("SELECT mac FROM phones ORDER BY mac")]
    return {
        "settings": get_settings(conn),
        "extensions": [dict(r) for r in conn.execute("SELECT * FROM extensions ORDER BY ext")],
        "phones": [load_phone(conn, m) for m in macs],
        "ring_groups": [dict(r) for r in conn.execute("SELECT * FROM ring_groups ORDER BY num")],
        "trunks": [dict(r) for r in conn.execute("SELECT * FROM trunks ORDER BY name")],
        "inbound": [dict(r) for r in conn.execute("SELECT * FROM inbound_routes ORDER BY did")],
        "outbound": [dict(r) for r in conn.execute("SELECT * FROM outbound_routes ORDER BY pattern")],
    }
