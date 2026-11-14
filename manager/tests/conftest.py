import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="ccxpbx-test-"))
os.environ["CCXPBX_DATA"] = str(_tmp / "data")
os.environ["CCXPBX_AST_DIR"] = str(_tmp / "asterisk")
os.environ["CCXPBX_TLS_CA"] = str(_tmp / "none-ca.crt")
os.environ["CCXPBX_SECRET_KEY"] = "test-secret-key"
os.environ["CCXPBX_AMI_PORT"] = "1"  # nothing listens -> AMI errors are handled
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


@pytest.fixture
def snap():
    from ccxpbx import db
    settings = dict(db.DEFAULT_SETTINGS)
    settings.update(server_host="192.168.1.10", prov_password="provpass123", phone_admin_password="adm12345")
    exts = [
        dict(ext="2001", name="Kiss Anna", secret="a" * 20, vm_enabled=1, vm_pin="1234", email="", ring_time=25,
             record=0, pickup_group="1", max_contacts=1, in_directory=1, page_member=1),
        dict(ext="2002", name="Nagy Béla; & <x>", secret="b" * 20, vm_enabled=0, vm_pin="", email="", ring_time=20,
             record=1, pickup_group="1", max_contacts=2, in_directory=1, page_member=0),
    ]
    phone = {"mac": "0004f2aabbcc", "label": "Recepció", "overrides": "up.backlight.idleIntensity=1",
             "lines": [{"idx": 1, "ext": "2001", "line_keys": 2, "name": "Kiss Anna", "secret": "a" * 20}],
             "keys": [{"pos": 1, "type": "line", "value": "1", "label": ""},
                      {"pos": 2, "type": "park", "value": "", "label": "Park"},
                      {"pos": 3, "type": "blf", "value": "2002", "label": "Béla"},
                      {"pos": 4, "type": "speeddial", "value": "0612345678", "label": "Iroda"},
                      {"pos": 5, "type": "unassigned", "value": "", "label": ""}]}
    return {"settings": settings, "extensions": exts, "phones": [phone],
            "ring_groups": [dict(num="6000", name="Sales", strategy="ringall", ring_time=20,
                                 members="2001,2002", failover="vm:2001")],
            "trunks": [dict(name="prov1", host="sip.example.hu", port=5060, username="user1", password="p;ss",
                            register=1, from_user="", from_domain="", callerid="3612345678", codecs="alaw,ulaw")],
            "inbound": [dict(id=1, did="3612345678", destination="6000")],
            "outbound": [dict(id=1, pattern="_0.", strip=1, prepend="", trunk="prov1"),
                         dict(id=2, pattern="112", strip=0, prepend="", trunk="prov1")]}
