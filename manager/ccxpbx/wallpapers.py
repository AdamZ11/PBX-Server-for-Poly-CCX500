"""Phone background images: the four CCXPBX brand wallpapers plus uploaded ones.

Poly bg.color.bm.1.name takes a URL of a BMP or JPEG; baseline (non-progressive)
JPEG at the CCX500 screen size, 720x1280 portrait, works best.
"""
import re
import struct
from pathlib import Path

from . import config

LABELS = {
    "CCXPBX_hatter_01_kozpont.jpg": "Központ (alapértelmezett)",
    "CCXPBX_hatter_02_kapcsolotabla.jpg": "Kapcsolótábla",
    "CCXPBX_hatter_03_minimal.jpg": "Minimál",
    "CCXPBX_hatter_04_papir.jpg": "Papír (világos)",
}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.jpe?g$", re.I)


class WallpaperError(ValueError):
    pass


def available() -> list[dict]:
    """Brand wallpapers first, then uploaded ones."""
    items = []
    if config.BUNDLED_WALLPAPER_DIR.is_dir():
        for f in sorted(config.BUNDLED_WALLPAPER_DIR.glob("*.jpg")):
            items.append({"file": f.name, "label": LABELS.get(f.name, f.stem), "bundled": True})
    if config.WALLPAPER_DIR.is_dir():
        for f in sorted(config.WALLPAPER_DIR.iterdir()):
            if f.is_file() and NAME_RE.match(f.name) and f.name not in LABELS:
                items.append({"file": f.name, "label": f.stem, "bundled": False})
    return items


def path(name: str) -> Path | None:
    if not NAME_RE.match(name or ""):
        return None
    for d in (config.WALLPAPER_DIR, config.BUNDLED_WALLPAPER_DIR):
        f = d / name
        if f.is_file():
            return f
    return None


def jpeg_info(data: bytes) -> tuple[int, int, bool]:
    """(width, height, progressive) of a JPEG, or WallpaperError."""
    if data[:3] != b"\xff\xd8\xff":
        raise WallpaperError("A fájl nem JPEG kép.")
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height, marker == 0xC2
        i += 2 + length
    raise WallpaperError("Nem sikerült kiolvasni a kép méretét.")


def save_upload(filename: str, data: bytes) -> tuple[str, str | None]:
    """Store an uploaded wallpaper; returns (stored name, warning or None)."""
    name = Path(filename or "").name.replace(" ", "_")
    if not NAME_RE.match(name):
        raise WallpaperError("Csak .jpg képet tölthetsz fel (a fájlnévben betű, szám, pont, kötőjel, aláhúzás).")
    if name in LABELS:
        raise WallpaperError("Ez a név az arculati háttérképeké, nevezd át a fájlt.")
    if len(data) > config.MAX_WALLPAPER:
        raise WallpaperError("A kép legfeljebb 2 MB lehet.")
    width, height, progressive = jpeg_info(data)
    if progressive:
        raise WallpaperError("Ez progresszív JPEG, amit a Poly telefon nem jelenít meg. Mentsd el sima (baseline) JPG-ként.")
    config.WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.WALLPAPER_DIR / f".{name}.part"
    tmp.write_bytes(data)
    tmp.replace(config.WALLPAPER_DIR / name)
    warning = None if (width, height) == (720, 1280) else (
        f"A kép {width}×{height} pixeles. A CCX500 kijelzőjéhez a 720×1280-as álló kép illik a legjobban.")
    return name, warning


def delete(name: str) -> bool:
    if name in LABELS or not NAME_RE.match(name or ""):
        return False
    f = config.WALLPAPER_DIR / name
    if f.is_file():
        f.unlink()
        return True
    return False
