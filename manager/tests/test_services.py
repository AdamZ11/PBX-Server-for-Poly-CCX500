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


def test_restart_dropped_connection_is_success():
    services.restart_asterisk(FakeAMI(ami.AMIError("AMI kapcsolat lezárult")))
    services.restart_asterisk(FakeAMI(None))


def test_restart_other_errors_are_reported():
    with pytest.raises(ami.AMIError):
        services.restart_asterisk(FakeAMI(ami.AMIError("Permission denied")))
