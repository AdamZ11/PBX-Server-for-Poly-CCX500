#!/usr/bin/env bash
# Container start: prepares /data on the first run, refreshes the Asterisk configuration from the
# image on every start, then hands over to supervisord (Asterisk + the ccxpbx web manager).
#
# Environment:
#   CCXPBX_HOST            IP address the phones use to reach this server (default: detected)
#   CCXPBX_HTTP_PORT       web UI + provisioning port (default 80; use e.g. 8080 next to TrueNAS)
#   CCXPBX_ADMIN_PASSWORD  admin password for the very first start (otherwise one is generated
#                          and printed in the container log)
#   CCXPBX_RESET_ADMIN_PASSWORD=1   print a new admin password at this start (remove it afterwards)
set -euo pipefail

DATA=/data
log() { echo "[ccxpbx] $*"; }

mkdir -p "$DATA/ccxpbx/prov" "$DATA/asterisk/keys" "$DATA/asterisk/spool" "$DATA/asterisk/db"

# ------------------------------------------------------------------ secrets (first start only)
SECRETS="$DATA/secrets.env"
if [[ ! -f "$SECRETS" ]]; then
  log "First start: generating secrets in $SECRETS"
  umask 077
  cat > "$SECRETS" <<EOF
CCXPBX_AMI_SECRET=$(openssl rand -hex 20)
CCXPBX_SECRET_KEY=$(openssl rand -hex 32)
EOF
  umask 022
fi
# shellcheck disable=SC1090
set -a; source "$SECRETS"; set +a
chmod 0600 "$SECRETS"

HOST="${CCXPBX_HOST:-}"
if [[ -z "$HOST" ]]; then
  HOST=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' || true)
  log "CCXPBX_HOST not set, detected address: ${HOST:-unknown}"
fi
export CCXPBX_HTTP_PORT="${CCXPBX_HTTP_PORT:-80}"

# ------------------------------------------------------------------ Asterisk configuration
# Our files over the Asterisk samples, exactly like install.sh does on a VM; refreshed on every
# start so an updated image brings its configuration along.
for f in /opt/ccxpbx/asterisk/*.conf; do
  install -m 0640 "$f" "/etc/asterisk/$(basename "$f")"
done
sed "s/@AMI_SECRET@/${CCXPBX_AMI_SECRET}/" /opt/ccxpbx/asterisk/manager.conf.in > /etc/asterisk/manager.conf
# the Asterisk internal database lives in /data, everything else in /etc/asterisk is rebuilt
sed -i "s#^astdbdir => .*#astdbdir => $DATA/asterisk/db#" /etc/asterisk/asterisk.conf

# TLS keys (own CA, pushed to the phones when SIP TLS is enabled) persist in /data
if [[ ! -L /etc/asterisk/keys ]]; then rm -rf /etc/asterisk/keys; ln -s "$DATA/asterisk/keys" /etc/asterisk/keys; fi
if [[ ! -f "$DATA/asterisk/keys/asterisk.crt" ]]; then
  log "Creating TLS CA and server certificate for ${HOST:-ccxpbx}"
  (
    cd "$DATA/asterisk/keys"
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=ccxpbx CA" -keyout ca.key -out ca.crt 2>/dev/null
    openssl req -newkey rsa:2048 -nodes -subj "/CN=${HOST:-ccxpbx}" -keyout asterisk.key -out asterisk.csr 2>/dev/null
    if [[ -n "$HOST" ]]; then printf "subjectAltName=IP:%s\n" "$HOST" > san.ext; else : > san.ext; fi
    echo "extendedKeyUsage=serverAuth" >> san.ext
    openssl x509 -req -in asterisk.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 3650 \
      -extfile san.ext -out asterisk.crt 2>/dev/null
    rm -f asterisk.csr san.ext
    chmod 0640 ./*; chmod 0644 ca.crt; chmod 0600 ca.key
  )
fi

# voicemail, recordings: /var/spool/asterisk -> /data (seeded with the directory layout once)
if [[ ! -L /var/spool/asterisk ]]; then rm -rf /var/spool/asterisk; ln -s "$DATA/asterisk/spool" /var/spool/asterisk; fi
if [[ -z "$(ls -A "$DATA/asterisk/spool")" ]]; then cp -a /usr/share/ccxpbx/spool-skeleton/. "$DATA/asterisk/spool/"; fi

mkdir -p /etc/asterisk/ccxpbx /var/run/asterisk /var/log/asterisk /var/cache/asterisk
chown -R asterisk:asterisk /etc/asterisk "$DATA/asterisk" /var/lib/asterisk /var/run/asterisk /var/log/asterisk /var/cache/asterisk
chown -R ccxpbx:asterisk /etc/asterisk/ccxpbx
chmod 2770 /etc/asterisk/ccxpbx
chown -R ccxpbx:ccxpbx "$DATA/ccxpbx"
chmod 0750 "$DATA/ccxpbx"

# ------------------------------------------------------------------ manager database
cli() { (cd /opt/ccxpbx/manager && runuser -u ccxpbx -- /opt/ccxpbx/venv/bin/python -m ccxpbx.cli "$@"); }

FIRST_RUN=0
[[ -f "$DATA/ccxpbx/ccxpbx.db" ]] || FIRST_RUN=1
INIT_ARGS=(--http-port "$CCXPBX_HTTP_PORT")
# the stored address is kept unless CCXPBX_HOST is given (or this is the first start)
if [[ $FIRST_RUN -eq 1 || -n "${CCXPBX_HOST:-}" ]]; then INIT_ARGS+=(--host "$HOST"); fi
OUT=$(cli init "${INIT_ARGS[@]}")

if [[ $FIRST_RUN -eq 1 && -n "${CCXPBX_ADMIN_PASSWORD:-}" ]]; then
  cli set-admin-password "$CCXPBX_ADMIN_PASSWORD" >/dev/null
  OUT=$(echo "$OUT" | grep -v '^ADMIN_PASSWORD=' || true)
  log "Admin password set from CCXPBX_ADMIN_PASSWORD."
fi
if [[ "${CCXPBX_RESET_ADMIN_PASSWORD:-0}" == "1" ]]; then
  OUT="$OUT"$'\n'"$(cli set-admin-password)"
  log "CCXPBX_RESET_ADMIN_PASSWORD=1: new admin password below - remove the variable now."
fi

PORT_SUFFIX=$([[ "$CCXPBX_HTTP_PORT" == 80 ]] || echo ":$CCXPBX_HTTP_PORT")
echo "------------------------------------------------------------------"
echo "  CCXPBX ${CCXPBX_VERSION:-}   web UI: http://${HOST:-<server-ip>}${PORT_SUFFIX}/   (user: admin)"
echo "$OUT" | grep -v '^ADMIN_PASSWORD=' | sed 's/^/  /' || true
if echo "$OUT" | grep -q '^ADMIN_PASSWORD='; then
  echo
  echo "  $(echo "$OUT" | grep '^ADMIN_PASSWORD=')"
  echo "  !!! Save the ADMIN_PASSWORD above, it is shown only once."
fi
echo "------------------------------------------------------------------"

cli apply >/dev/null 2>&1 || true   # writes /etc/asterisk/ccxpbx/*.conf before Asterisk starts

exec /opt/ccxpbx/venv/bin/supervisord -c /etc/ccxpbx/supervisord.conf
