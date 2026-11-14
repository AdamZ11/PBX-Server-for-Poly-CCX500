"""Poly REST API client (endpoint management directly on the phone).

Enabled by apps.restapi.enabled=1 in site.cfg; authenticates as user "Polycom" with
the phone's admin password. PolyOS 9 (CCX500 9.5.1) answers with
    WWW-Authenticate: Digest realm="API Authentication", algorithm="SHA-256" (and "MD5")
so the client first asks without credentials, then answers the challenge the phone
actually sent. Never sending a guessed scheme matters: every rejected attempt counts
towards the phone's account lockout. Older UC Software phones that offer only Basic
still work.

Phones use self-signed certificates, so certificate verification is disabled - only
use on a trusted LAN.
"""
import base64
import hashlib
import json
import re
import secrets
import ssl
import urllib.error
import urllib.request

USER = "Polycom"

ENDPOINTS = {
    "info": ("GET", "/api/v1/mgmt/device/info"),
    "network": ("GET", "/api/v1/mgmt/network/info"),
    "lines": ("GET", "/api/v1/mgmt/lineInfo"),
    "calls": ("GET", "/api/v1/webCallControl/callStatus"),
    "restart": ("POST", "/api/v1/mgmt/safeRestart"),
    "reboot": ("POST", "/api/v1/mgmt/safeReboot"),
}

_PARAM_RE = re.compile(r'(\w+)=(?:"([^"]*)"|([^\s,]+))')
_HASHES = {"SHA-256": hashlib.sha256, "MD5": hashlib.md5}


class PolyRestError(RuntimeError):
    pass


def _ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _send(url: str, method: str, data: bytes | None, auth: str | None, timeout: float):
    """Returns (status, headers, body). HTTP error statuses are returned, not raised."""
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("Authorization", auth)
    ctx = _ctx() if url.startswith("https:") else None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def parse_challenges(headers) -> list[tuple[str, dict]]:
    """All WWW-Authenticate challenges as (scheme, params)."""
    values = headers.get_all("WWW-Authenticate") if hasattr(headers, "get_all") else headers
    out = []
    for value in values or []:
        scheme, _, rest = value.strip().partition(" ")
        params = {m.group(1).lower(): m.group(2) if m.group(2) is not None else m.group(3)
                  for m in _PARAM_RE.finditer(rest)}
        out.append((scheme.lower(), params))
    return out


def authorization(challenges, method: str, uri: str, password: str) -> str | None:
    """Build the Authorization header for the strongest challenge offered."""
    digests = {(p.get("algorithm") or "MD5").upper(): p for s, p in challenges if s == "digest"}
    for algo in ("SHA-256", "MD5"):
        if algo in digests:
            return _digest(digests[algo], algo, method, uri, password)
    if any(s == "basic" for s, _ in challenges):
        return "Basic " + base64.b64encode(f"{USER}:{password}".encode()).decode()
    return None


def _digest(p: dict, algo: str, method: str, uri: str, password: str) -> str:
    h = lambda text: _HASHES[algo](text.encode()).hexdigest()  # noqa: E731
    ha1 = h(f"{USER}:{p.get('realm', '')}:{password}")
    ha2 = h(f"{method}:{uri}")
    fields = [f'username="{USER}"', f'realm="{p.get("realm", "")}"', f'nonce="{p.get("nonce", "")}"',
              f'uri="{uri}"', f"algorithm={algo}"]
    qops = [q.strip() for q in p.get("qop", "").split(",") if q.strip()]
    if "auth" in qops:
        nc, cnonce = "00000001", secrets.token_hex(8)
        response = h(f"{ha1}:{p.get('nonce', '')}:{nc}:{cnonce}:auth:{ha2}")
        fields += ["qop=auth", f"nc={nc}", f'cnonce="{cnonce}"']
    else:
        response = h(f"{ha1}:{p.get('nonce', '')}:{ha2}")
    fields.append(f'response="{response}"')
    if p.get("opaque"):
        fields.append(f'opaque="{p["opaque"]}"')
    return "Digest " + ", ".join(fields)


def _result(status: int, body: bytes):
    raw = body.decode("utf-8", "replace")
    try:
        return json.loads(raw) if raw else {"Status": str(status)}
    except json.JSONDecodeError:
        return {"raw": raw}


def call(ip: str, password: str, method: str, path: str, body: dict | None = None,
         timeout: float = 6.0, schemes=("https", "http")):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    last_error = None
    for scheme in schemes:
        url = f"{scheme}://{ip}{path}"
        try:
            status, headers, resp_body = _send(url, method, data, None, timeout)
            if status == 401:
                auth = authorization(parse_challenges(headers), method, path, password)
                if not auth:
                    raise PolyRestError("A telefon ismeretlen hitelesítési módot kér a REST API-hoz.")
                status, headers, resp_body = _send(url, method, data, auth, timeout)
        except (urllib.error.URLError, OSError) as exc:
            last_error = str(getattr(exc, "reason", exc))
            continue
        if 200 <= status < 300:
            return _result(status, resp_body)
        if status == 401:
            raise PolyRestError(
                "HTTP 401: a telefon nem fogadta el az admin jelszót, vagy a 'Polycom' fiók zárolva van. "
                "Ne próbálkozz újra, mert minden sikertelen hívás a zárolás felé visz. Gyári visszaállítás "
                "után a jelszó 456, amíg a telefon le nem tölti a szerver konfigját.")
        if status == 403:
            raise PolyRestError("HTTP 403: a REST API ki van kapcsolva a telefonon "
                                "(apps.restapi.enabled), vagy a fiók zárolva van.")
        last_error = f"HTTP {status}"
    raise PolyRestError(f"REST hívás sikertelen ({ip}{path}): {last_error}")


def run(ip: str, password: str, name: str):
    method, path = ENDPOINTS[name]
    return call(ip, password, method, path)


def dial(ip: str, password: str, number: str, line: int = 1):
    return call(ip, password, "POST", "/api/v1/callctrl/dial",
                {"data": {"Dest": number, "Line": str(line), "Type": "SIP"}})


def _config_value(v) -> str | None:
    """Normalise one value of a mgmt/config/get answer (plain value, bool, or {"Value": ..., "Source": ...})."""
    if isinstance(v, dict):
        v = next((v[k] for k in ("Value", "value", "CurrentValue", "currentValue") if k in v), None)
    if isinstance(v, bool):
        return "1" if v else "0"
    if v is None or v == "":
        return None
    text = str(v).strip()
    return {"true": "1", "false": "0", "enabled": "1", "disabled": "0"}.get(text.lower(), text)


def config_get(ip: str, password: str, params: list[str], raw: bool = False):
    """Values the phone actually uses (POST /api/v1/mgmt/config/get). None = the phone did not report it.
    With raw=True also returns the phone's answer for troubleshooting."""
    resp = call(ip, password, "POST", "/api/v1/mgmt/config/get", {"data": list(params)})
    data = resp.get("data") if isinstance(resp, dict) else None
    if isinstance(data, list):   # some firmware answers with [{"name": ..., "value": ...}]
        data = {d.get("name") or d.get("Name"): d for d in data if isinstance(d, dict)}
    if not isinstance(data, dict):
        raise PolyRestError(f"Váratlan válasz a telefontól: {str(resp)[:200]}")
    values = {p: _config_value(data.get(p)) for p in params}
    return (values, resp) if raw else values
