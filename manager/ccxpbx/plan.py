"""Numbering plan, feature codes and input validation shared by all generators."""
import re

PARK_EXT = "700"
PARK_SLOTS = [str(n) for n in range(701, 709)]
CONF_ROOMS = [str(n) for n in range(800, 810)]

# Feature codes (all fixed-length so the phone digit map never becomes ambiguous)
FC_VM_OWN = "*97"
FC_VM_ANY = "*98"
FC_ECHO = "*43"
FC_TIME = "*60"
FC_PAGE_ALL = "*82"
FC_GROUP_PICKUP = "*88"
FC_INTERCOM = "*80"        # + extension
FC_DIRECTED_PICKUP = "**"  # + extension
DTMF_PARK = "#72"          # in-call, Asterisk featuremap parkcall
DTMF_RECORD = "*1"         # in-call, Asterisk featuremap automixmon

RESERVED = set([PARK_EXT, *PARK_SLOTS, *CONF_ROOMS])

INTERCOM_ALERT = "Ring Answer"  # Alert-Info value matched by voIpProt.SIP.alertInfo.1.value

KEY_TYPES = {
    "line": "Vonal (saját mellék)",
    "blf": "BLF / foglaltság",
    "park": "Park gomb (700)",
    "speeddial": "Gyorshívó",
    "unassigned": "Üres",
}
MAX_KEYS = 24   # CCX500 line key slots managed by the UI
MAX_LINES = 4

EXT_RE = re.compile(r"^[1-9][0-9]{1,5}$")
MAC_RE = re.compile(r"^[0-9a-f]{12}$")
DIAL_RE = re.compile(r"^[0-9*#+]{1,32}$")
TRUNK_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
PATTERN_RE = re.compile(r"^_?[0-9XNZxnz\[\]\-.!+*#]{1,40}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.\-:\[\]]{1,253}$")
PARAM_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,127}$")


class ValidationError(ValueError):
    pass


def normalize_mac(value: str) -> str:
    mac = re.sub(r"[^0-9a-fA-F]", "", value or "").lower()
    if not MAC_RE.match(mac) or mac == "000000000000":
        raise ValidationError(f"Érvénytelen MAC cím: {value!r}")
    return mac


def check_ext(value: str) -> str:
    value = (value or "").strip()
    if not EXT_RE.match(value):
        raise ValidationError(f"Érvénytelen hívószám: {value!r} (2-6 számjegy, nem kezdődhet 0-val)")
    if value in RESERVED:
        raise ValidationError(f"A {value} foglalt szám (park/konferencia)")
    return value


def clean_text(value: str, max_len: int = 64) -> str:
    """Strip characters that would break Asterisk .conf files or XML."""
    value = re.sub(r"[\r\n\t;\"<>\\]", " ", value or "")
    value = re.sub(r" {2,}", " ", value).strip()
    return value[:max_len]


def parse_params(text: str) -> dict:
    """Parse `key=value` lines (Poly parameters) - '#' starts a comment."""
    params = {}
    for lineno, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValidationError(f"{lineno}. sor: hiányzó '=' ({line!r})")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        if not PARAM_RE.match(key):
            raise ValidationError(f"{lineno}. sor: érvénytelen paraméternév ({key!r})")
        params[key] = value
    return params


def ast_pattern_to_digitmap(pattern: str) -> str:
    """Convert an Asterisk extension pattern to a Poly digit map segment."""
    if not pattern.startswith("_"):
        return pattern
    out = []
    for ch in pattern[1:]:
        if ch in "Xx":
            out.append("x")
        elif ch in "Nn":
            out.append("[2-9]")
        elif ch in "Zz":
            out.append("[1-9]")
        elif ch in ".!":
            out.append("x.T")
            break
        else:
            out.append(ch)
    return "".join(out)


def build_digitmap(extensions, ring_groups, outbound) -> str:
    """Poly digit map that dials instantly for internal numbers, with a timeout for external ones."""
    segments = []
    internal = sorted({e["ext"] for e in extensions} | {g["num"] for g in ring_groups})
    by_len: dict[int, set] = {}
    for num in internal:
        by_len.setdefault(len(num), set()).add(num[0])
    for length, firsts in sorted(by_len.items()):
        first = "".join(sorted(firsts))
        head = first if len(first) == 1 else f"[{first}]"
        segments.append(head + "x" * (length - 1))
    segments += ["70x", "80x"]
    segments += [FC_VM_OWN, FC_VM_ANY, FC_ECHO, FC_TIME, FC_PAGE_ALL, FC_GROUP_PICKUP]
    for length in sorted(by_len):
        segments.append(FC_INTERCOM + "x" * length)
        segments.append(FC_DIRECTED_PICKUP + "x" * length)
    for route in outbound:
        seg = ast_pattern_to_digitmap(route["pattern"])
        if seg not in segments:
            segments.append(seg)
    return "|".join(segments)
