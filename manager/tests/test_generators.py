import xml.etree.ElementTree as ET

import pytest

from ccxpbx import asterisk_gen, plan, poly


def test_site_cfg_is_valid_xml_with_core_params(snap):
    params = poly.site_params(snap)
    assert params["voIpProt.server.1.address"] == "192.168.1.10"
    assert params["voIpProt.server.1.transport"] == "UDPOnly"
    assert params["device.prov.serverName"] == "192.168.1.10/prov"
    assert params["device.auth.localAdminPassword"] == "adm12345"
    assert params["voice.codecPref.G722"] == "1"
    assert params["voice.codecPref.G711_A"] == "2"
    assert params["voice.codecPref.Opus"] == "0"
    assert params["voIpProt.SIP.alertInfo.1.value"] == plan.INTERCOM_ALERT
    assert params["softkey.1.action"] == "#72$Tdtmf$"
    assert params["tcpIpApp.sntp.daylightSavings.start.dayOfWeek.lastInMonth"] == "1"
    assert params["call.offering.led"] == "1"
    snap["settings"]["led_incoming"] = "0"
    assert poly.site_params(snap)["call.offering.led"] == "0"
    snap["settings"]["led_incoming"] = "1"
    root = ET.fromstring(poly.render_cfg(params, "x").encode())
    attrs = {k: v for el in root for k, v in el.attrib.items()}
    assert attrs == params


def test_phone_cfg_lines_and_keys(snap):
    p = poly.phone_params(snap, snap["phones"][0])
    assert p["reg.1.address"] == "2001"
    assert p["reg.1.lineKeys"] == "2"
    assert p["msg.mwi.1.callBack"] == "*97"
    assert p["msg.mwi.1.led"] == "1"
    assert p["lineKey.reassignment.enabled"] == "1"
    assert (p["lineKey.1.category"], p["lineKey.1.index"]) == ("Line", "1")
    assert p["attendant.resourceList.1.address"] == "700"
    assert p["attendant.resourceList.1.type"] == "automata"
    assert p["attendant.resourceList.2.address"] == "2002"
    assert (p["lineKey.3.category"], p["lineKey.3.index"]) == ("BLF", "2")
    assert p["efk.efklist.1.action.string"] == "0612345678$Tinvite$"
    assert p["lineKey.4.category"] == "EFK"
    assert p["lineKey.5.category"] == "Unassigned"
    assert p["up.backlight.idleIntensity"] == "1"
    ET.fromstring(poly.render_cfg(p).encode())


def test_master_and_directory_xml(snap):
    master = ET.fromstring(poly.render_master(snap["settings"], "0004f2aabbcc").encode())
    assert master.attrib["CONFIG_FILES"] == "ccx/0004f2aabbcc-phone.cfg, ccx/site.cfg"
    assert master.attrib["APP_FILE_PATH"] == ""
    unknown = ET.fromstring(poly.render_master(snap["settings"], None).encode())
    assert unknown.attrib["CONFIG_FILES"] == "ccx/site.cfg"
    d = ET.fromstring(poly.render_directory(snap).encode())
    assert [i.findtext("ct") for i in d.iter("item")] == ["2001", "2002"]


def test_digitmap(snap):
    segs = plan.build_digitmap(snap["extensions"], snap["ring_groups"], snap["outbound"]).split("|")
    assert "[23456]xxx" in segs and "*80xxxx" in segs and "**xxxx" in segs
    assert "0x.T" in segs and "112" in segs
    # a phone configured before an extension in another plan range existed can still dial it
    only = plan.build_digitmap([{"ext": "2001"}], [], []).split("|")
    assert "[23456]xxx" in only


def test_asterisk_files(snap):
    files = asterisk_gen.generate(snap)
    ep = files["pjsip_endpoints.conf"]
    assert "[2001]\ntype=endpoint" in ep
    assert "mailboxes=2001@default" in ep
    assert 'callerid="Nagy Béla & x" <2002>' in ep  # cleaned
    assert "max_contacts=2" in ep
    trunks = files["pjsip_trunks.conf"]
    assert r"password=p\;ss" in trunks
    assert "client_uri=sip:user1@sip.example.hu" in trunks
    dp = files["extensions_generated.conf"]
    assert "exten => 2001,hint,PJSIP/2001" in dp
    assert "Gosub(sub-dial-ext,s,1(2002,20,0,1))" in dp
    assert "Dial(Local/2001@ccx-ringtarget&Local/2002@ccx-ringtarget,20,tTkK)" in dp
    assert "VoiceMail(2001@default,u)" in dp
    assert "exten => _0.,1,Gosub(sub-outbound,s,1(prov1,${EXTEN:1},3612345678))" in dp
    assert "exten => 3612345678,1,Goto(from-internal,6000,1)" in dp
    assert "PAGE_ALL=PJSIP/2001\n" in files["globals.conf"]
    vm = files["voicemail_boxes.conf"]
    assert "2001 => 1234,Kiss Anna" in vm and "2002 =>" not in vm


def test_parse_params_rejects_garbage():
    assert plan.parse_params('a.b="x y"\n# c\n') == {"a.b": "x y"}
    with pytest.raises(plan.ValidationError):
        plan.parse_params("bad key=1")
    with pytest.raises(plan.ValidationError):
        plan.parse_params("noequals")
