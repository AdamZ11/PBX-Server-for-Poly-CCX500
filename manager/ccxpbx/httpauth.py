"""HTTP Basic / Digest (RFC 2617, MD5, qop=auth) for the provisioning server.

Nonces are stateless: "<timestamp>:<hmac>" so no server-side storage is needed.
"""
import base64
import hashlib
import hmac
import re
import secrets
import time

REALM = "ccxpbx-provisioning"
NONCE_TTL = 300

_PARAM_RE = re.compile(r'(\w+)=(?:"([^"]*)"|([^\s,]+))')


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


class Authenticator:
    def __init__(self, secret: str):
        self.secret = secret.encode()

    def _sign(self, ts: str) -> str:
        return hmac.new(self.secret, ts.encode(), hashlib.sha256).hexdigest()[:32]

    def make_nonce(self) -> str:
        ts = str(int(time.time()))
        return base64.b64encode(f"{ts}:{self._sign(ts)}".encode()).decode()

    def nonce_state(self, nonce: str) -> str:
        """'ok', 'stale' or 'bad'."""
        try:
            ts, sig = base64.b64decode(nonce).decode().split(":", 1)
        except Exception:
            return "bad"
        if not hmac.compare_digest(sig, self._sign(ts)):
            return "bad"
        return "ok" if time.time() - int(ts) <= NONCE_TTL else "stale"

    def challenge(self, mode: str, stale: bool = False) -> str:
        if mode == "basic":
            return f'Basic realm="{REALM}"'
        return (f'Digest realm="{REALM}", qop="auth", algorithm=MD5, '
                f'nonce="{self.make_nonce()}", opaque="{secrets.token_hex(8)}"'
                + (", stale=true" if stale else ""))

    def check(self, mode: str, header: str | None, method: str, path: str, user: str, password: str) -> str:
        """Returns 'ok', 'stale' or 'fail'."""
        if mode == "none":
            return "ok"
        if not header:
            return "fail"
        scheme, _, rest = header.partition(" ")
        scheme = scheme.lower()
        if mode == "basic" and scheme == "basic":
            try:
                u, _, p = base64.b64decode(rest.strip()).decode().partition(":")
            except Exception:
                return "fail"
            ok = hmac.compare_digest(u, user) & hmac.compare_digest(p, password)
            return "ok" if ok else "fail"
        if mode != "digest" or scheme != "digest":
            return "fail"
        params = {m.group(1).lower(): m.group(2) if m.group(2) is not None else m.group(3)
                  for m in _PARAM_RE.finditer(rest)}
        need = ("username", "realm", "nonce", "uri", "response")
        if any(k not in params for k in need) or params["realm"] != REALM:
            return "fail"
        if params["uri"].split("?", 1)[0] != path:
            return "fail"
        if not hmac.compare_digest(params["username"], user):
            return "fail"
        state = self.nonce_state(params["nonce"])
        if state == "bad":
            return "fail"
        ha1 = _md5(f"{user}:{REALM}:{password}")
        ha2 = _md5(f"{method}:{params['uri']}")
        if params.get("qop"):
            if params["qop"] != "auth" or "nc" not in params or "cnonce" not in params:
                return "fail"
            expected = _md5(f"{ha1}:{params['nonce']}:{params['nc']}:{params['cnonce']}:auth:{ha2}")
        else:
            expected = _md5(f"{ha1}:{params['nonce']}:{ha2}")
        if not hmac.compare_digest(expected, params["response"].lower()):
            return "fail"
        return "stale" if state == "stale" else "ok"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(calc.hex(), digest)
