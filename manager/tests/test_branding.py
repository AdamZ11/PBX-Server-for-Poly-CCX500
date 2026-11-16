"""Brand package integration: wallpapers, phone portal (microbrowser), phone UI colours."""
import struct

import pytest

from ccxpbx import ami, config, poly, wallpapers


def jpeg(width=720, height=1280, progressive=False) -> bytes:
    sof = b"\xff\xc2" if progressive else b"\xff\xc0"
    frame = sof + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + frame + b"\xff\xd9"


def test_bundled_wallpapers_are_listed_and_baseline():
    files = [w["file"] for w in wallpapers.available() if w["bundled"]]
    assert files == sorted(wallpapers.LABELS)
    for name in files:
        w, h, progressive = wallpapers.jpeg_info(wallpapers.path(name).read_bytes())
        assert (w, h, progressive) == (720, 1280, False)


def test_upload_rules():
    name, warn = wallpapers.save_upload("Recepcio hatter.jpg", jpeg())
    assert name == "Recepcio_hatter.jpg" and warn is None
    assert (config.WALLPAPER_DIR / name).is_file()
    _, warn = wallpapers.save_upload("kicsi.jpg", jpeg(400, 300))
    assert "400×300" in warn
    with pytest.raises(wallpapers.WallpaperError, match="progresszív"):
        wallpapers.save_upload("prog.jpg", jpeg(progressive=True))
    with pytest.raises(wallpapers.WallpaperError, match="nem JPEG"):
        wallpapers.save_upload("fake.jpg", b"PNG data")
    with pytest.raises(wallpapers.WallpaperError):
        wallpapers.save_upload("../evil.jpg.exe", jpeg())
    with pytest.raises(wallpapers.WallpaperError):
        wallpapers.save_upload("CCXPBX_hatter_01_kozpont.jpg", jpeg())   # brand names are reserved
    assert wallpapers.delete("kicsi.jpg") and not wallpapers.delete("CCXPBX_hatter_01_kozpont.jpg")


def test_phone_params_for_look(snap):
    s = snap["settings"]
    p = poly.site_params(snap)
    assert p["bg.color.bm.1.name"] == "http://192.168.1.10/wallpapers/CCXPBX_hatter_01_kozpont.jpg"
    assert p["mb.main.home"] == "http://192.168.1.10/phone/" and p["homeScreen.application.enable"] == "1"
    assert "ui.statusBar.background" not in p
    s.update(phone_ui_brand="1", wallpaper="", http_port="8080")
    p = poly.site_params(snap)
    assert p["ui.statusBar.background"] == "#0E1116"
    assert p["bg.color.bm.1.name"] == ""
    assert p["mb.main.home"] == "http://192.168.1.10:8080/phone/"
    phone = dict(snap["phones"][0], wallpaper="CCXPBX_hatter_04_papir.jpg")
    assert poly.phone_params(snap, phone)["bg.color.bm.1.name"].endswith("/wallpapers/CCXPBX_hatter_04_papir.jpg")
    assert poly.phone_params(snap, dict(phone, wallpaper="none"))["bg.color.bm.1.name"] == ""
    assert "bg.color.bm.1.name" not in poly.phone_params(snap, dict(phone, wallpaper=""))


@pytest.mark.parametrize("bits,state", [("0", "free"), ("1", "busy"), ("2", "busy"), ("4", "off"), ("8", "ring"),
                                        ("9", "busy"), ("16", "hold"), ("17", "hold"), ("-1", "off"), ("x", "off")])
def test_hint_states(bits, state):
    assert ami.hint_state(bits) == state


def test_public_wallpaper_route_and_portal(monkeypatch):
    from fastapi.testclient import TestClient

    from ccxpbx import db, httpauth, services
    from ccxpbx.main import app

    conn = db.connect()
    db.init_db(conn)
    db.set_setting(conn, "admin_password_hash", httpauth.hash_password("adminpass123"))
    conn.execute("INSERT OR IGNORE INTO extensions(ext,name,secret,vm_pin) VALUES ('2101','Portál Teszt','x'||hex(randomblob(8)),'1234')")
    conn.execute("INSERT OR IGNORE INTO phones(mac,label) VALUES ('0004f2000001','Portál')")
    conn.execute("INSERT OR IGNORE INTO phone_lines(mac,idx,ext) VALUES ('0004f2000001',1,'2101')")
    conn.commit()
    with TestClient(app) as c:
        r = c.get("/wallpapers/CCXPBX_hatter_01_kozpont.jpg")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
        assert c.get("/wallpapers/../ccxpbx.db").status_code == 404

        # an unknown client gets 403, the phone itself (matched by IP) gets the portal
        monkeypatch.setattr(services, "phone_ip", lambda conn, mac, contacts=None: "")
        assert c.get("/phone/").status_code == 403
        monkeypatch.setattr(services, "phone_ip", lambda conn, mac, contacts=None: "testclient" if mac == "0004f2000001" else "")
        page = c.get("/phone/")
        assert page.status_code == 200 and "Portál" in page.text and "2101" in page.text and "Telefonkönyv" in page.text
        for view in ("directory", "parked", "codes", "system"):
            assert c.get(f"/phone/{view}").status_code == 200, view
        assert "*97" in c.get("/phone/codes").text
        assert "tel:2101" not in c.get("/phone/directory").text   # no call link to yourself

        # admin preview of any phone with ?mac=
        monkeypatch.setattr(services, "phone_ip", lambda conn, mac, contacts=None: "")
        c.post("/login", data={"username": "admin", "password": "adminpass123"})
        assert c.get("/phone/?mac=0004f2000001").status_code == 200
        assert c.get("/phone/?mac=ffffffffffff").status_code == 403
