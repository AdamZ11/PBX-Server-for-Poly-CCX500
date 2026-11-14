"""Poly UC Software REST API client (endpoint management directly on the phone).

Enabled by apps.restapi.enabled=1 in site.cfg; authenticates with the phone's
admin password (user "Polycom"). Phones use self-signed certificates, so
certificate verification is disabled - only use on a trusted LAN.
"""
import base64
import json
import ssl
import urllib.error
import urllib.request

ENDPOINTS = {
    "info": ("GET", "/api/v1/mgmt/device/info"),
    "network": ("GET", "/api/v1/mgmt/network/info"),
    "lines": ("GET", "/api/v1/mgmt/lineInfo"),
    "calls": ("GET", "/api/v1/webCallControl/callStatus"),
    "restart": ("POST", "/api/v1/mgmt/safeRestart"),
    "reboot": ("POST", "/api/v1/mgmt/safeReboot"),
}


class PolyRestError(RuntimeError):
    pass


def _ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def call(ip: str, password: str, method: str, path: str, body: dict | None = None, timeout: float = 6.0):
    token = base64.b64encode(f"Polycom:{password}".encode()).decode()
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    last_error = None
    for scheme in ("https", "http"):
        req = urllib.request.Request(f"{scheme}://{ip}{path}", data=data, method=method)
        req.add_header("Authorization", f"Basic {token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx() if scheme == "https" else None) as resp:
                raw = resp.read().decode("utf-8", "replace")
                try:
                    return json.loads(raw) if raw else {"Status": str(resp.status)}
                except json.JSONDecodeError:
                    return {"raw": raw}
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise PolyRestError("A telefon elutasította a hitelesítést (admin jelszó / REST API engedélyezve?)")
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, OSError) as exc:
            last_error = str(getattr(exc, "reason", exc))
    raise PolyRestError(f"REST hívás sikertelen ({ip}{path}): {last_error}")


def run(ip: str, password: str, name: str):
    method, path = ENDPOINTS[name]
    return call(ip, password, method, path)


def dial(ip: str, password: str, number: str, line: int = 1):
    return call(ip, password, "POST", "/api/v1/callctrl/dial",
                {"data": {"Dest": number, "Line": str(line), "Type": "SIP"}})
