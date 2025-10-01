from __future__ import annotations

import random
from typing import Dict, Callable

from .model import Flight


def a_alt_neg(evt: dict, fl: Flight) -> None:
    evt["altitude"] = -abs(evt["altitude"])  # marcar valor negativo
    fl.anomaly = "ALT<0"


def a_speed_impossible(evt: dict, fl: Flight) -> None:
    evt["speed_knots"] = random.uniform(1500, 3000)
    fl.anomaly = "SPD>1500"


def a_dup_icao(evt: dict, fl: Flight, dup_with: str) -> None:
    evt["icao"] = dup_with
    fl.anomaly = "DUP ICAO"


def a_teleport(evt: dict, fl: Flight) -> None:
    evt["lat"] = random.uniform(-60, 80)
    evt["lon"] = random.uniform(-180, 180)
    fl.lat = evt["lat"]
    fl.lon = evt["lon"]
    fl.trail.clear()
    fl.anomaly = "TELEPORT"


ANOMAP: Dict[str, Callable[..., None]] = {
    "alt_neg": a_alt_neg,
    "speed_impossible": a_speed_impossible,
    "dup_icao": a_dup_icao,
    "teleport": a_teleport,
}
