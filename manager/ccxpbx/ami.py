"""Minimal synchronous Asterisk Manager Interface client (no external dependencies)."""
import itertools
import socket

from . import config


class AMIError(RuntimeError):
    pass


class AMI:
    _ids = itertools.count(1)

    def __init__(self, host=None, port=None, user=None, secret=None, timeout=5.0):
        self.host = host or config.AMI_HOST
        self.port = port or config.AMI_PORT
        self.user = user or config.AMI_USER
        self.secret = secret if secret is not None else config.AMI_SECRET
        self.timeout = timeout
        self.sock = None
        self._buf = b""

    def __enter__(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as exc:
            raise AMIError(f"AMI nem elérhető ({self.host}:{self.port}): {exc}") from exc
        self._readline()  # banner
        resp = self.action("Login", Username=self.user, Secret=self.secret, Events="off")[0]
        if resp.get("Response") != "Success":
            raise AMIError(f"AMI bejelentkezés sikertelen: {resp.get('Message')}")
        return self

    def __exit__(self, *exc):
        try:
            self.action("Logoff")
        except Exception:
            pass
        if self.sock:
            self.sock.close()

    # --- low level -----------------------------------------------------
    def _readline(self) -> bytes:
        while b"\r\n" not in self._buf:
            self._recv()
        line, self._buf = self._buf.split(b"\r\n", 1)
        return line

    def _recv(self):
        try:
            chunk = self.sock.recv(65536)
        except OSError as exc:
            raise AMIError(f"AMI olvasási hiba: {exc}") from exc
        if not chunk:
            raise AMIError("AMI kapcsolat lezárult")
        self._buf += chunk

    def _read_message(self) -> dict:
        while b"\r\n\r\n" not in self._buf:
            self._recv()
        raw, self._buf = self._buf.split(b"\r\n\r\n", 1)
        msg: dict = {}
        for line in raw.decode("utf-8", "replace").split("\r\n"):
            key, sep, value = line.partition(":")
            if not sep:
                continue
            key, value = key.strip(), value.strip()
            if key == "Output":
                msg.setdefault("Output", []).append(value)
            else:
                msg[key] = value
        return msg

    def action(self, name: str, **fields) -> list[dict]:
        """Send an action; returns [response, *events] (events only for event lists)."""
        action_id = f"ccx{next(self._ids)}"
        lines = [f"Action: {name}", f"ActionID: {action_id}"]
        for key, value in fields.items():
            values = value if isinstance(value, (list, tuple)) else [value]
            lines += [f"{key}: {v}" for v in values]
        self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        result = []
        while True:
            msg = self._read_message()
            if msg.get("ActionID") != action_id:
                continue
            result.append(msg)
            if len(result) == 1:
                if msg.get("EventList") != "start":
                    return result
            elif msg.get("EventList") == "Complete":
                return result

    # --- helpers -------------------------------------------------------
    def command(self, cmd: str) -> str:
        resp = self.action("Command", Command=cmd)[0]
        if resp.get("Response") == "Error":
            raise AMIError(resp.get("Message", "command failed"))
        return "\n".join(resp.get("Output", []))

    def contacts(self) -> list[dict]:
        return [m for m in self.action("PJSIPShowContacts")[1:] if m.get("Event") == "ContactList"]

    def channels(self) -> list[dict]:
        return [m for m in self.action("CoreShowChannels")[1:] if m.get("Event") == "CoreShowChannel"]

    def registrations(self) -> list[dict]:
        return [m for m in self.action("PJSIPShowRegistrationsOutbound")[1:]
                if m.get("Event") == "OutboundRegistrationDetail"]

    def notify(self, endpoint: str, event: str) -> dict:
        return self.action("PJSIPNotify", Endpoint=endpoint, Variable=f"Event={event}")[0]


def safe_call(fn, default=None):
    """Run fn(ami) and return (result, error_message)."""
    try:
        with AMI() as ami:
            return fn(ami), None
    except AMIError as exc:
        return default, str(exc)
    except OSError as exc:
        return default, f"AMI hiba: {exc}"
