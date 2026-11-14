# PBX Server for Poly CCX500

Asterisk 22 LTS alapú telefonközpont saját provisioning- és eszközkezelő szerverrel, **kizárólag Poly CCX500**
telefonokra optimalizálva (UC Software / PolyOS, OpenSIP – `device.baseProfile=Generic`).
Debian 12/13 virtuális gépen tesztelhető, és ugyanaz a telepítő fut Raspberry Pi OS-en (arm64/armhf).

## Miért Asterisk, és nem FreeSWITCH?

| Szempont | Asterisk 22 LTS | FreeSWITCH |
|---|---|---|
| Raspberry Pi erőforrásigény | kicsi (~60–120 MB RAM) | nagyobb, a forrásból fordítás Pi-n nehézkes |
| Poly/Polycom kompatibilitás | évtizedes, jól dokumentált (BLF dialog-info, MWI, check-sync, Alert-Info intercom) | működik, de kevesebb Poly-specifikus tapasztalat |
| Telepítés Debianon | forrásból, egy szkripttel, minden architektúrán | a hivatalos csomagokhoz SignalWire token kell |
| Támogatás | LTS ág 2029-ig | – |

Egy kis-közepes irodai PBX-hez, ahol egyetlen telefontípus van, az Asterisk egyszerűbb és könnyebb. A Poly-specifikus
tudás (provisioning, gombkiosztás, eszközkezelés) a saját `ccxpbx` kezelőben van, nem a PBX motorban.

## Architektúra

```
 Poly CCX500 ──HTTP(S) GET/PUT──▶ ccxpbx (Python/FastAPI, :80)
      │        /prov/...            ├─ provisioning: dinamikusan generált Poly XML konfig
      │                             ├─ feltöltések: naplók, telefon oldali override-ok, névjegyek, híváslisták
      │                             ├─ webes admin felület (magyar)
      │                             ├─ Poly REST API kliens (eszközinfó, újraindítás, click-to-dial)
      │                             └─ SQLite adatbázis
      │                                   │ generált fájlok: /etc/asterisk/ccxpbx/*.conf
      │                                   │ AMI (127.0.0.1:5038): reload, check-sync NOTIFY, állapot
      └──────SIP/RTP──────────────▶ Asterisk 22 (PJSIP)
                                     ├─ mellékek, BLF hintek, hangposta + MWI, park, konferencia
                                     ├─ intercom / hangosbemondás (Alert-Info auto-answer)
                                     └─ SIP trönk(ök), bejövő/kimenő útvonalak
```

## Telepítés

### 1. Debian VM (teszt)

1. Telepíts egy minimális **Debian 12 vagy 13** (amd64) gépet, *bridged* hálózattal, hogy a telefonok elérjék.
   Ajánlott: 2 vCPU, 2 GB RAM, 16 GB lemez. Adj neki fix IP-t (vagy DHCP-foglalást).
2. ```bash
   sudo apt install -y git
   git clone https://github.com/AdamZ11/PBX-Server-for-Poly-CCX500.git
   cd PBX-Server-for-Poly-CCX500
   sudo ./install/install.sh --host 192.168.1.10
   ```
   Az Asterisk forrásból fordul (~10–15 perc). A végén a telepítő kiírja:
   * `ADMIN_PASSWORD` – a webes felület `admin` jelszava (**csak egyszer jelenik meg!**)
   * `PROV_URL` – ezt kell megadni a telefonoknak
   * `PHONE_ADMIN_PASSWORD` – a telefonok admin jelszava (a szerver állítja be rajtuk)
3. Nyisd meg: `http://192.168.1.10/`

Opciók: `--firewall` (nftables szabályok, előbb nézd át: [install/extra/nftables.conf](install/extra/nftables.conf)),
`--fail2ban`, `--skip-asterisk`, `--http-port 8080`.

### 2. Raspberry Pi (éles)

