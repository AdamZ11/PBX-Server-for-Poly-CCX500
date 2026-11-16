from ccxpbx import callmap

EXTS = [{"num": "2001", "name": "Anna", "state": "busy"}, {"num": "2002", "name": "Béla", "state": "busy"},
        {"num": "2003", "name": "Cili", "state": "free"}, {"num": "2004", "name": "Dani", "state": "off"}]


def ch(chan, uid, linked, state="Up", bridge="", app="", data="", cid="", conn="", exten="", dur="00:00:10"):
    return {"Channel": chan, "Uniqueid": uid, "Linkedid": linked, "ChannelStateDesc": state, "BridgeId": bridge,
            "Application": app, "ApplicationData": data, "CallerIDNum": cid, "ConnectedLineNum": conn,
            "Exten": exten, "Duration": dur}


def edges(m):
    return {(e["from"], e["to"], e["state"]) for e in m["edges"]}


def test_internal_call_and_ring_group():
    chans = [
        ch("PJSIP/2001-0001", "1.1", "1.1", bridge="b1", app="Dial", dur="00:01:05"),
        ch("PJSIP/2002-0002", "1.2", "1.1", bridge="b1", app="AppDial", dur="00:01:00"),
        ch("Local/6000@groups-0001;1", "1.5", "1.1"),            # glue legs are ignored
        # 2003 rings 2001? no: an outside caller rings a ring group with 2003 in it
        ch("PJSIP/prov1-0003", "2.1", "2.1", state="Ring", app="Dial", cid="06301234567"),
        ch("PJSIP/2003-0004", "2.2", "2.1", state="Ringing", app="AppDial", cid="2003", conn="06301234567"),
    ]
    m = callmap.build(chans, EXTS, {"prov1"})
    assert edges(m) == {("ext:2001", "ext:2002", "talk"), ("out:06301234567", "ext:2003", "ring")}
    nodes = {n["id"]: n for n in m["nodes"]}
    assert nodes["ext:2003"]["state"] == "ring"
    assert nodes["out:06301234567"]["kind"] == "out"
    assert m["talking"] == 1 and m["ringing"] == 1
    assert next(e for e in m["edges"] if e["state"] == "talk")["secs"] == 60


def test_services_and_conference():
    chans = [
        ch("PJSIP/2001-0001", "3.1", "3.1", app="ConfBridge", data="800,default_bridge"),
        ch("PJSIP/2002-0002", "4.1", "4.1", app="ConfBridge", data="800,default_bridge"),
        ch("PJSIP/2003-0003", "5.1", "5.1", app="VoiceMailMain", data="2003@default"),
        ch("PJSIP/2004-0004", "6.1", "6.1", state="Ring", app="Dial", exten="0612345"),
    ]
    m = callmap.build(chans, EXTS, set())
    assert ("ext:2001", "svc:conf:800", "talk") in edges(m)
    assert ("ext:2002", "svc:conf:800", "talk") in edges(m)
    assert ("ext:2003", "svc:vm", "talk") in edges(m)
    dial = next(e for e in m["edges"] if e["state"] == "dial")
    assert dial["from"] == "ext:2004" and dial["to"] is None and dial["number"] == "0612345"
    assert {n["label"] for n in m["nodes"] if n["kind"] == "svc"} == {"Konferencia 800", "Hangposta"}


def test_no_channels():
    m = callmap.build([], EXTS, set())
    assert m["edges"] == [] and len(m["nodes"]) == 4
