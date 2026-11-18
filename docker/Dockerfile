# CCXPBX in one container: Asterisk 22 LTS + the ccxpbx manager (web UI + phone provisioning).
#
#   docker build -f docker/Dockerfile -t ccxpbx .
#
# Run it with host networking (SIP 5060, RTP 10000-20000, paging multicast) or with its own LAN
# address (macvlan). Everything that must survive an update lives in /data - see docs/TRUENAS.md.

ARG DEBIAN_RELEASE=bookworm

# ------------------------------------------------------------------ 1. build Asterisk
FROM debian:${DEBIAN_RELEASE}-slim AS asterisk
ARG ASTERISK_MAJOR=22
ENV ASTERISK_MAJOR=${ASTERISK_MAJOR}
# the same build script the bare-metal installer uses (downloads, verifies SHA256, builds, installs)
COPY install/build-asterisk.sh /tmp/build-asterisk.sh
RUN bash /tmp/build-asterisk.sh && rm -rf /usr/src/asterisk-*
# list the Debian packages that provide the shared libraries Asterisk and its modules link against
COPY docker/collect-runtime-deps.sh /tmp/collect-runtime-deps.sh
RUN sh /tmp/collect-runtime-deps.sh > /runtime-packages.txt && cat /runtime-packages.txt

# ------------------------------------------------------------------ 2. runtime image
FROM debian:${DEBIAN_RELEASE}-slim
ARG CCXPBX_VERSION=dev
LABEL org.opencontainers.image.title="CCXPBX" \
      org.opencontainers.image.description="Asterisk 22 PBX with Poly CCX500 provisioning and web management" \
      org.opencontainers.image.source="https://github.com/AdamZ11/PBX-Server-for-Poly-CCX500"

COPY --from=asterisk /runtime-packages.txt /tmp/runtime-packages.txt
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends $(cat /tmp/runtime-packages.txt) \
      python3 python3-venv openssl ca-certificates tini iproute2 libcap2-bin sqlite3 procps tzdata >/dev/null \
 && rm -rf /var/lib/apt/lists/* /tmp/runtime-packages.txt

# Asterisk binary, libraries, modules, sounds and the sample configs ("make samples")
COPY --from=asterisk /usr/sbin/asterisk /usr/sbin/asterisk
COPY --from=asterisk /usr/lib/libasterisk* /usr/lib/
COPY --from=asterisk /usr/lib/asterisk/ /usr/lib/asterisk/
COPY --from=asterisk /var/lib/asterisk/ /var/lib/asterisk/
COPY --from=asterisk /var/spool/asterisk/ /usr/share/ccxpbx/spool-skeleton/
COPY --from=asterisk /etc/asterisk/ /etc/asterisk/
RUN ln -sf /usr/sbin/asterisk /usr/sbin/rasterisk && ldconfig \
 && /usr/sbin/asterisk -V \
 && useradd --system --home-dir /var/lib/asterisk --shell /usr/sbin/nologin asterisk \
 && useradd --system --home-dir /data/ccxpbx --shell /usr/sbin/nologin ccxpbx \
 && usermod -aG asterisk ccxpbx \
 && mkdir -p /var/log/asterisk /var/run/asterisk /var/cache/asterisk

# manager
COPY manager/requirements.txt /opt/ccxpbx/manager/requirements.txt
RUN python3 -m venv /opt/ccxpbx/venv \
 && /opt/ccxpbx/venv/bin/pip install -q --no-cache-dir --upgrade pip \
 && /opt/ccxpbx/venv/bin/pip install -q --no-cache-dir -r /opt/ccxpbx/manager/requirements.txt supervisor \
 && setcap cap_net_bind_service=+ep "$(readlink -f /opt/ccxpbx/venv/bin/python)"
COPY manager/ccxpbx /opt/ccxpbx/manager/ccxpbx
COPY asterisk /opt/ccxpbx/asterisk
COPY docker/entrypoint.sh /usr/local/bin/ccxpbx-entrypoint
COPY docker/supervisord.conf /etc/ccxpbx/supervisord.conf
COPY docker/ccxpbx-cli.sh /usr/local/bin/ccxpbx
RUN chmod 0755 /usr/local/bin/ccxpbx-entrypoint /usr/local/bin/ccxpbx \
 && python3 -m compileall -q /opt/ccxpbx/manager/ccxpbx

ENV CCXPBX_DOCKER=1 \
    CCXPBX_VERSION=${CCXPBX_VERSION} \
    CCXPBX_DATA=/data/ccxpbx \
    CCXPBX_AST_DIR=/etc/asterisk/ccxpbx \
    CCXPBX_AMI_HOST=127.0.0.1 \
    CCXPBX_AMI_PORT=5038 \
    CCXPBX_AMI_USER=ccxpbx \
    CCXPBX_HTTP_PORT=80 \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
EXPOSE 80/tcp 5060/udp 5060/tcp 5061/tcp 10000-20000/udp
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD /opt/ccxpbx/venv/bin/python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/login' % os.environ.get('CCXPBX_HTTP_PORT','80'), timeout=4)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/ccxpbx-entrypoint"]
