"""Turns Poly REST API JSON into labelled sections for the phone status pages."""
import re

TITLES = {
    "info": "Eszközinfó",
    "network": "Hálózat",
    "lines": "Vonalak",
    "calls": "Hívásállapot",
}

# Hungarian labels for keys the CCX500 (PolyOS 9.5.1) returns; unknown keys get a readable fallback.
LABELS = {
    "ModelNumber": "Modell",
    "DeviceVendor": "Gyártó",
    "DeviceType": "Eszköz típusa",
    "FirmwareRelease": "Firmware",
    "UpTimeSinceLastReboot": "Üzemidő (utolsó indítás óta)",
    "IPV4Address": "IPv4 cím",
    "IPV6Address": "IPv6 cím",
    "MACAddress": "MAC cím",
    "SubnetMask": "Alhálózati maszk",
    "DefaultGateway": "Alapértelmezett átjáró",
    "DNSServer": "DNS szerver",
    "AlternateDNSServer": "Másodlagos DNS",
    "DHCPServer": "DHCP szerver",
    "DHCPEnabled": "DHCP",
    "DHCPBootServerOption": "DHCP boot szerver opció",
    "DHCPBootServerUseOption": "DHCP boot szerver mód",
    "DHCPBootServerOptionType": "DHCP boot opció típusa",
    "DHCPOption60Format": "DHCP option 60 formátum",
    "ProvServerAddress": "Provisioning szerver",
    "ProvServerUser": "Provisioning felhasználó",
    "ProvServerType": "Provisioning típus",
    "VLANID": "VLAN azonosító",
    "VLANDiscoveryMode": "VLAN felderítés",
    "VLANIDOption": "VLAN DHCP opció",
    "LLDPEnabled": "LLDP",
    "CDPEnabled": "CDP",
    "SNTPAddress": "NTP szerver",
    "ZeroTouchEnabled": "Zero Touch",
    "LineNumber": "Vonal",
    "Label": "Felirat",
    "SIPAddress": "SIP cím",
    "UserID": "Felhasználó",
    "RegistrationStatus": "Regisztráció",
    "ProxyAddress": "SIP szerver",
    "Port": "Port",
    "Protocol": "Protokoll",
    "LineType": "Vonal típusa",
    "CallHandle": "Hívás azonosító",
    "CallState": "Állapot",
    "CallType": "Típus",
    "RemotePartyName": "Távoli fél",
    "RemotePartyNumber": "Távoli szám",
    "DurationInSeconds": "Időtartam (mp)",
    "StartTime": "Kezdés",
    "Muted": "Némítva",
    "Ringing": "Csörög",
}

# Common values translated for display; the colour (tone) is decided on the original value.
VALUES = {
    "registered": "regisztrált",
    "unregistered": "nincs regisztrálva",
    "hardwareendpoint": "hardveres telefon",
    "connected": "kapcsolódva",
    "active": "aktív",
    "ringing": "csörög",
    "hold": "tartva",
    "idle": "szabad",
}

_GOOD = {"registered", "active", "connected", "true", "enabled", "up", "2000"}
_BAD = {"unregistered", "failed", "false", "disabled", "error", "down"}


def label(key: str) -> str:
    if key in LABELS:
        return LABELS[key]
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", key)
    return words[:1].upper() + words[1:]


def fmt(key: str, value) -> str:
    if value is None or value == "":
        return "–"
    if isinstance(value, bool):
        return "igen" if value else "nem"
    text = str(value)
    if text.lower() in ("true", "false"):
        return "igen" if text.lower() == "true" else "nem"
    if key == "UpTimeSinceLastReboot":
        text = re.sub(r"\bDays?\b", "nap", text)
    if key.endswith("IPV6Address") and text == "::":
        return "nincs"
    return VALUES.get(text.lower(), text)


def tone(value) -> str:
    """'ok' / 'err' / '' to colour status-like values."""
    v = str(value).strip().lower()
    if v in _GOOD:
        return "ok"
    if v in _BAD:
        return "err"
    return ""


def _kv(title: str, d: dict) -> dict:
    return {"kind": "kv", "title": title,
            "rows": [{"label": label(k), "value": fmt(k, v), "tone": tone(v) if "Status" in k or "State" in k else ""}
                     for k, v in d.items() if not isinstance(v, (dict, list))]}


def _table(title: str, items: list) -> dict:
    cols: list[str] = []
    for item in items:
        for k, v in item.items():
            if k not in cols and not isinstance(v, (dict, list)):
                cols.append(k)
    return {"kind": "table", "title": title, "cols": [label(c) for c in cols],
            "rows": [[{"value": fmt(c, item.get(c)), "tone": tone(item.get(c)) if "Status" in c or "State" in c else ""}
                      for c in cols] for item in items]}


def build(name: str, data) -> dict:
    """{'title', 'status', 'status_ok', 'sections': [...]} for the template."""
    status = data.get("Status") if isinstance(data, dict) else None
    payload = data.get("data", data) if isinstance(data, dict) else data
    sections: list[dict] = []

    def walk(title: str, obj):
        if isinstance(obj, dict):
            kv = _kv(title, obj)
            if kv["rows"]:
                sections.append(kv)
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    walk(label(k), v)
        elif isinstance(obj, list):
            dicts = [x for x in obj if isinstance(x, dict)]
            if dicts:
                sections.append(_table(title, dicts))
            scalars = [x for x in obj if not isinstance(x, dict)]
            if scalars:
                sections.append({"kind": "kv", "title": title,
                                 "rows": [{"label": str(i + 1), "value": fmt("", x), "tone": ""}
                                          for i, x in enumerate(scalars)]})
        elif obj not in (None, ""):
            sections.append({"kind": "kv", "title": title, "rows": [{"label": "Érték", "value": fmt("", obj),
                                                                     "tone": ""}]})

    walk(TITLES.get(name, name), payload)
    return {"title": TITLES.get(name, name), "status": status, "status_ok": status in (None, "2000"),
            "sections": sections}
