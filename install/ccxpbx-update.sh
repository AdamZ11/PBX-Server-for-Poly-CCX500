#!/usr/bin/env bash
# ccxpbx update helper (runs as root from systemd, never from the web app itself).
#
#   ccxpbx-update.sh check     fetch the git remote and write the update status
#   ccxpbx-update.sh apply     git pull + re-run install.sh, then check again
#   ccxpbx-update.sh request   run whatever the web UI asked for in $UPDATE_DIR/request
#
# The web UI (user ccxpbx) can only drop the words "check" or "apply" into the request file
# and read status.json / update.log; everything else happens here.
set -uo pipefail

UPDATE_DIR="${CCXPBX_UPDATE_DIR:-/var/lib/ccxpbx/update}"
STATUS="$UPDATE_DIR/status.json"
LOG="$UPDATE_DIR/update.log"
CONF="${CCXPBX_UPDATE_CONF:-/etc/ccxpbx/update.env}"
[[ -f "$CONF" ]] && source "$CONF"
REPO="${CCXPBX_REPO_DIR:-}"

mkdir -p "$UPDATE_DIR"
chown ccxpbx:ccxpbx "$UPDATE_DIR" 2>/dev/null || true

json_str() { python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().rstrip("\n")))'; }

# git as the owner of the checkout, so root never leaves root-owned files in .git
g() {
  if [[ $EUID -ne 0 ]]; then git -C "$REPO" "$@"; return; fi
  local owner
  owner=$(stat -c %U "$REPO")
  runuser -u "$owner" -- git -C "$REPO" "$@"
}

write_status() {   # $1 = state (idle|running|done|failed), $2 = message
  local state="$1" msg="$2" tmp
  tmp=$(mktemp "$UPDATE_DIR/.status.XXXXXX")
  local cur_hash="" cur_date="" cur_subject="" latest="" latest_date="" behind=0 ahead=0 branch="" commits="[]" dirty=0
  if [[ -n "$REPO" && -d "$REPO/.git" ]]; then
    branch=$(g rev-parse --abbrev-ref HEAD 2>/dev/null)
    cur_hash=$(g rev-parse --short HEAD 2>/dev/null)
    cur_date=$(g log -1 --format=%cI HEAD 2>/dev/null)
    cur_subject=$(g log -1 --format=%s HEAD 2>/dev/null)
    if g rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
      latest=$(g rev-parse --short '@{u}')
      latest_date=$(g log -1 --format=%cI '@{u}')
      behind=$(g rev-list --count 'HEAD..@{u}')
      ahead=$(g rev-list --count '@{u}..HEAD')
      commits=$(g log --format='%h%x09%cI%x09%s' -n 30 'HEAD..@{u}' | python3 -c '
import json, sys
print(json.dumps([dict(zip(("hash", "date", "subject"), l.rstrip("\n").split("\t", 2))) for l in sys.stdin if l.strip()]))')
    fi
    [[ -n "$(g status --porcelain --untracked-files=no 2>/dev/null)" ]] && dirty=1
  fi
  cat > "$tmp" <<EOF
{"state": "$state", "message": $(printf '%s' "$msg" | json_str), "checked_at": "$(date -Iseconds)",
 "repo": $(printf '%s' "$REPO" | json_str), "branch": $(printf '%s' "$branch" | json_str),
 "current": {"hash": "$cur_hash", "date": "$cur_date", "subject": $(printf '%s' "$cur_subject" | json_str)},
 "latest": {"hash": "$latest", "date": "$latest_date"},
 "behind": ${behind:-0}, "ahead": ${ahead:-0}, "dirty": $dirty, "commits": $commits}
EOF
  chmod 0644 "$tmp"
  chown ccxpbx:ccxpbx "$tmp" 2>/dev/null || true
  mv -f "$tmp" "$STATUS"
}

do_check() {
  if [[ -z "$REPO" || ! -d "$REPO/.git" ]]; then
    write_status failed "Nem található a telepítéshez használt git könyvtár ($CONF)."
    return 1
  fi
  if g fetch --quiet origin 2>>"$LOG"; then
    write_status idle "OK"
  else
    write_status failed "A GitHub nem érhető el (nincs internet vagy a repó nem elérhető)."
    return 1
  fi
}

do_apply() {
  : > "$LOG"
  chown ccxpbx:ccxpbx "$LOG" 2>/dev/null || true
  chmod 0644 "$LOG"
  write_status running "Frissítés folyamatban"
  (
    echo "== $(date -Iseconds) frissítés indul"
    g fetch origin && g merge --ff-only '@{u}' || { echo "!! git pull nem sikerült (helyi módosítások?)"; exit 1; }
    echo "== telepítő futtatása"
    bash "$REPO/install/install.sh" ${CCXPBX_INSTALL_ARGS:-}
  ) >>"$LOG" 2>&1
  local rc=$?
  if [[ $rc -eq 0 ]]; then
    write_status done "A frissítés sikerült."
  else
    write_status failed "A frissítés nem sikerült, részletek a naplóban."
  fi
  echo "== $(date -Iseconds) vége (kód: $rc)" >>"$LOG"
  return $rc
}

case "${1:-check}" in
  check) do_check ;;
  apply) do_apply ;;
  request)
    req=$(head -c 16 "$UPDATE_DIR/request" 2>/dev/null | tr -cd 'a-z')
    rm -f "$UPDATE_DIR/request"
    case "$req" in
      apply) do_apply ;;
      *) do_check ;;
    esac
    ;;
  *) echo "usage: $0 check|apply|request" >&2; exit 2 ;;
esac