Raspberry Pi 4/5, legalább 2 GB RAM, **Raspberry Pi OS Lite 64-bit** (Bookworm vagy újabb). Ugyanaz a parancs:
```bash
sudo ./install/install.sh --host <pi-ip>
```
Az Asterisk fordítása Pi 4-en 30–60 perc. SD kártya helyett SSD ajánlott. A naplózás alapból kímélő (nincs `full` log).
Költözéskor elég a `/var/lib/ccxpbx/` könyvtárat (adatbázis, feltöltött firmware) és az `/etc/ccxpbx/ccxpbx.env`
fájlt átmásolni, majd a telepítőt lefuttatni.

## Telefonok bekötése (zero-touch)

0. **Adj a szervernek fix IP-t** (DHCP-foglalás a routeren). A telefonok ezt a címet kapják meg SIP és provisioning
   szervernek, és ha a cím később megváltozik, elvesztik a kapcsolatot.
1. **DHCP opció 160** (a Poly ezt nézi először) vagy **66** a routeren/DHCP szerveren, értéke a `PROV_URL`:
   `http://ccxprov:<jelszó>@192.168.1.10/prov`. Példa dnsmasq-hoz: [install/extra/dnsmasq-ccxpbx.conf](install/extra/dnsmasq-ccxpbx.conf).
   Kézzel: a telefonon *Beállítások → Speciális → Adminisztráció → Hálózati konfiguráció → Provisioning szerver*,
   típus HTTP, cím `192.168.1.10/prov`, felhasználó/jelszó a `PROV_URL`-ből.
2. Gyári állapotú CCX500 esetén: ha a telefon Teams/Zoom módban indul, az első induláskor válaszd az
   **OpenSIP / Generic** alapprofilt (vagy a `device.baseProfile=Generic` – ezt a szerver is beállítja).
3. A telefon letölti a konfigurációt, és megjelenik az **Áttekintés → Új, még fel nem vett telefonok** listában.
   Nyomd meg a *Felvétel* gombot, és rendelj hozzá mellékeket. Mentéskor a szerver azonnal frissíti az Asteriskot.
   A még nem regisztrált telefont ezután indítsd újra (táp ki/be), és letölti a vonalait; a már regisztrált
   telefonok a mentéskor automatikusan megkapják a változást (SIP `check-sync`).
