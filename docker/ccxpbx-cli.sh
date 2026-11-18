#!/usr/bin/env bash
# The ccxpbx command line inside the container, e.g.
#   docker exec ccxpbx ccxpbx show-secrets
#   docker exec ccxpbx ccxpbx set-admin-password
set -euo pipefail
set -a
# shellcheck disable=SC1091
source /data/secrets.env
set +a
cd /opt/ccxpbx/manager
exec runuser -u ccxpbx -- /opt/ccxpbx/venv/bin/python -m ccxpbx.cli "$@"
