import pytest
from fastapi.testclient import TestClient

from ccxpbx import config, db, httpauth

from .test_httpauth import client_response

UA = "FileTransport PolycomCCX-CCX_500-UA/8.1.3.1301"


@pytest.fixture(scope="module")
def client():
    from ccxpbx.main import app
    conn = db.connect()
    db.init_db(conn)
    db.set_setting(conn, "admin_password_hash", httpauth.hash_password("adminpass123"))
    db.set_setting(conn, "server_host", "192.168.1.10")
    conn.commit()
    conn.close()
    with TestClient(app) as c:
        yield c


def login(c):
    r = c.post("/login", data={"username": "admin", "password": "adminpass123"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def prov(c, path, method="GET", content=None):
    r = c.request(method, path, content=content, headers={"User-Agent": UA})
    if r.status_code != 401:
        return r
    s = db.get_settings(db.connect())
    hdr = client_response(r.headers["www-authenticate"], s["prov_user"], s["prov_password"], method, path)
    return c.request(method, path, headers={"Authorization": hdr, "User-Agent": UA}, content=content)


def test_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client.get("/prov/000000000000.cfg").status_code == 401


def test_full_flow(client):
    login(client)
    assert client.get("/").status_code == 200
    for ext, name in (("2001", "Kiss Anna"), ("2002", "Nagy Béla")):
        r = client.post("/extensions/save", data={"is_new": "1", "ext": ext, "name": name, "vm_enabled": "1",
                                                   "vm_pin": "1234", "ring_time": "25", "pickup_group": "1",
                                                   "max_contacts": "1", "in_directory": "1"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/extensions"
    # saving applies right away: the extension is in Asterisk before any phone boots
    assert "exten => 2002,hint,PJSIP/2002" in (config.AST_GEN_DIR / "extensions_generated.conf").read_text()

    # an unknown phone appears on the dashboard after its first provisioning request
    r = prov(client, "/prov/0004f2aabbcc.cfg")
    assert r.status_code == 200 and 'CONFIG_FILES="ccx/site.cfg"' in r.text
    assert "0004f2aabbcc" in client.get("/").text

    r = client.post("/phones/save", data={"is_new": "1", "mac": "00:04:F2:AA:BB:CC", "label": "Recepció",
                                          "line_ext_1": "2001", "line_keys_1": "1",
                                          "key_type_1": "line", "key_value_1": "1",
                                          "key_type_2": "blf", "key_value_2": "2002", "key_label_2": "Béla"},
                    follow_redirects=False)
    assert r.headers["location"] == "/phones/0004f2aabbcc"
    assert client.get("/phones/0004f2aabbcc").status_code == 200

    assert "ccx/0004f2aabbcc-phone.cfg" in prov(client, "/prov/0004f2aabbcc.cfg").text
    r = prov(client, "/prov/ccx/0004f2aabbcc-phone.cfg")
    assert 'reg.1.address="2001"' in r.text and 'attendant.resourceList.1.address="2002"' in r.text
    assert 'voIpProt.server.1.address="192.168.1.10"' in prov(client, "/prov/ccx/site.cfg").text
    assert "<ct>2002</ct>" in prov(client, "/prov/000000000000-directory.xml").text
    assert prov(client, "/prov/ccx/112233445566-phone.cfg").status_code == 404
    assert prov(client, "/prov/a/b/c.cfg").status_code == 404

    # uploads from the phone
    assert prov(client, "/prov/logs/0004f2aabbcc-app.log", "PUT", b"line1\n").status_code == 201
    assert prov(client, "/prov/logs/0004f2aabbcc-app.log", "PUT", b"line2\n").status_code == 201
    assert (config.PROV_DIR / "logs" / "0004f2aabbcc-app.log").read_bytes() == b"line1\nline2\n"
    core = "encl.0004f2aabbcc-9.5.1.0067-CCX500-core.tApp0.11.1791827128.gz.tar.gz"
    assert prov(client, f"/prov/logs/{core}", "PUT", b"core").status_code == 201
    assert prov(client, "/prov/logs/encl.000000000000-core.tar.gz", "PUT", b"x").status_code == 403
    assert prov(client, "/prov/firmware/evil.ld", "PUT", b"x").status_code == 403
    assert prov(client, "/prov/overrides/notamac.cfg", "PUT", b"x").status_code == 403
    page = client.get("/phones/0004f2aabbcc").text
    assert "0004f2aabbcc-app.log" in page and core in page
    assert client.get(f"/phones/0004f2aabbcc/files/logs/{core}").content == b"core"

    seen = db.connect().execute("SELECT model, firmware FROM seen_devices").fetchone()
    assert (seen["model"], seen["firmware"]) == ("CCX500", "8.1.3.1301")

    # apply writes the Asterisk files even when Asterisk is not running
    assert client.post("/apply", data={}, follow_redirects=False).status_code == 303
    assert "PJSIP/2001" in (config.AST_GEN_DIR / "extensions_generated.conf").read_text()
    # Asterisk not running -> it reads the new transports at start, no restart banner
    assert db.get_settings(db.connect())["restart_required"] == "0"

    r = client.post("/phones/0004f2aabbcc/autokeys", follow_redirects=False)
    assert r.status_code == 303
    keys = db.load_phone(db.connect(), "0004f2aabbcc")["keys"]
    assert [k["type"] for k in keys[:3]] == ["line", "park", "blf"]

    for page in ("/extensions", "/phones", "/ringgroups", "/ringgroups/new", "/trunks", "/settings",
                 "/phones/0004f2aabbcc/config", "/asterisk/preview", "/extensions/2001", "/phones/new"):
        assert client.get(page).status_code == 200, page
    assert "password=********" in client.get("/asterisk/preview").text


def test_rest_pages_render(client, monkeypatch):
    from ccxpbx import polyrest
    from .test_restview import INFO
    login(client)
    monkeypatch.setattr(polyrest, "run", lambda ip, pw, name: INFO if name == "info" else {"Status": "2000", "data": {}})
    page = client.get("/phones/0004f2aabbcc/rest/info")
    assert page.status_code == 200
    assert "Eszközinfó" in page.text and "CCX 500" in page.text and "0 nap 0:09:10" in page.text
    assert client.get("/phones/0004f2aabbcc/rest/calls").status_code == 200

    def fail(ip, pw, name):
        raise polyrest.PolyRestError("HTTP 401: teszt")
    monkeypatch.setattr(polyrest, "run", fail)
    page = client.get("/phones/0004f2aabbcc/rest/network")
    assert page.status_code == 200 and "HTTP 401: teszt" in page.text


def test_live_api(client):
    login(client)
    r = client.get("/api/live")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    d = r.json()
    assert set(d) >= {"contacts", "channels", "regs", "unknown", "phones", "counts", "ami_error", "time"}
    assert d["ami_error"]  # no Asterisk in the test environment
    assert d["phones"]["0004f2aabbcc"]["ext"] == "2001"
    assert d["phones"]["0004f2aabbcc"]["registered"] is False
    page = client.get("/").text
    assert 'data-live="dashboard"' in page and "/static/live.js" in page
    assert 'data-live="phones"' in client.get("/phones").text
    assert 'data-live="phone"' in client.get("/phones/0004f2aabbcc").text
    client.post("/logout")
    r = client.get("/api/live", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def browser_form(html: str) -> dict:
    """What a browser submits for the settings form: text inputs, checked boxes, selected options, textareas."""
    import re
    form_html = re.split(r'<form method="post" action="/settings"[^>]*>', html, maxsplit=1)[1].split("</form>", 1)[0]
    data = {}
    for tag in re.findall(r"<input\b[^>]*>", form_html):
        name = re.search(r'name="([^"]+)"', tag)
        if not name:
            continue
        value = re.search(r'value="([^"]*)"', tag)
        if re.search(r'type="(checkbox|radio)"', tag) and "checked" not in tag:
            continue
        data[name.group(1)] = value.group(1) if value else ""
    for name, body in re.findall(r'<select name="([^"]+)">(.*?)</select>', form_html, re.S):
        opts = re.findall(r'<option(?: value="([^"]*)")?([^>]*)>([^<]*)</option>', body)
        chosen = next((o for o in opts if "selected" in o[1]), opts[0])
        data[name] = chosen[0] if chosen[0] or 'value=""' in body else chosen[2]
    for name, body in re.findall(r'<textarea name="([^"]+)"[^>]*>(.*?)</textarea>', form_html, re.S):
        data[name] = body
    return data


def test_settings_form_as_browser(client):
    """Regression: the page has no base_profile field, so saving it used to fail."""
    login(client)
    form = browser_form(client.get("/settings").text)
    assert "base_profile" not in form and "server_host" in form
    form["site_overrides"] = "call.offering.led=1\nind.pattern.active.step.1.color=Green"
    r = client.post("/settings", data=form, follow_redirects=False)
    assert r.status_code == 303
    s = db.get_settings(db.connect())
    assert s["base_profile"] == "Generic"
    assert "call.offering.led=1" in s["site_overrides"]
    assert 'call.offering.led="1"' in prov(client, "/prov/ccx/site.cfg").text


def test_settings_validation(client):
    login(client)
    form = dict(db.get_settings(db.connect()))
    form["server_host"] = "bad host;"
    client.post("/settings", data=form)
    assert db.get_settings(db.connect())["server_host"] == "192.168.1.10"
    form["server_host"] = "192.168.1.20"
    assert client.post("/settings", data=form, follow_redirects=False).status_code == 303
    assert db.get_settings(db.connect())["server_host"] == "192.168.1.20"

    # special characters are fine in the phone admin password ...
    form["phone_admin_password"] = "Adamka12345."
    assert client.post("/settings", data=form, follow_redirects=False).status_code == 303
    assert db.get_settings(db.connect())["phone_admin_password"] == "Adamka12345."
    # ... and a rejected password is never echoed back in the error message
    form["phone_admin_password"] = "has space!"
    page = client.post("/settings", data=form).text
    assert "has space!" not in page and "Telefon admin jelszó: 6-32 karakter" in page
    assert db.get_settings(db.connect())["phone_admin_password"] == "Adamka12345."


def test_home_screen_editor(client):
    login(client)
    mac = "0004f2aabbcc"   # created by test_full_flow
    page = client.get(f"/phones/{mac}/screen")
    assert page.status_code == 200 and 'id="editor-data"' in page.text and "/static/screen.js" in page.text
    assert client.get("/static/screen.js").status_code == 200

    # the editor posts the same key_* fields as the phone form, renumbered in display order
    r = client.post(f"/phones/{mac}/screen", data={
        "wallpaper": "CCXPBX_hatter_02_kapcsolotabla.jpg", "home_hidden": "redial,bogus,settings",
        "key_type_1": "blf", "key_value_1": "2002", "key_label_1": "Béla",
        "key_type_2": "line", "key_value_2": "1",
        "key_type_3": "speeddial", "key_value_3": "112", "key_label_3": "Segély",
    }, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/phones/{mac}/screen"
    cfg = prov(client, f"/prov/ccx/{mac}-phone.cfg").text
    assert 'lineKey.1.category="BLF"' in cfg and 'lineKey.2.category="Line"' in cfg and 'lineKey.3.category="EFK"' in cfg
    assert "CCXPBX_hatter_02_kapcsolotabla.jpg" in cfg
    assert 'homeScreen.redial.enable="0"' in cfg and 'homeScreen.settings.enable="0"' in cfg and "bogus" not in cfg
    assert 'homeScreen.messages.enable' not in cfg   # visible icons keep the phone default

    # an invalid number is rejected and nothing changes
    r = client.post(f"/phones/{mac}/screen", data={"key_type_1": "speeddial", "key_value_1": "abc"}, follow_redirects=False)
    assert r.headers["location"] == f"/phones/{mac}/screen"
    assert 'lineKey.3.category="EFK"' in prov(client, f"/prov/ccx/{mac}-phone.cfg").text


def test_office_hours_editor(client):
    login(client)
    page = client.get("/office-hours")
    assert page.status_code == 200 and 'id="oh-data"' in page.text and "/static/office.js" in page.text
    r = client.post("/office-hours", data={"power_saving": "1", "office_hours": "monday=8-17,saturday=9-12",
                                           "idle_office": "30", "idle_off": "2", "idle_user_ext": "5"}, follow_redirects=False)
    assert r.status_code == 303
    site = prov(client, "/prov/ccx/site.cfg").text
    assert 'powerSaving.enable="1"' in site
    assert 'powerSaving.officeHours.startHour.monday="8"' in site and 'powerSaving.officeHours.duration.monday="9"' in site
    assert 'powerSaving.officeHours.duration.tuesday="0"' in site      # no office hours that day
    assert 'powerSaving.officeHours.duration.saturday="3"' in site
    assert 'powerSaving.idleTimeout.officeHours="30"' in site and 'powerSaving.idleTimeout.offHours="2"' in site

    # invalid spans are rejected and the stored hours stay
    client.post("/office-hours", data={"office_hours": "monday=18-8", "idle_office": "30", "idle_off": "2", "idle_user_ext": "5"})
    assert 'powerSaving.officeHours.startHour.monday="8"' in prov(client, "/prov/ccx/site.cfg").text
    # unchecked box turns power saving off
    client.post("/office-hours", data={"office_hours": "monday=8-17", "idle_office": "30", "idle_off": "2", "idle_user_ext": "5"})
    assert 'powerSaving.enable="0"' in prov(client, "/prov/ccx/site.cfg").text


def test_update_watcher(client):
    import json

    from ccxpbx import updates
    login(client)
    d = updates.update_dir()
    for f in ("status.json", "request", "update.log"):
        (d / f).unlink(missing_ok=True)

    # helper not installed yet: the page explains the one-time install, no request is written
    page = client.get("/updates")
    assert page.status_code == 200 and "még nincs telepítve" in page.text
    client.post("/updates/apply")
    assert not (d / "request").exists()

    d.mkdir(parents=True, exist_ok=True)
    (d / "status.json").write_text(json.dumps({
        "state": "idle", "message": "OK", "checked_at": "2026-11-14T21:00:00+01:00", "repo": "/home/x/repo", "branch": "main",
        "current": {"hash": "abc1234", "date": "2026-11-10T10:00:00+01:00", "subject": "Old"},
        "latest": {"hash": "def5678", "date": "2026-11-14T10:00:00+01:00"},
        "behind": 2, "ahead": 0, "dirty": 0,
        "commits": [{"hash": "def5678", "date": "2026-11-14T10:00:00+01:00", "subject": "Új funkció"},
                    {"hash": "bbb2222", "date": "2026-11-13T10:00:00+01:00", "subject": "Javítás"}]}), encoding="utf-8")
    home = client.get("/").text
    assert "Új CCXPBX verzió érhető el" in home and 'class="nav-badge"' in home
    page = client.get("/updates").text
    assert "Új funkció" in page and "Frissítés most" in page and "abc1234" in page

    r = client.post("/updates/apply", follow_redirects=False)
    assert r.status_code == 303 and (d / "request").read_text() == "apply"
    assert client.get("/api/update").json()["pending"] == "apply"
    client.post("/updates/rm-rf")   # unknown actions are ignored
    assert (d / "request").read_text() == "apply"
    (d / "request").unlink()


def test_home_screen_verify(client, monkeypatch):
    from ccxpbx import polyrest, services
    login(client)
    mac = "0004f2aabbcc"
    monkeypatch.setattr(services, "phone_ip", lambda conn, m, contacts=None: "")
    assert "IP" in client.get(f"/phones/{mac}/screen/verify").json()["error"]

    monkeypatch.setattr(services, "phone_ip", lambda conn, m, contacts=None: "192.0.2.10")
    seen = {}

    def fake_get(ip, password, params):
        seen["params"] = params
        return {p: ("0" if p == "homeScreen.redial.enable" else None) for p in params}
    monkeypatch.setattr(polyrest, "config_get", fake_get)
    d = client.get(f"/phones/{mac}/screen/verify").json()
    rows = {r["key"]: r for r in d["rows"]}
    assert "homeScreen.redial.enable" in seen["params"] and rows["redial"]["phone"] == "0"
    assert rows["redial"]["expected"] == "0" and rows["messages"]["phone"] is None


def test_polyrest_config_get_formats(monkeypatch):
    from ccxpbx import polyrest
    monkeypatch.setattr(polyrest, "call", lambda *a, **k: {"Status": "2000", "data": {"a.b": "1", "c.d": ""}})
    assert polyrest.config_get("x", "y", ["a.b", "c.d", "e.f"]) == {"a.b": "1", "c.d": None, "e.f": None}
    monkeypatch.setattr(polyrest, "call", lambda *a, **k: {"data": [{"name": "a.b", "value": "0"}]})
    assert polyrest.config_get("x", "y", ["a.b"]) == {"a.b": "0"}
