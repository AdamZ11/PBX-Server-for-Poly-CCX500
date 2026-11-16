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
                # list actions announce themselves with "EventList: start" (some older
                # ones only say "... will follow" in Message)
                is_list = msg.get("EventList") == "start" or "follow" in msg.get("Message", "").lower()
                if msg.get("Response") == "Error" or not is_list:
                    return result
            elif msg.get("EventList") == "Complete" or msg.get("Event", "").endswith("Complete"):
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

    def extension_states(self) -> dict[str, str]:
        """{exten: 'free'|'ring'|'busy'|'off'} from the dialplan hints."""
        states = {}
        for m in self.action("ExtensionStateList")[1:]:
            if m.get("Event") == "ExtensionStatus" and m.get("Exten"):
                states[m["Exten"]] = hint_state(m.get("Status", "-1"))
        return states

    def mailbox_count(self, mailbox: str) -> tuple[int, int]:
        """(new, old) voicemail messages."""
        resp = self.action("MailboxCount", Mailbox=mailbox)[0]
        try:
            return int(resp.get("NewMessages", 0)), int(resp.get("OldMessages", 0))
        except ValueError:
            return 0, 0

    def originate(self, channel: str, callerid: str, *, exten: str = "", context: str = "from-internal",
                  application: str = "", data: str = "") -> dict:
        """Ring `channel` first; when answered, dial `exten` (or run `application`). Returns at once."""
        fields = {"Channel": channel, "CallerID": callerid, "Async": "true", "Timeout": "30000"}
        if application:
            fields.update(Application=application, Data=data)
        else:
            fields.update(Context=context, Exten=exten, Priority="1")
        resp = self.action("Originate", **fields)[0]
        if resp.get("Response") == "Error":
            raise AMIError(resp.get("Message", "originate failed"))
        return resp

    def hangup(self, channel: str) -> None:
        resp = self.action("Hangup", Channel=channel)[0]
        if resp.get("Response") == "Error":
            raise AMIError(resp.get("Message", "hangup failed"))

    def parked_calls(self) -> list[dict]:
        return [m for m in self.action("ParkedCalls")[1:] if m.get("Event") == "ParkedCall"]


def hint_state(status: str) -> str:
    """Asterisk extension state bits -> CCXPBX status (free / ring / hold / busy / off)."""
    try:
        bits = int(status)
    except ValueError:
        return "off"
    if bits < 0 or bits & 4:      # removed / unavailable
        return "off"
    if bits & 8 and not bits & 1:  # ringing (not also in use)
        return "ring"
    if bits & 16:                  # on hold (the phone pressed Hold)
        return "hold"
    if bits & (1 | 2):             # in use / busy
        return "busy"
    return "free"


def safe_call(fn, default=None):
    """Run fn(ami) and return (result, error_message)."""
    try:
        with AMI() as ami:
            return fn(ami), None
    except AMIError as exc:
        return default, str(exc)
    except OSError as exc:
        return default, f"AMI hiba: {exc}"
