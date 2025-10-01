from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Tuple, List


def now_iso() -> str:
    """Devuelve la hora actual en UTC en formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def random_icao() -> str:
    """Genera un código ICAO aleatorio de 6 dígitos hexadecimales (24 bits)."""
    return f"{random.getrandbits(24):06X}"


def random_callsign() -> str:
    """Genera un indicativo de vuelo tipo 'XXX1234' usando prefijos comunes."""
    prefixes = [
        "IBE",
        "RYR",
        "AIB",
        "SWR",
        "DAL",
        "BAW",
        "KLM",
        "AFR",
        "SAS",
        "VLG",
        "EZY",
    ]
    return f"{random.choice(prefixes)}{random.randint(100,9999)}"


def bearing_to(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Devuelve el rumbo (deg) de (lat1,lon1) a (lat2,lon2) usando fórmula esférica simple."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    brng = (math.degrees(math.atan2(y, x)) + 360) % 360
    return brng


# Aeropuertos (código, lat, lon)
AIRPORTS: List[Tuple[str, float, float]] = [
    ("MAD", 40.472, -3.561),
    ("BCN", 41.297, 2.078),
    ("CDG", 49.009, 2.55),
    ("LHR", 51.470, -0.454),
    ("FRA", 50.037, 8.562),
    ("AMS", 52.310, 4.768),
    ("PMI", 39.551, 2.738),
    ("AGP", 36.676, -4.499),
    ("SVQ", 37.418, -5.898),
]


# Región de mapa
MAP_LAT_MIN, MAP_LAT_MAX = 30.0, 60.0
MAP_LON_MIN, MAP_LON_MAX = -20.0, 40.0


def geo_to_grid(lat: float, lon: float, rows: int, cols: int) -> Tuple[int, int]:
    """Convierte (lat, lon) a coordenadas (y, x) dentro de una rejilla de tamaño rows x cols."""
    lat = max(MAP_LAT_MIN, min(MAP_LAT_MAX, lat))
    lon = max(MAP_LON_MIN, min(MAP_LON_MAX, lon))
    yf = (MAP_LAT_MAX - lat) / (MAP_LAT_MAX - MAP_LAT_MIN)  # arriba->abajo
    xf = (lon - MAP_LON_MIN) / (MAP_LON_MAX - MAP_LON_MIN)
    y = int(yf * (rows - 2)) + 1
    x = int(xf * (cols - 2)) + 1
    return y, x
