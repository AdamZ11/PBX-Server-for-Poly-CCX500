import base64
import hashlib
import re

from ccxpbx import httpauth


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()


def client_response(challenge, user, pw, method, uri):
    nonce = re.search(r'nonce="([^"]+)"', challenge).group(1)
    ha1, ha2 = md5(f"{user}:{httpauth.REALM}:{pw}"), md5(f"{method}:{uri}")
    resp = md5(f"{ha1}:{nonce}:00000001:abc:auth:{ha2}")
    return (f'Digest username="{user}", realm="{httpauth.REALM}", nonce="{nonce}", uri="{uri}", '
            f'response="{resp}", qop=auth, nc=00000001, cnonce="abc"')


def test_digest_roundtrip():
    a = httpauth.Authenticator("k")
    hdr = client_response(a.challenge("digest"), "u", "p", "GET", "/prov/x.cfg")
    assert a.check("digest", hdr, "GET", "/prov/x.cfg", "u", "p") == "ok"
    assert a.check("digest", hdr, "GET", "/prov/x.cfg", "u", "wrong") == "fail"
    assert a.check("digest", hdr, "GET", "/prov/other.cfg", "u", "p") == "fail"


def test_basic():
    a = httpauth.Authenticator("k")
    hdr = "Basic " + base64.b64encode(b"u:p").decode()
    assert a.check("basic", hdr, "GET", "/", "u", "p") == "ok"
    assert a.check("digest", hdr, "GET", "/", "u", "p") == "fail"
    assert a.check("none", None, "GET", "/", "u", "p") == "ok"


def test_password_hash():
    h = httpauth.hash_password("correct horse")
    assert httpauth.verify_password("correct horse", h)
    assert not httpauth.verify_password("wrong", h)
