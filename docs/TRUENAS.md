# CCXPBX telepítése TrueNAS SCALE-re (Docker)

A CCXPBX egyetlen konténerben fut: Asterisk 22 + a webes kezelő (telefon-provisioning, Hívástérkép stb.).
Minden, aminek meg kell maradnia (adatbázis, telefonok, hangposta, felvételek, tanúsítványok, titkos
kulcsok), egyetlen könyvtárban, a konténer `/data` kötetében van – ezt egy TrueNAS datasetre kötjük.

Feltétel: **TrueNAS SCALE 24.10 (Electric Eel) vagy újabb** – ettől kezdve az alkalmazások Dockerrel futnak,
és YAML-lel (Docker Compose) is telepíthetők.

## 1. Melyik hálózati mód?

| | Host hálózat (egyszerűbb) | Saját IP-cím (macvlan) |
|---|---|---|
| A PBX címe | a TrueNAS címe (pl. 192.168.10.116) | külön cím (pl. 192.168.10.120) |
| Webes felület és provisioning | **8080-as port** (a 80/443 a TrueNAS felületé) | 80-as port |
| Provisioning URL a telefonoknak | `http://ccxprov:<jelszó>@192.168.10.116:8080/prov` | `http://ccxprov:<jelszó>@192.168.10.120/prov` |
| Fájl | [docker/truenas-host-network.yaml](../docker/truenas-host-network.yaml) | [docker/truenas-macvlan.yaml](../docker/truenas-macvlan.yaml) |
| Megjegyzés | a TrueNAS-on nem futhat más SIP szolgáltatás (5060, 10000–20000/UDP) | a TrueNAS maga nem éri el a konténer címét (a telefonok és a gépek igen) |

Ha nem tudod eldönteni: **host hálózat**.

## 2. Dataset létrehozása

*Datasets* → válaszd a poolt → *Add Dataset*:

* Név: `ccxpbx` (pl. a `tank/apps` alá → `/mnt/tank/apps/ccxpbx`)
* *Dataset Preset*: **Generic** (vagy *Apps*)

A konténer első induláskor maga hozza létre benne a könyvtárakat és a jogosultságokat.

## 3. Telepítés YAML-lel

1. *Apps* → *Discover Apps* → jobb felül a **⋮** menü → **Install via YAML**.
2. Név: `ccxpbx`.
3. Másold be a választott fájl tartalmát ([host hálózat](../docker/truenas-host-network.yaml) vagy
   [macvlan](../docker/truenas-macvlan.yaml)), és írd át benne:
   * `CCXPBX_HOST` – az a cím, amelyen a telefonok elérik a PBX-et (host módban a TrueNAS címe),
   * a kötet útvonalát (`/mnt/tank/apps/ccxpbx`) a saját datasetedre,
   * macvlan esetén a `parent` hálózati kártyát (*Network* oldalon látod a nevét, pl. `enp3s0` vagy `br0`),
     a `subnet` / `gateway` értéket és a szabad IP-címet (a DHCP tartományon kívülről).
4. *Save*. Az első indulás 1–2 perc (image letöltése, kulcsok és tanúsítványok generálása).

### Első belépés

Az admin jelszót a konténer **első** indulásakor generálja, és kiírja a naplóba:
*Apps* → *ccxpbx* → *Workloads* → a konténer melletti **Logs** ikon. Ilyen sort keress:

```
  ADMIN_PASSWORD=...
  !!! Save the ADMIN_PASSWORD above, it is shown only once.
```

Ugyanitt látod a `PROV_URL`-t is, ezt kell a telefonoknak megadni.

Ha saját jelszót szeretnél, az első telepítés előtt add hozzá az `environment` részhez:
`CCXPBX_ADMIN_PASSWORD: "legalább10karakter"`.

**Elfelejtett jelszó:** add hozzá a `CCXPBX_RESET_ADMIN_PASSWORD: "1"` sort (*Edit*), mentsd, és a naplóban
megjelenik az új jelszó. Utána vedd ki a sort, különben minden újraindításkor új jelszót kapsz.
Vagy a TrueNAS *Shell*-ben:

```bash
sudo docker exec ccxpbx ccxpbx set-admin-password
```

Böngészőben: `http://<CCXPBX_HOST>:8080/` (host mód) vagy `http://<CCXPBX_HOST>/` (macvlan), felhasználó: `admin`.

## 4. Telefonok bekötése

