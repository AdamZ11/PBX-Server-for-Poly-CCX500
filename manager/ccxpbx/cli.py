"""Command line helper:  python -m ccxpbx.cli <command>

  init [--host IP]          create the database, set server address, print generated secrets
  set-admin-password [PW]   set the web UI admin password (random if omitted, printed)
  apply                     write Asterisk config files and reload Asterisk
  resync-all                send check-sync to every phone
  show-secrets              print provisioning credentials and phone admin password
"""
import argparse
import sys

from . import config, db, httpauth, services


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ccxpbx")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--host", default="")
    p_pw = sub.add_parser("set-admin-password")
    p_pw.add_argument("password", nargs="?")
    sub.add_parser("apply")
    sub.add_parser("resync-all")
    sub.add_parser("show-secrets")
    args = parser.parse_args(argv)

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.PROV_DIR.mkdir(parents=True, exist_ok=True)
    conn = db.connect()
    db.init_db(conn)
    try:
        if args.cmd == "init":
            if args.host:
                db.set_setting(conn, "server_host", args.host)
            if not db.get_settings(conn)["admin_password_hash"]:
                pw = db.gen_secret(14)
                db.set_setting(conn, "admin_password_hash", httpauth.hash_password(pw))
                print(f"ADMIN_PASSWORD={pw}")
            conn.commit()
            _print_secrets(conn)
        elif args.cmd == "set-admin-password":
            pw = args.password or db.gen_secret(14)
            if len(pw) < 10:
                print("Password must be at least 10 characters", file=sys.stderr)
                return 1
            db.set_setting(conn, "admin_password_hash", httpauth.hash_password(pw))
            conn.commit()
            if not args.password:
                print(f"ADMIN_PASSWORD={pw}")
        elif args.cmd == "apply":
            result = services.apply_config(conn)
            conn.commit()
            print(f"changed: {result['changed']} reloaded: {result['reloaded']}")
            if result["error"]:
                print(f"error: {result['error']}", file=sys.stderr)
                return 2
            if result["restart_required"]:
                print("transport changed: restart Asterisk (systemctl restart asterisk)")
        elif args.cmd == "resync-all":
            for row in conn.execute("SELECT mac FROM phones").fetchall():
                err = services.notify_phone(conn, row["mac"])
                print(f"{row['mac']}: {err or 'ok'}")
        elif args.cmd == "show-secrets":
            _print_secrets(conn)
    finally:
        conn.close()
    return 0


def _print_secrets(conn) -> None:
    s = db.get_settings(conn)
    print(f"PROV_USER={s['prov_user']}")
    print(f"PROV_PASSWORD={s['prov_password']}")
    print(f"PHONE_ADMIN_PASSWORD={s['phone_admin_password']}")
    host = s["server_host"] or "<server-ip>"
    print(f"PROV_URL=http://{s['prov_user']}:{s['prov_password']}@{host}/prov")


if __name__ == "__main__":
    sys.exit(main())
