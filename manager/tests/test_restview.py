from ccxpbx import restview

# Real response of a CCX500 on PolyOS 9.5.1 (/api/v1/mgmt/device/info)
INFO = {"Status": "2000", "data": {
    "ModelNumber": "CCX 500", "IPV6Address": "::", "DeviceVendor": "Poly", "FirmwareRelease": "9.5.1.0130",
    "DeviceType": "hardwareEndpoint", "UpTimeSinceLastReboot": "0 Day 0:09:10",
    "IPV4Address": "192.168.10.121", "MACAddress": "64167fe2156a"}}


def test_device_info_is_labelled():
    v = restview.build("info", INFO)
    assert v["title"] == "Eszközinfó" and v["status_ok"]
    rows = {r["label"]: r["value"] for r in v["sections"][0]["rows"]}
    assert rows["Modell"] == "CCX 500"
    assert rows["Firmware"] == "9.5.1.0130"
    assert rows["Üzemidő (utolsó indítás óta)"] == "0 nap 0:09:10"
    assert rows["IPv6 cím"] == "nincs"


def test_list_becomes_table_and_unknown_keys_are_readable():
    data = {"Status": "2000", "data": [
        {"LineNumber": "1", "SIPAddress": "2001@192.168.10.116", "RegistrationStatus": "registered",
         "SomeNewField": "x"}]}
    v = restview.build("lines", data)
    t = v["sections"][0]
    assert t["kind"] == "table"
    assert t["cols"] == ["Vonal", "SIP cím", "Regisztráció", "Some New Field"]
    assert t["rows"][0][2] == {"value": "regisztrált", "tone": "ok"}


def test_error_status_and_empty():
    assert restview.build("calls", {"Status": "4007", "data": []})["status_ok"] is False
    assert restview.build("calls", {"Status": "2000", "data": {}})["sections"] == []
