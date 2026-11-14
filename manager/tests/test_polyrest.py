"""Poly REST client against a fake phone that challenges exactly like a CCX500 on PolyOS 9.5.1."""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ccxpbx import polyrest

PASSWORD = "Adamka12345."
REALM = "API Authentication"
NONCE = "NjgwMGVmN2I4ZGNmMTE4ZDhmYTgxOGQ2NmRmMmU2YTQ6NDIwOTky"


class FakePhone(BaseHTTPRequestHandler):
    attempts: list = []   # Authorization headers received
    offer = ("SHA-256", "MD5")

    def log_message(self, *args):
        pass

    def _check(self) -> bool:
        auth = self.headers.get("Authorization")
        if not auth:
            return False
        FakePhone.attempts.append(auth)
        params = dict(polyrest.parse_challenges([auth])[0][1])
        algo = params.get("algorithm", "MD5")
        h = {"SHA-256": hashlib.sha256, "MD5": hashlib.md5}[algo]
        ha1 = h(f"Polycom:{REALM}:{PASSWORD}".encode()).hexdigest()
        ha2 = h(f"{self.command}:{params['uri']}".encode()).hexdigest()
        expected = h(f"{ha1}:{NONCE}:{ha2}".encode()).hexdigest()
        return auth.startswith("Digest ") and params.get("response") == expected and params["uri"] == self.path

    def _handle(self):
        if self.command == "POST":
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if not self._check():
            self.send_response(401)
            for algo in FakePhone.offer:
                self.send_header("WWW-Authenticate",
                                 f'Digest realm="{REALM}", nonce="{NONCE}", algorithm="{algo}"')
            self.end_headers()
            return
        body = json.dumps({"Status": "2000", "data": {"ModelNumber": "CCX500", "Path": self.path}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _handle
    do_POST = _handle


@pytest.fixture
def phone():
    FakePhone.attempts = []
    FakePhone.offer = ("SHA-256", "MD5")
    server = HTTPServer(("127.0.0.1", 0), FakePhone)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"127.0.0.1:{server.server_port}"
    server.shutdown()


def test_digest_sha256_like_ccx500(phone):
    data = polyrest.call(phone, PASSWORD, "GET", "/api/v1/mgmt/device/info", schemes=("http",))
    assert data["data"]["ModelNumber"] == "CCX500"
    assert len(FakePhone.attempts) == 1 and "algorithm=SHA-256" in FakePhone.attempts[0]


def test_digest_md5_only(phone):
    FakePhone.offer = ("MD5",)
    data = polyrest.call(phone, PASSWORD, "POST", "/api/v1/mgmt/safeRestart", schemes=("http",))
    assert data["Status"] == "2000"
    assert "algorithm=MD5" in FakePhone.attempts[0]


def test_wrong_password_makes_a_single_attempt(phone):
    with pytest.raises(polyrest.PolyRestError, match="HTTP 401"):
        polyrest.call(phone, "wrong", "GET", "/api/v1/mgmt/device/info", schemes=("http",))
    assert len(FakePhone.attempts) == 1  # no retries that would push the account into lockout


def test_basic_only_for_old_firmware():
    challenges = polyrest.parse_challenges(['Basic realm="Polycom"'])
    assert polyrest.authorization(challenges, "GET", "/x", "pw").startswith("Basic ")
