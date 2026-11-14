#!/usr/bin/env bash
# ccxpbx installer - Asterisk 22 LTS + Poly CCX500 provisioning / management server
#
# Debian 12/13 (VM, amd64) and Raspberry Pi OS (Bookworm or newer, arm64/armhf).
#
#   sudo ./install/install.sh [--host 192.168.1.10] [--skip-asterisk] [--firewall] [--fail2ban]
#
# Safe to re-run (upgrades the manager, keeps database and secrets).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST=""
SKIP_ASTERISK=0
FIREWALL=0
FAIL2BAN=0
HTTP_PORT=80

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --skip-asterisk) SKIP_ASTERISK=1; shift ;;
    --firewall) FIREWALL=1; shift ;;
    --fail2ban) FAIL2BAN=1; shift ;;
    --http-port) HTTP_PORT="$2"; shift 2 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

log() { echo -e "\033[1;32m[ccxpbx]\033[0m $*"; }
[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)"; exit 1; }
grep -qiE 'debian|raspbian' /etc/os-release || log "WARNING: not a Debian based system, continuing anyway"

if [[ -z "$HOST" ]]; then
  HOST=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')
fi
log "Server address: ${HOST:-unknown} (change later in the web UI -> Beállítások)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip openssl ca-certificates sqlite3 chrony

# ------------------------------------------------------------------ Asterisk
if [[ $SKIP_ASTERISK -eq 0 ]]; then
  if command -v asterisk >/dev/null && asterisk -V | grep -q "Asterisk 22"; then
    log "Asterisk 22 already installed: $(asterisk -V)"
  else
    bash "$REPO_DIR/install/build-asterisk.sh"
  fi
fi

id asterisk >/dev/null 2>&1 || useradd --system --home-dir /var/lib/asterisk --shell /usr/sbin/nologin asterisk
id ccxpbx >/dev/null 2>&1 || useradd --system --home-dir /var/lib/ccxpbx --shell /usr/sbin/nologin ccxpbx
usermod -aG asterisk ccxpbx

# ------------------------------------------------------------------ Asterisk config
if [[ ! -f /etc/asterisk/.ccxpbx ]]; then
  if [[ -d /etc/asterisk ]]; then
    BACKUP="/etc/asterisk.orig-$(date +%Y%m%d%H%M%S)"
    log "Backing up existing /etc/asterisk to $BACKUP"
    cp -a /etc/asterisk "$BACKUP"
  fi
  mkdir -p /etc/asterisk
  touch /etc/asterisk/.ccxpbx
fi

mkdir -p /etc/ccxpbx
ENV_FILE=/etc/ccxpbx/ccxpbx.env
if [[ ! -f "$ENV_FILE" ]]; then
  AMI_SECRET=$(openssl rand -hex 20)
  SECRET_KEY=$(openssl rand -hex 32)
  cat > "$ENV_FILE" <<EOF
CCXPBX_DATA=/var/lib/ccxpbx
CCXPBX_AST_DIR=/etc/asterisk/ccxpbx
CCXPBX_AMI_HOST=127.0.0.1
CCXPBX_AMI_PORT=5038
CCXPBX_AMI_USER=ccxpbx
CCXPBX_AMI_SECRET=${AMI_SECRET}
CCXPBX_SECRET_KEY=${SECRET_KEY}
CCXPBX_HTTP_PORT=${HTTP_PORT}
EOF
fi
chown root:ccxpbx "$ENV_FILE"
chmod 0640 "$ENV_FILE"
# shellcheck disable=SC1090
source "$ENV_FILE"

