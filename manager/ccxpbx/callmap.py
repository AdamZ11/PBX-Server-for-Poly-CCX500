"""Live call map: who is talking to whom, built from Asterisk's CoreShowChannels list.

Every extension is a node; a call adds an edge between the parties. Calls that reach the outside world
get a node for the remote number, calls into voicemail, a conference room, the parking lot etc. get a
node for that service. Channels of one call share a Linkedid; the channel whose Uniqueid equals the
Linkedid is the one that started the call.
"""
import re

_CHAN_RE = re.compile(r"^(?:PJSIP|SIP|IAX2)/(.+)-[0-9a-f]+$", re.I)

# Application of a lone channel -> (node id prefix, label)
SERVICES = {
    "voicemail": ("vm", "Hangposta"),
    "voicemailmain": ("vm", "Hangposta"),
    "confbridge": ("conf", "Konferencia"),
    "park": ("park", "Parkoló"),
    "parkandannounce": ("park", "Parkoló"),
    "parkedcall": ("park", "Parkoló"),
    "echo": ("echo", "Visszhang teszt"),
    "page": ("page", "Hangosbemondás"),
    "sayunixtime": ("time", "Pontos idő"),
    "queue": ("queue", "Várakozási sor"),
    "playback": ("play", "Bemondás"),
    "background": ("play", "Bemondás"),
}


def _endpoint(channel: str) -> str:
    m = _CHAN_RE.match(channel or "")
    return m.group(1) if m else ""


def _seconds(duration: str) -> int:
    try:
        parts = [int(x) for x in str(duration or "0").split(":")]
    except ValueError:
        return 0
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


def build(channels: list[dict], extensions: list[dict], trunks: set[str], groups: list[dict] | None = None) -> dict:
    """channels: raw CoreShowChannel events; extensions: [{num, name, state}] (state from the hints,
    'hold' when the phone put its call on hold); groups: ring groups [{num, name, members}]."""
    ext_nums = {e["num"] for e in extensions}
    nodes = {f"ext:{e['num']}": {"id": f"ext:{e['num']}", "kind": "ext", "label": e["num"], "sub": e["name"],
                                  "state": e["state"]} for e in extensions}
    calls: dict[str, list[dict]] = {}
    for ch in channels or []:
        ep = _endpoint(ch.get("Channel", ""))
        if not ep:
            continue   # Local/ channels and the like only glue the real legs together
        calls.setdefault(ch.get("Linkedid") or ch.get("Uniqueid") or ch.get("Channel"), []).append(dict(ch, _ep=ep))

    def party(ch: dict) -> str:
        """Node id for the party behind one channel (created on demand)."""
        ep = ch["_ep"]
        if ep in ext_nums:
            return f"ext:{ep}"
        if ep in trunks:
            cands = [ch.get("CallerIDNum", ""), ch.get("ConnectedLineNum", ""), ch.get("Exten", "")]
            num = next((n for n in cands if n and n not in ext_nums and n not in ("<unknown>", "s")), "") or "ismeretlen"
            name = next((n for n in (ch.get("CallerIDName", ""), ch.get("ConnectedLineName", ""))
                         if n and n not in ("<unknown>",) and n != num and not n.isdigit()), "")
            nid = f"out:{num}"
            nodes.setdefault(nid, {"id": nid, "kind": "out", "label": num, "sub": name or f"külső · {ep}",
                                   "state": "busy"})
            return nid
        nid = f"dev:{ep}"   # an endpoint we do not manage (old phone, softphone)
        nodes.setdefault(nid, {"id": nid, "kind": "out", "label": ep, "sub": "egyéb végpont", "state": "busy"})
        return nid

    def service(ch: dict) -> str | None:
        app = (ch.get("Application") or "").lower()
        if app not in SERVICES:
            return None
        prefix, label = SERVICES[app]
        data = (ch.get("ApplicationData") or "").split(",")[0].split("@")[0]
        key = data if prefix in ("conf", "queue") and data else ""
        nid = f"svc:{prefix}{':' + key if key else ''}"
        nodes.setdefault(nid, {"id": nid, "kind": "svc", "label": f"{label} {key}".strip(), "sub": "", "state": "busy"})
        return nid

    edges = []
    for linked, legs in calls.items():
        origin = next((c for c in legs if c.get("Uniqueid") == linked), legs[0])
        src = party(origin)
        others = [c for c in legs if c is not origin]
        secs = max(_seconds(c.get("Duration")) for c in legs)
        names = [c.get("Channel", "") for c in legs]
        if not others:
            dst = service(origin)
            if dst:
                edges.append({"from": src, "to": dst, "state": "talk", "secs": secs, "channels": names})
            elif (origin.get("ChannelStateDesc") or "").lower() != "up":
                edges.append({"from": src, "to": None, "state": "dial", "secs": secs,
                              "number": origin.get("Exten", ""), "channels": names})
            continue
        for c in others:
            dst = party(c)
            if dst == src:
                continue
            state_desc = (c.get("ChannelStateDesc") or "").lower()
            bridged = c.get("BridgeId") and c.get("BridgeId") == origin.get("BridgeId")
            state = "talk" if bridged or (state_desc == "up" and (origin.get("ChannelStateDesc") or "").lower() == "up") \
                else "ring"
            if state == "talk" and any(nodes.get(n, {}).get("state") == "hold" for n in (src, dst)):
                state = "hold"
            edges.append({"from": src, "to": dst, "state": state, "secs": _seconds(c.get("Duration")) or secs,
                          "channels": [origin.get("Channel", ""), c.get("Channel", "")]})
    # a ring group rings several phones; once one answers the others drop, so no special casing is needed
    for e in edges:
        for end in (e["from"], e["to"]):
            n = nodes.get(end)
            if n and n["kind"] == "ext" and n["state"] in ("free", "off") and e["state"] != "hold":
                n["state"] = "ring" if e["state"] == "ring" and end == e["to"] else "busy"
    group_list = [{"num": g["num"], "name": g["name"],
                   "members": [m for m in (g.get("members") or "").split(",") if m in ext_nums]} for g in groups or []]
    return {"nodes": list(nodes.values()), "edges": edges, "groups": group_list,
            "talking": sum(e["state"] == "talk" for e in edges),
            "holding": sum(e["state"] == "hold" for e in edges),
            "ringing": sum(e["state"] == "ring" for e in edges)}
