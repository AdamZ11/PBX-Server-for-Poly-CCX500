import pytest

from ccxpbx import ami, db, services


def test_generated_secrets_have_no_lookalikes():
    s = "".join(db.gen_secret(200) for _ in range(20))
    assert not set(s) & set("lI1Oo0")


class FakeAMI:
    def __init__(self, exc):
        self.exc = exc

    def command(self, cmd):
        assert cmd == "core restart gracefully"
        if self.exc:
            raise self.exc
        return ""


@pytest.mark.parametrize("text,expected", [
    ("FileTransport PolycomCCX-CCX_500-UA/8.1.3.1301", ("CCX500", "8.1.3.1301")),
    ("PolyCCX-CCX_500-UA/9.5.1.0130", ("CCX500", "9.5.1.0130")),  # real CCX500, PolyOS 9.5.1
    ("64167fe2156a-encl.64167fe2156a-9.5.1.0067-CCX500-core.tapp0.11.1791827128.gz.tar.gz",
     ("CCX500", "9.5.1.0067")),
    ("Poly/CCX500 9.5.1.0130 (64167fe2156a)", ("CCX500", "9.5.1.0130")),
    ("Mozilla/5.0 (X11; Linux x86_64)", ("", "")),
])
def test_parse_user_agent(text, expected):
    assert services.parse_user_agent(text) == expected


def test_localtime_filter():
    from ccxpbx.web import localtime
    assert localtime("2026-11-14 10:10:50", "UTC") == "2026-11-14 10:10:50"
    assert localtime("", "UTC") == ""
    assert localtime("garbage", "UTC") == "garbage"


def test_server_host_mismatch(monkeypatch):
    monkeypatch.setattr(services, "local_ips", lambda: {"192.168.10.116"})
    assert services.server_host_mismatch("192.168.10.132") == ["192.168.10.116"]
    assert services.server_host_mismatch("192.168.10.116") is None
    assert services.server_host_mismatch("pbx.local") is None  # DNS names are not checked
    monkeypatch.setattr(services, "local_ips", lambda: set())
    assert services.server_host_mismatch("192.168.10.132") is None


def test_sync_phones_only_registered(monkeypatch):
    from ccxpbx import web

    class Req:
        session = {}

    sent = []
    monkeypatch.setattr(web.ami, "safe_call", lambda fn, default=None: ([{"Endpoint": "2001"}], None))
    monkeypatch.setattr(web.services, "primary_endpoint", lambda conn, mac: {"aa": "2001", "bb": "2002"}[mac])
    monkeypatch.setattr(web.services, "notify_phone", lambda conn, mac, reboot=False: sent.append(mac))
    req = Req()
    web.sync_phones(req, None, ["aa", "bb"])
    assert sent == ["aa"]  # bb is not registered: it gets the config at its next boot
    assert "1 telefon megkapta" in req.session["flash"][0][1]
    assert "1 nem regisztrált" in req.session["flash"][0][1]


def test_restart_dropped_connection_is_success():
    services.restart_asterisk(FakeAMI(ami.AMIError("AMI kapcsolat lezárult")))
    services.restart_asterisk(FakeAMI(None))


def test_restart_other_errors_are_reported():
    with pytest.raises(ami.AMIError):
        services.restart_asterisk(FakeAMI(ami.AMIError("Permission denied")))


def _fw_db(rows):
    conn = db.connect(":memory:")
    db.init_db(conn)
    for mac, label, fw, days_ago in rows:
        conn.execute("INSERT INTO phones(mac, label) VALUES (?, ?)", (mac, label))
        if days_ago is not None:
            conn.execute("INSERT INTO seen_devices(mac, ip, firmware, last_seen) VALUES (?, '', ?, datetime('now', ?))",
                         (mac, fw, f"-{days_ago} days"))
    return conn


def test_firmware_report_against_selected_file():
    conn = _fw_db([("aa", "A", "9.5.1.0130", 0), ("bb", "B", "9.2.0.1000", 0), ("cc", "C", "", None)])
    fw = services.firmware_report(conn, {"firmware_file": "CCX500-9.5.1.0130.zip"})
    assert fw["target"] == "9.5.1.0130"
    states = {r["mac"]: r["state"] for r in fw["phones"]}
    assert states == {"aa": "ok", "bb": "pending", "cc": "never"}
    assert fw["by_mac"]["bb"]["older"] and fw["pending"] == 1 and fw["issues"] == 1
    assert fw["versions"] == [("9.5.1.0130", 1), ("9.2.0.1000", 1)]   # tie: newer first


def test_firmware_report_without_target_uses_majority_and_flags_stale():
    conn = _fw_db([("aa", "A", "9.5.1.0130", 0), ("bb", "B", "9.5.1.0130", 5), ("cc", "C", "9.2.0.1000", 0)])
    fw = services.firmware_report(conn, {"firmware_file": ""})
    assert fw["reference"] == "9.5.1.0130" and fw["mixed"]
    assert fw["by_mac"]["cc"]["state"] == "differs" and fw["differs"] == 1
    assert fw["by_mac"]["bb"]["stale_days"] == 5 and fw["stale"] == 1
    assert fw["issues"] == 2


def test_firmware_report_unparsable_file_name():
    conn = _fw_db([("aa", "A", "9.5.1.0130", 0), ("bb", "B", "9.5.1.0130", 0)])
    fw = services.firmware_report(conn, {"firmware_file": "sip.ld"})
    assert fw["target_unparsed"] and not fw["issues"] and not fw["mixed"]


def test_update_status_in_docker(monkeypatch):
    from ccxpbx import updates
    monkeypatch.setenv("CCXPBX_DOCKER", "1")
    monkeypatch.setenv("CCXPBX_VERSION", "abc1234")
    st = updates.status()
    assert st["docker"] and st["version"] == "abc1234" and not st["available"] and not st["installed"]


def test_cli_init_sets_http_port(capsys):
    from ccxpbx import cli
    assert cli.main(["init", "--http-port", "8080"]) == 0
    assert db.get_settings(db.connect())["http_port"] == "8080"
    assert ":8080/prov" in capsys.readouterr().out
    assert cli.main(["init", "--http-port", "x"]) == 1
    assert cli.main(["init", "--http-port", "80"]) == 0
