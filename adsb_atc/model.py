from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

from .utils import now_iso, random_callsign, random_icao


@dataclass
class Flight:
    """Modelo simple de vuelo para la simulación."""

    icao: str = field(default_factory=random_icao)
    callsign: str = field(default_factory=random_callsign)
    lat: float = field(default_factory=lambda: random.uniform(36.0, 60.0))
    lon: float = field(default_factory=lambda: random.uniform(-10.0, 25.0))
    altitude: float = field(default_factory=lambda: random.uniform(3500, 35000))
    speed: float = field(default_factory=lambda: random.uniform(250, 350))
    heading: float = field(default_factory=lambda: random.uniform(0, 360))
    vrate: float = 0.0  # ft/min
    anomaly: Optional[str] = None
    trail: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=60))
    # Derivadas / sensores
    bank_deg: float = 0.0
    turn_rate_dps: float = 0.0
    baro_altitude: float = 0.0
    qnh_hpa: float = field(default_factory=lambda: random.uniform(985.0, 1030.0))
    squawk: str = field(default_factory=lambda: random.choice(["7000", "1200", "2000"]))
    nic: int = field(default_factory=lambda: random.randint(6, 9))
    nacp: int = field(default_factory=lambda: random.randint(8, 10))
    sil: int = field(default_factory=lambda: random.randint(2, 3))
    on_ground: bool = False
    _last_heading: float = field(default=0.0, init=False, repr=False)
    # LNAV/VNAV
    route: List[Tuple[float, float]] = field(default_factory=list)
    wp_index: int = 0
    vnav_target_alt: Optional[float] = None
    # Tipo de aeronave / límites
    ac_type: str = field(default_factory=lambda: random.choice(["A320", "B738", "E190"]))
    max_bank_deg: float = 25.0
    max_turn_rate_dps: float = 3.0
    # Viento y velocidades
    gs_knots: float = 0.0

    def __post_init__(self):
        self._last_heading = self.heading
        self.baro_altitude = self.altitude + (1013.25 - self.qnh_hpa) * 27.0
        self.on_ground = self.altitude < 50 and self.speed < 50
        if self.ac_type in ("A320", "B738"):
            self.max_bank_deg = 25.0
            self.max_turn_rate_dps = 3.0
        elif self.ac_type == "E190":
            self.max_bank_deg = 20.0
            self.max_turn_rate_dps = 2.5

    def step(
        self,
        dt: float = 1.0,
        *,
        wind_dir_deg: Optional[float] = None,
        wind_speed_kt: float = 0.0,
        lnav_bearing: Optional[float] = None,
        vnav_target_alt: Optional[float] = None,
    ):
        """Avanza el estado del vuelo un paso de tiempo 'dt' en segundos."""

        # LNAV
        if lnav_bearing is not None:
            diff = (lnav_bearing - self.heading + 540) % 360 - 180
            max_change = self.max_turn_rate_dps * dt
            change = max(-max_change, min(max_change, diff))
            self.heading = (self.heading + change) % 360
        else:
            self.heading = (self.heading + random.uniform(-1.0, 1.0)) % 360

        # VNAV
        if vnav_target_alt is not None:
            delta = vnav_target_alt - self.altitude
            if abs(delta) > 100:
                target_vrate = 1500.0 * (1 if delta > 0 else -1)
                if abs(delta) < 1000:
                    target_vrate *= abs(delta) / 1000.0
                self.vrate = target_vrate
            else:
                self.vrate = 0.0

        factor = 0.00026  # conversión aproximada nudos -> delta lat/lon

        # TAS vector (knots) según rumbo
        tas_vx = math.cos(math.radians(self.heading)) * self.speed
        tas_vy = math.sin(math.radians(self.heading)) * self.speed

        # Viento a vector (desde donde sopla)
        if wind_dir_deg is not None and wind_speed_kt:
            to_dir = (wind_dir_deg + 180.0) % 360
            wind_vx = math.cos(math.radians(to_dir)) * wind_speed_kt
            wind_vy = math.sin(math.radians(to_dir)) * wind_speed_kt
        else:
            wind_vx = wind_vy = 0.0

        gs_vx = tas_vx + wind_vx
        gs_vy = tas_vy + wind_vy
        self.gs_knots = math.hypot(gs_vx, gs_vy)
        dx = gs_vx * factor * dt
        dy = gs_vy * factor * dt
        self.lat += dy
        self.lon += dx
        self.altitude += (self.vrate / 60.0) * dt  # ft/min -> ft/s

        # Razón de viraje
        old_hdg = self._last_heading
        dh = (self.heading - old_hdg)
        if dh > 180:
            dh -= 360
        elif dh < -180:
            dh += 360
        self.turn_rate_dps = dh / max(1e-6, dt)
        self.turn_rate_dps = max(-self.max_turn_rate_dps, min(self.max_turn_rate_dps, self.turn_rate_dps))

        # Ángulo de alabeo esperado (viraje coordinado)
        v_mps = self.speed * 0.514444
        omega_rad = math.radians(self.turn_rate_dps)
        g = 9.80665
        try:
            self.bank_deg = math.degrees(math.atan2(v_mps * omega_rad, g))
        except Exception:
            self.bank_deg = 0.0

        self.bank_deg = max(-self.max_bank_deg, min(self.max_bank_deg, self.bank_deg))
        self._last_heading = self.heading

        self.baro_altitude = self.altitude + (1013.25 - self.qnh_hpa) * 27.0
        self.on_ground = self.altitude < 50 and self.speed < 50
        self.trail.append((self.lat, self.lon))

    def snapshot(self) -> dict:
        """Devuelve un snapshot con métricas avanzadas típicas ADS-B/aviónica."""
        alt_m = max(0.0, self.altitude * 0.3048)
        T0 = 288.15
        L = 0.0065
        R = 287.052
        gamma = 1.4
        if alt_m <= 11000:
            T = T0 - L * alt_m
        else:
            T = T0 - L * 11000
        a = math.sqrt(gamma * R * T)
        tas_ms = self.speed * 0.514444
        mach = max(0.0, tas_ms / max(1e-6, a))
        rho0 = 1.225
        expo = (9.80665 / (L * R)) - 1.0
        sigma = (T / T0) ** expo
        ias_ms = tas_ms * math.sqrt(max(0.1, sigma))
        ias_knots = ias_ms / 0.514444
        return {
            "timestamp": now_iso(),
            "icao": self.icao,
            "callsign": self.callsign,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "altitude": round(self.altitude, 1),
            "speed_knots": round(self.speed, 1),
            "gs_knots": round(self.gs_knots, 1),
            "heading": round(self.heading, 1),
            "vertical_rate": round(self.vrate, 1),
            "baro_altitude": round(self.baro_altitude, 1),
            "ias_knots": round(ias_knots, 1),
            "mach": round(mach, 3),
            "bank_deg": round(self.bank_deg, 1),
            "turn_rate_dps": round(self.turn_rate_dps, 2),
            "qnh_hpa": round(self.qnh_hpa, 1),
            "nic": self.nic,
            "nacp": self.nacp,
            "sil": self.sil,
            "squawk": self.squawk,
            "on_ground": self.on_ground,
            "anomaly": self.anomaly,
            "source": "simulator",
        }