Ugyanúgy, mint a VM-es telepítésnél ([README](../README.md#telefonok-bekötése-zero-touch)), csak a
provisioning URL-ben host módban ott a **:8080** port:

* DHCP opció 160 (vagy 66): a naplóban látott `PROV_URL`.
* Kézzel a telefonon: provisioning szerver `192.168.10.116:8080/prov`, felhasználó/jelszó a `PROV_URL`-ből.

A webes felület *Beállítások* oldalán a *Provisioning HTTP port* mezőt Docker alatt nem kell állítani: a
konténer minden induláskor a `CCXPBX_HTTP_PORT` értékére állítja.

## 5. Frissítés

Az image-et a GitHub automatikusan elkészíti minden módosítás után
(`ghcr.io/adamz11/pbx-server-for-poly-ccx500:latest`). A frissítés új image letöltése; az adatok a datasetben
maradnak.

* Ha az *Apps* oldalon a ccxpbx mellett megjelenik az **Update**, nyomd meg.
* Különben a TrueNAS *Shell*-ben:

  ```bash
  sudo docker pull ghcr.io/adamz11/pbx-server-for-poly-ccx500:latest
  ```

  majd *Apps* → *ccxpbx* → **Stop**, utána **Start** (a konténer az új image-ből indul).

A frissítés alatt kb. fél percig nem lehet telefonálni. A kezelő *Frissítések* oldala Docker alatt a
telepített image verzióját mutatja.

## 6. Mentés és visszaállítás

Minden a datasetben van:

| Útvonal a datasetben | Tartalom |
|---|---|
| `ccxpbx/ccxpbx.db` | mellékek, telefonok, gombok, beállítások |
| `ccxpbx/prov/` | firmware, telefonnaplók, telefonkönyv |
| `ccxpbx/wallpapers/` | feltöltött háttérképek |
| `asterisk/spool/` | hangposta, hívásfelvételek |
| `asterisk/keys/` | saját CA és SIP TLS tanúsítvány |
| `asterisk/db/` | Asterisk belső adatbázis |
| `secrets.env` | AMI jelszó és munkamenet-kulcs |

Mentéshez elég a datasetre **Periodic Snapshot Task**-ot beállítani (*Data Protection*), vagy
replikálni. Visszaállítás: snapshot visszaállítása, majd a ccxpbx *Start*.

Átköltözés VM-ről: a VM-en a `/var/lib/ccxpbx/ccxpbx.db` fájlt másold a dataset `ccxpbx/` könyvtárába
(a konténer leállított állapotában), a `/var/spool/asterisk/voicemail` könyvtárat pedig az
`asterisk/spool/voicemail` alá. Ha a PBX címe változik, a *Beállításokban* állítsd át, és a telefonokat
szinkronizáld.

## 7. Hibakeresés

* **Napló:** *Apps* → *ccxpbx* → *Logs* (Asterisk és a kezelő együtt).
* **Asterisk konzol** a TrueNAS *Shell*-ben:

  ```bash
  sudo docker exec -it ccxpbx asterisk -rvvv
  ```

* **Provisioning adatok újra:** `sudo docker exec ccxpbx ccxpbx show-secrets`
* **A telefon nem regisztrál:** ellenőrizd, hogy a TrueNAS-on nem fut-e más, ami az 5060/UDP portot
  használja, és hogy a telefon a `CCXPBX_HOST` címet kapta-e. `sudo docker exec ccxpbx asterisk -rx "pjsip show contacts"`
* **Egyirányú vagy nincs hang:** a 10000–20000/UDP portoknak elérhetőnek kell lenniük (host vagy macvlan
  módban nincs portleképezés, ez magától működik; tűzfal ne szűrje).
* **Saját build, GitHub nélkül** (a repó a TrueNAS-on, pl. `/mnt/tank/apps/src`):

  ```bash
  sudo docker build -f docker/Dockerfile -t ccxpbx:local .
  ```

  és a YAML-ben `image: ccxpbx:local`. Az Asterisk fordítása 10–20 perc.
* **Privát repó:** ha a GitHub repó privát, az image is privát. Ilyenkor vagy a GitHubon a csomag
  (*Packages* → *pbx-server-for-poly-ccx500* → *Package settings*) láthatóságát állítsd *Public*-ra, vagy a
  TrueNAS-on lépj be egy `read:packages` jogú tokennel: `sudo docker login ghcr.io`.
