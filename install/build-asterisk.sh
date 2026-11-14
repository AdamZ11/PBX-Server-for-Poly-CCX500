#!/usr/bin/env bash
# Builds and installs Asterisk (LTS) from source. Works on Debian 12/13 (amd64)
# and Raspberry Pi OS / Debian on arm64 or armhf.
#   ASTERISK_MAJOR=22 ./build-asterisk.sh
set -euo pipefail

ASTERISK_MAJOR="${ASTERISK_MAJOR:-22}"
SRC_DIR="${SRC_DIR:-/usr/src}"
URL_BASE="https://downloads.asterisk.org/pub/telephony/asterisk"
TARBALL="asterisk-${ASTERISK_MAJOR}-current.tar.gz"

log() { echo -e "\033[1;34m[asterisk]\033[0m $*"; }

[[ $EUID -eq 0 ]] || { echo "Run as root"; exit 1; }

log "Installing build dependencies"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
PKGS=(build-essential pkg-config autoconf automake libtool wget curl ca-certificates bzip2 patch
      libedit-dev libjansson-dev libxml2-dev uuid-dev libsqlite3-dev libssl-dev libncurses-dev
      libsrtp2-dev libspeexdsp-dev libspeex-dev libogg-dev libvorbis-dev libopus-dev libcurl4-openssl-dev
      libnewt-dev libpopt-dev libical-dev libgsm1-dev xmlstarlet python3-dev subversion sox)
AVAILABLE=()
for p in "${PKGS[@]}"; do
  if apt-cache show "$p" >/dev/null 2>&1; then AVAILABLE+=("$p"); else log "package $p not available, skipping"; fi
done
apt-get install -y -qq "${AVAILABLE[@]}"

mkdir -p "$SRC_DIR"
cd "$SRC_DIR"
log "Downloading ${TARBALL}"
wget -q -O "$TARBALL" "${URL_BASE}/${TARBALL}"
if wget -q -O "${TARBALL}.sha256" "${URL_BASE}/${TARBALL}.sha256"; then
  expected=$(awk '{print $1}' "${TARBALL}.sha256")
  actual=$(sha256sum "$TARBALL" | awk '{print $1}')
  [[ "$expected" == "$actual" ]] || { echo "SHA256 mismatch for $TARBALL"; exit 1; }
  log "SHA256 verified"
else
  log "WARNING: no .sha256 published, checksum not verified"
fi

DIR=$(tar -tzf "$TARBALL" | head -1 | cut -d/ -f1)
rm -rf "$DIR"
tar -xzf "$TARBALL"
cd "$DIR"
log "Building $DIR"

./configure --with-pjproject-bundled --with-jansson-bundled=no --libdir=/usr/lib >/dev/null
make menuselect.makeopts >/dev/null
menuselect/menuselect \
  --disable BUILD_NATIVE \
  --enable CORE-SOUNDS-EN-WAV --enable CORE-SOUNDS-EN-G722 \
  --enable MOH-OPSOUND-WAV --enable MOH-OPSOUND-G722 \
  --enable EXTRA-SOUNDS-EN-WAV --enable EXTRA-SOUNDS-EN-G722 \
  --disable chan_mgcp --disable chan_skinny --disable chan_unistim \
  menuselect.makeopts

# Keep memory use sane on small Raspberry Pis
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
JOBS=$(nproc)
if (( MEM_MB < 2048 && JOBS > 2 )); then JOBS=2; fi
log "make -j${JOBS} (this takes 10-15 min on a PC, 30-60 min on a Raspberry Pi 4)"
make -j"$JOBS" >/dev/null
make install >/dev/null
if [[ ! -f /etc/asterisk/asterisk.conf ]]; then
  make samples >/dev/null
fi
make install-logrotate >/dev/null || true
ldconfig

log "Installed: $(/usr/sbin/asterisk -V)"
