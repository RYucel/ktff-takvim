"""Proje ayarları. Sezon değişince KTFF lig adreslerindeki sayı (163, 164...) değişir;
yeni sezonda sadece LEAGUES içindeki `path` değerlerini güncellemek yeterli."""

from pathlib import Path

BASE_URL = "https://ktff.org"
TIMEZONE = "Europe/Nicosia"
MATCH_DURATION_MIN = 110  # 90 dk + devre arası + uzatmalar

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "docs"  # GitHub Pages: main branch /docs

# enabled=False olan ligler taranmaz.
LEAGUES = [
    {"key": "super-lig", "name": "AKSA Süper Lig", "path": "aksa-super-lig-163", "enabled": True},
    {"key": "1-lig", "name": "AKSA 1. Lig", "path": "aksa-1lig-164", "enabled": True},
    {"key": "a2-super-lig", "name": "AKSA A2 Süper Lig", "path": "aksa-a2-super-lig-165", "enabled": False},
    {"key": "a2-1-lig", "name": "AKSA A2 1. Lig", "path": "aksa-a2-1lig-166", "enabled": False},
]

REQUEST_DELAY_S = 0.6  # KTFF sunucusuna nazik davran
MAX_WEEKS = 60
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
