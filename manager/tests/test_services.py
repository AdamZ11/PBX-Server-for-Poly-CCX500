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
