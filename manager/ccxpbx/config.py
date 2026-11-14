"""Runtime configuration, read from environment (see /etc/ccxpbx/ccxpbx.env)."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("CCXPBX_DATA", "/var/lib/ccxpbx"))
DB_PATH = Path(os.environ.get("CCXPBX_DB", str(DATA_DIR / "ccxpbx.db")))
PROV_DIR = Path(os.environ.get("CCXPBX_PROV_DIR", str(DATA_DIR / "prov")))
AST_GEN_DIR = Path(os.environ.get("CCXPBX_AST_DIR", "/etc/asterisk/ccxpbx"))
TLS_CA_CERT = Path(os.environ.get("CCXPBX_TLS_CA", "/etc/asterisk/keys/ca.crt"))
TLS_CERT = os.environ.get("CCXPBX_TLS_CERT", "/etc/asterisk/keys/asterisk.crt")
TLS_KEY = os.environ.get("CCXPBX_TLS_KEY", "/etc/asterisk/keys/asterisk.key")

AMI_HOST = os.environ.get("CCXPBX_AMI_HOST", "127.0.0.1")
AMI_PORT = int(os.environ.get("CCXPBX_AMI_PORT", "5038"))
AMI_USER = os.environ.get("CCXPBX_AMI_USER", "ccxpbx")
AMI_SECRET = os.environ.get("CCXPBX_AMI_SECRET", "")

SECRET_KEY = os.environ.get("CCXPBX_SECRET_KEY", "")

# Directories phones may upload into (relative to PROV_DIR), see master config.
UPLOAD_DIRS = ("logs", "overrides", "contacts", "calllists")
WALLPAPER_DIR = Path(os.environ.get("CCXPBX_WALLPAPER_DIR", str(DATA_DIR / "wallpapers")))   # uploaded
BUNDLED_WALLPAPER_DIR = Path(__file__).parent / "static" / "brand" / "wallpapers"         # brand package
MAX_WALLPAPER = 2 * 1024 * 1024
FIRMWARE_DIR = "firmware"
MAX_UPLOAD = 50 * 1024 * 1024   # core dump archives can be several MB
MAX_LOG_SIZE = 5 * 1024 * 1024