4. **A telefon webfelületén ne ments semmit kézzel**: az ottani módosítások felülírják a szervert. Ha egy telefon
   nem veszi át a szerver beállítását, lásd [docs/CCX500.md – Tipikus hibák](docs/CCX500.md#tipikus-hibák).

## Funkciók és használatuk

| Funkció | Hogyan | Telefonon |
|---|---|---|
| Belső hívás | mellékszám (javasolt 2000–5999) | tárcsázás, azonnal hív (digit map) |
| BLF / foglaltságjelzés | Telefon → gombkiosztás → *BLF* | zöld/piros gomb; csörgéskor megnyomva felveszi (`**mellék`) |
| Hívásparkolás | `#72` hívás közben, vagy *Park* gomb (700) | *Park* soft key; a park helyek (701–708) BLF-en látszanak, megnyomva visszaveszi |
| Hangposta + MWI | mellékenként; `*97` saját, `*98` bármely | üzenetjelző lámpa, *Messages* gomb `*97`-et hív |
| Intercom | `*80` + mellék | a hívott automatikusan felveszi kihangosítva |
| Hangosbemondás | `*82` (unicast, minden tag) vagy Poly multicast *Paging* | *Paging* gomb – szerver nélkül, multicast |
| Hívásfelvétel | `*88` csoport, `**mellék` célzott | |
| Hívásrögzítés | `*1` hívás közben, vagy mellékenként „mindig” | *Felvétel* soft key; fájlok: `/var/spool/asterisk/monitor` |
| Konferencia | `800`–`809` szobák; helyi 3 résztvevős konferencia a telefonon | |
| Átkapcsolás | natív Poly transfer (REFER) vagy `##` / `*2` | Transfer gomb |
| Átirányítás, DND | a telefonon (302 redirect-et az Asterisk követi) | Forward / DND |
| Csengetési csoport | 6xxx, egyszerre / sorban, tartalék cél | |
| Telefonkönyv | automatikus a mellékekből (`000000000000-directory.xml`) | Contacts; a telefonon szerkesztve visszatöltődik a szerverre |
| Gyorshívó | gombkiosztás → *Gyorshívó* (EFK) | |
| Kifelé hívás | Trönkök menü: SIP szolgáltató + kimenő minta (pl. `_0.` levág 1) | |
| Titkosítás | Beállítások → SIP transport *TLS + SRTP* (a saját CA-t a szerver kiküldi a telefonra) | |
| Firmware frissítés | Beállítások → firmware feltöltés és kiválasztás | a telefon a következő induláskor frissít |
| Eszközkezelés | Telefon oldal: szinkronizálás, újraindítás (SIP / REST), eszközinfó, hálózat, vonalak, hívásállapot, click-to-dial, feltöltött naplók | |
| Egyedi paraméter | bármely Poly paraméter `kulcs=érték` – telefononként vagy mindenkire | |

Számozási terv: 1xx segélyhívók (112, 104, 105, 107 – vegyél fel nekik kimenő útvonalat), 2000–5999 mellékek,
6xxx csoportok, 700–708 park, 800–809 konferencia. A 1xxx mellékszámok ütköznének a 112-vel, ezért nem javasoltak.

## Arculat

A webes felület a CCXPBX arculati kézikönyvet követi ([docs/arculat](docs/arculat/), PDF, logók, `tokens.css`):
sötét menüsáv, világos munkaterület, egyetlen kiemelőszín (borostyán), Space Grotesk / Inter / JetBrains Mono betűk
(Google Fonts; internet nélkül rendszerbetűvel jelenik meg).

A telefonokon:
* **Háttérkép:** a négy arculati háttérkép (720×1280, sima JPG) közül a *Beállítások → Megjelenés a telefonokon*
  részben választasz, telefononként felülírható, és saját JPG is feltölthető.
* **CCXPBX oldal az *Alkalmazások* menüben:** a telefon böngészője a `http://<szerver>/phone/` oldalt nyitja meg:
  hangposta, telefonkönyv élő állapottal (koppintásra hív), parkolt hívások, hasznos kódok, rendszeradatok. Az oldal a
  telefon IP-címe alapján ismeri fel a készüléket; más gépről csak bejelentkezett admin láthatja előnézetként
  (`/phone/?mac=<mac>`).
* **Arculati színek a telefon menüjében (opcionális):** sötét állapotsor és menük; a telefon a bekapcsoláskor újraindul.

## Könyvtárszerkezet

```
asterisk/          statikus Asterisk konfig (/etc/asterisk), a generált részeket #include-olja
manager/ccxpbx/    provisioning + webes kezelő (FastAPI)
  poly.py          Poly CCX500 konfiggenerátor (site.cfg, <mac>-phone.cfg, master, directory)
  asterisk_gen.py  PJSIP / dialplan / voicemail generátor
  prov.py          /prov/ HTTP szerver (Digest auth, feltöltések)
  web.py           admin felület
  polyrest.py      Poly REST API kliens
  ami.py           Asterisk Manager kliens
install/           telepítő, Asterisk fordítás, systemd unitok, tűzfal/fail2ban/dnsmasq példák
docs/              részletes leírás és hardveres ellenőrzőlista
```

Fejlesztés / tesztek (bármilyen OS-en, Asterisk nélkül):
```bash
cd manager
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

## Fontos tudnivalók

* A Poly paraméterneveket a Poly UC Software adminisztrátori útmutató alapján állítottam össze. Valódi CCX500-on
  még nem teszteltem őket; a [docs/CCX500.md](docs/CCX500.md) ellenőrzőlistáján végig kell menni, mielőtt élesbe kerül.
  Ha egy paraméter nem stimmel az adott firmware-rel, a webes felület *Egyedi Poly paraméterek* mezőjében kód nélkül felülírható.
* A provisioning sima HTTP-n, Digest hitelesítéssel megy (LAN-ra szánva). Interneten keresztül ne tedd elérhetővé.
* A telefonon kézzel tett módosítások (`overrides/<mac>-phone.cfg`) felülírják a szerver beállításait. A telefon
  oldalán lévő *Telefon oldali override-ok törlése* gombbal lehet visszaállni.
