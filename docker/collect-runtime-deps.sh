#!/bin/sh
# Prints the Debian packages that own the shared libraries the installed Asterisk (binary, its own
# libraries and every module) links against, so the runtime image installs exactly those.
set -e
files="/usr/sbin/asterisk $(ls /usr/lib/libasterisk*.so* 2>/dev/null || true) $(find /usr/lib/asterisk/modules -name '*.so')"
for f in $files; do ldd "$f" 2>/dev/null || true; done \
  | awk '$2 == "=>" && $3 ~ /^\// {print $3}' | sort -u \
  | while read -r lib; do
      real=$(readlink -f "$lib")
      for p in "$lib" "$real" "${lib#/usr}" "/usr$lib" "${real#/usr}" "/usr$real"; do
        pkg=$(dpkg -S "$p" 2>/dev/null | head -n1 | cut -d: -f1)
        if [ -n "$pkg" ]; then echo "$pkg"; break; fi
      done
    done \
  | sort -u