for f in "$REPO_DIR"/asterisk/*.conf; do
  install -m 0640 -o asterisk -g asterisk "$f" "/etc/asterisk/$(basename "$f")"
done
sed "s/@AMI_SECRET@/${CCXPBX_AMI_SECRET}/" "$REPO_DIR/asterisk/manager.conf.in" > /etc/asterisk/manager.conf
chown asterisk:asterisk /etc/asterisk/manager.conf
chmod 0640 /etc/asterisk/manager.conf
if [[ ! -f /etc/asterisk/indications.conf ]] && [[ -d /usr/src ]]; then
  sample=$(find /usr/src -path '*configs/samples/indications.conf.sample' 2>/dev/null | head -1 || true)
  [[ -n "$sample" ]] && install -m 0640 -o asterisk -g asterisk "$sample" /etc/asterisk/indications.conf
fi

install -d -m 2750 -o ccxpbx -g asterisk /etc/asterisk/ccxpbx

# TLS: own CA + server certificate (CA is pushed to the phones when SIP TLS is enabled)
install -d -m 0750 -o asterisk -g asterisk /etc/asterisk/keys
if [[ ! -f /etc/asterisk/keys/asterisk.crt ]]; then
  log "Creating TLS CA and server certificate"
  pushd /etc/asterisk/keys >/dev/null
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=ccxpbx CA" -keyout ca.key -out ca.crt 2>/dev/null
  openssl req -newkey rsa:2048 -nodes -subj "/CN=${HOST}" -keyout asterisk.key -out asterisk.csr 2>/dev/null
  printf "subjectAltName=IP:%s\nextendedKeyUsage=serverAuth\n" "$HOST" > san.ext
  openssl x509 -req -in asterisk.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 3650 \
    -extfile san.ext -out asterisk.crt 2>/dev/null
  rm -f asterisk.csr san.ext
  chown asterisk:asterisk ./*
  chmod 0640 ./*
  chmod 0644 ca.crt
  chmod 0600 ca.key
  popd >/dev/null
fi

for d in /var/lib/asterisk /var/log/asterisk /var/spool/asterisk /var/cache/asterisk; do
  mkdir -p "$d"
  chown -R asterisk:asterisk "$d"
done
chown -R asterisk:asterisk /etc/asterisk
chown -R ccxpbx:asterisk /etc/asterisk/ccxpbx
chmod 2750 /etc/asterisk/ccxpbx

# ------------------------------------------------------------------ manager
log "Installing ccxpbx manager to /opt/ccxpbx"
mkdir -p /opt/ccxpbx
rm -rf /opt/ccxpbx/manager
cp -a "$REPO_DIR/manager" /opt/ccxpbx/manager
rm -rf /opt/ccxpbx/manager/tests
[[ -d /opt/ccxpbx/venv ]] || python3 -m venv /opt/ccxpbx/venv
/opt/ccxpbx/venv/bin/pip install -q --upgrade pip
/opt/ccxpbx/venv/bin/pip install -q -r /opt/ccxpbx/manager/requirements.txt
chown -R root:root /opt/ccxpbx
install -d -m 0750 -o ccxpbx -g ccxpbx /var/lib/ccxpbx /var/lib/ccxpbx/prov

run_cli() {
  (cd /opt/ccxpbx/manager && runuser -u ccxpbx -- env $(grep -v '^#' "$ENV_FILE" | xargs) \
    /opt/ccxpbx/venv/bin/python -m ccxpbx.cli "$@")
}
FIRST_RUN=0
[[ -f /var/lib/ccxpbx/ccxpbx.db ]] || FIRST_RUN=1
SECRETS=$(run_cli init --host "$HOST")
run_cli apply >/dev/null 2>&1 || true   # writes /etc/asterisk/ccxpbx/*.conf (Asterisk may not run yet)

install -m 0644 "$REPO_DIR/install/systemd/asterisk.service" /etc/systemd/system/asterisk.service
install -m 0644 "$REPO_DIR/install/systemd/ccxpbx.service" /etc/systemd/system/ccxpbx.service
# the init script installed by "make config" would conflict with our unit
[[ -f /etc/init.d/asterisk ]] && update-rc.d -f asterisk remove >/dev/null 2>&1 || true
systemctl daemon-reload
systemctl enable --now asterisk >/dev/null
systemctl enable ccxpbx >/dev/null
systemctl restart ccxpbx

# ------------------------------------------------------------------ optional hardening
if [[ $FIREWALL -eq 1 ]]; then
  log "Installing nftables firewall"
  apt-get install -y -qq nftables
  install -m 0644 "$REPO_DIR/install/extra/nftables.conf" /etc/nftables.conf
  systemctl enable --now nftables >/dev/null
  nft -f /etc/nftables.conf
fi
if [[ $FAIL2BAN -eq 1 ]]; then
  log "Installing fail2ban jail for Asterisk"
  apt-get install -y -qq fail2ban
  install -m 0644 "$REPO_DIR/install/extra/fail2ban-asterisk.conf" /etc/fail2ban/jail.d/asterisk.conf
  systemctl restart fail2ban
fi

sleep 2
log "Done."
echo
echo "  Web UI:            http://${HOST}$( [[ $HTTP_PORT == 80 ]] || echo ":$HTTP_PORT" )/   (user: admin)"
if [[ $FIRST_RUN -eq 1 ]]; then
  echo "$SECRETS" | sed 's/^/  /'
  echo
  echo "  !!! Save the ADMIN_PASSWORD above, it is shown only once."
else
  echo "$SECRETS" | grep -v ADMIN_PASSWORD | sed 's/^/  /'
fi
echo
echo "  Point the phones to PROV_URL via DHCP option 160 / 66, or set it manually on the phone"
echo "  (Settings > Advanced > Administration > Network Configuration > Provisioning Server)."
echo "  Status: systemctl status asterisk ccxpbx    CLI: asterisk -rvvv"
