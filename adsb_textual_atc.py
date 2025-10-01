#!/usr/bin/env python3
"""
ADS-B ATC Textual TUI
=====================
- Mapa ATC con gradiente temático, glifos enriquecidos y estelas suavizadas.
- Panel lateral con tabla de vuelos (ICAO, CALL, FL, GS, IAS, VS, MACH...).
- Detección visual de anomalías con colores de severidad y leyenda actualizada.
- Exportación a JSONL + plantilla de ingesta para futura conexión Elastic Stack.
Controles:
  q         → salir
  p         → pausar/reanudar simulación
  t         → alternar estelas ON/OFF
  a         → alternar inserción de anomalías ON/OFF
  + / -     → subir/bajar eventos por tick (ritmo)
  h / ?     → ayuda
Ejemplos:
  python3 adsb_textual_atc.py -o adsb_stream.jsonl -n 25 -r 10 -d 300 -A alt_neg,speed_impossible,dup_icao,teleport
  python3 adsb_textual_atc.py -o out.jsonl --elastic-endpoint https://elastic.local:9200 --elastic-index sim-adsb
"""
from __future__ import annotations
import argparse
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Deque, Protocol, Sequence
from collections import deque
from rich.panel import Panel
from rich.align import Align
from rich.text import Text
from rich.box import ROUNDED
from rich.console import Group
from rich.style import Style
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Header, Footer, Static, DataTable
from textual.reactive import reactive
from textual.events import Key
# ---------------------- Helpers & Model ----------------------
def now_iso() -> str:
    """Devuelve la hora actual en UTC en formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat()
def random_icao() -> str:
    """Genera un código ICAO aleatorio de 6 dígitos hexadecimales (24 bits)."""
    return f"{random.getrandbits(24):06X}"
def random_callsign() -> str:
    """Genera un indicativo de vuelo tipo 'XXX1234' usando prefijos comunes."""
    prefixes = ["IBE", "RYR", "AIB", "SWR", "DAL", "BAW", "KLM", "AFR", "SAS", "VLG", "EZY"]
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
@dataclass
class Flight:
    """Modelo simple de vuelo para la simulación."""
    icao: str = field(default_factory=random_icao)
    callsign: str = field(default_factory=random_callsign)
    lat: float = field(default_factory=lambda: random.uniform(36.0, 60.0))
    lon: float = field(default_factory=lambda: random.uniform(-10.0, 25.0))
    """Generar altitudes de vuelo randoms entre un intervalo de 3500 a 35000 ft"""
    altitude: float = field(default_factory=lambda: random.uniform(3500, 35000))
    """Generar velocidades de vuelo randoms entre 250 y 350 nudos"""
    speed: float = field(default_factory=lambda: random.uniform(250, 350))
    heading: float = field(default_factory=lambda: random.uniform(0, 360))
    vrate: float = 0.0         # ft/min
    anomaly: Optional[str] = None
    trail: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=60))
    # Derivadas / sensores
    bank_deg: float = 0.0               # ángulo de alabeo estimado
    turn_rate_dps: float = 0.0          # razón de viraje (deg/s)
    baro_altitude: float = 0.0          # altitud barométrica (ft)
    qnh_hpa: float = field(default_factory=lambda: random.uniform(985.0, 1030.0))
    squawk: str = field(default_factory=lambda: random.choice(["7000", "1200", "2000"]))
    nic: int = field(default_factory=lambda: random.randint(6, 9))   # Navigation Integrity Category
    nacp: int = field(default_factory=lambda: random.randint(8, 10)) # Navigation Accuracy Category for Position
    sil: int = field(default_factory=lambda: random.randint(2, 3))   # Source Integrity Level
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
        # Inicializa baro con offset por QNH (~27 ft por hPa desde 1013)
        self.baro_altitude = self.altitude + (1013.25 - self.qnh_hpa) * 27.0
        self.on_ground = self.altitude < 50 and self.speed < 50
        # Límites por tipo
        if self.ac_type in ("A320", "B738"):
            self.max_bank_deg = 25.0
            self.max_turn_rate_dps = 3.0
        elif self.ac_type == "E190":
            self.max_bank_deg = 20.0
            self.max_turn_rate_dps = 2.5
    def step(self, dt: float = 1.0, *, wind_dir_deg: Optional[float] = None, wind_speed_kt: float = 0.0,
             lnav_bearing: Optional[float] = None, vnav_target_alt: Optional[float] = None):
        """Avanza el estado del vuelo un paso de tiempo 'dt' en segundos."""
        # Movimiento aproximado (suficiente para visualización)
        # LNAV: orientar rumbo hacia bearing objetivo respetando limitación de turn rate
        if lnav_bearing is not None:
            diff = (lnav_bearing - self.heading + 540) % 360 - 180
            max_change = self.max_turn_rate_dps * dt
            change = max(-max_change, min(max_change, diff))
            self.heading = (self.heading + change) % 360
        else:
            # Pequeña deriva si no hay LNAV
            self.heading = (self.heading + random.uniform(-1.0, 1.0)) % 360
        # VNAV: ajustar vrate hacia objetivo
        if vnav_target_alt is not None:
            delta = vnav_target_alt - self.altitude
            if abs(delta) > 100:
                target_vrate = 1500.0 * (1 if delta > 0 else -1)
                # reduce al acercarse para no pasarse
                if abs(delta) < 1000:
                    target_vrate *= abs(delta) / 1000.0
                self.vrate = target_vrate
            else:
                self.vrate = 0.0
        factor = 0.00026  # conversión aproximada nudos -> delta lat/lon
        # TAS vector (knots) según rumbo
        tas_vx = math.cos(math.radians(self.heading)) * self.speed
        tas_vy = math.sin(math.radians(self.heading)) * self.speed
        # Viento a vector (desde donde sopla): convertir a hacia donde va
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
        # Calcula razón de viraje (deg/s) considerando wrap-around
        old_hdg = self._last_heading
        dh = (self.heading - old_hdg)
        if dh > 180:
            dh -= 360
        elif dh < -180:
            dh += 360
        self.turn_rate_dps = dh / max(1e-6, dt)
        # Limita turn rate a máximos de la aeronave
        self.turn_rate_dps = max(-self.max_turn_rate_dps, min(self.max_turn_rate_dps, self.turn_rate_dps))
        # Ángulo de alabeo esperado en viraje coordinado: tan(phi)=v*omega/g (limitado)
        v_mps = self.speed * 0.514444
        omega_rad = math.radians(self.turn_rate_dps)
        g = 9.80665
        try:
            self.bank_deg = math.degrees(math.atan2(v_mps * omega_rad, g))
        except Exception:
            self.bank_deg = 0.0
        # Limitar bank
        if self.bank_deg > self.max_bank_deg:
            self.bank_deg = self.max_bank_deg
        if self.bank_deg < -self.max_bank_deg:
            self.bank_deg = -self.max_bank_deg
        self._last_heading = self.heading
        # Actualiza baro y on_ground
        self.baro_altitude = self.altitude + (1013.25 - self.qnh_hpa) * 27.0
        self.on_ground = self.altitude < 50 and self.speed < 50
        # Guarda estela (posición histórica)
        self.trail.append((self.lat, self.lon))
    def snapshot(self) -> dict:
        """Devuelve un snapshot con métricas avanzadas típicas ADS-B/aviónica."""
        # ISA simplificada para Mach e IAS aproximados
        alt_m = max(0.0, self.altitude * 0.3048)
        T0 = 288.15
        L = 0.0065
        R = 287.052
        gamma = 1.4
        if alt_m <= 11000:
            T = T0 - L * alt_m
        else:
            T = T0 - L * 11000  # tropopausa constante
        a = math.sqrt(gamma * R * T)  # velocidad del sonido (m/s)
        tas_ms = self.speed * 0.514444
        mach = max(0.0, tas_ms / max(1e-6, a))
        # Densidad relativa aproximada (troposfera)
        rho0 = 1.225
        # p ~ (T/T0)^(g/(L*R)), rho ~ p/T => ~ (T/T0)^(g/(L*R)-1)
        expo = (9.80665 / (L * R)) - 1.0  # ~ 4.2559
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
            "speed_knots": round(self.speed, 1),  # TAS aprox
            "gs_knots": round(self.gs_knots, 1),   # GS con viento
            "heading": round(self.heading, 1),
            "vertical_rate": round(self.vrate, 1),
            # Métricas adicionales
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
            "source": "simulator"
        }
# ---------------------- Exporters ----------------------
class EventExporter(Protocol):
    """Contrato mínimo para componentes que consumen eventos de la simulación."""
    def emit(self, event: dict) -> None:  # pragma: no cover - interfaz
        ...
    def close(self) -> None:  # pragma: no cover - interfaz
        ...
@dataclass
class ElasticConfig:
    """Configuración placeholder para futura integración con Elastic Stack."""
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    index: Optional[str] = None
    batch_size: int = 200
    verify_certs: bool = True
    emit_placeholders: bool = True
    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.index)
class JsonlExporter:
    """Exporta eventos a un fichero JSON Lines."""
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self._fh = open(path, "a", buffering=1, encoding="utf-8")
    def emit(self, event: dict) -> None:
        self._fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass
class ElasticTemplateExporter:
    """Plantilla para futura exportación de eventos a Elastic Stack.
    Actualmente no realiza llamadas de red; únicamente acumula una pequeña
    muestra y genera una advertencia para recordar la implementación pendiente.
    """
    def __init__(self, config: ElasticConfig):
        self.config = config
        self._buffer: List[dict] = []
        self._warned = False
    def emit(self, event: dict) -> None:
        if not self.config.enabled:
            return
        self._buffer.append(event)
        if len(self._buffer) >= max(1, self.config.batch_size):
            self._notify_placeholder()
    def close(self) -> None:
        if self._buffer:
            self._notify_placeholder()
    # ---------------------- Helpers ----------------------
    def _notify_placeholder(self) -> None:
        if not (self.config.emit_placeholders and not self._warned):
            self._buffer.clear()
            return
        self._warned = True
        sys.stderr.write(
            "[ElasticTemplate] Integración pendiente: se descartan "
            f"{len(self._buffer)} eventos.")
        sys.stderr.write(
            "\nConfigure endpoint/index y reemplace ElasticTemplateExporter.emit() "
            "con la llamada Bulk API de Elastic para activar la ingesta.\n")
        sys.stderr.flush()
        self._buffer.clear()
class MultiExporter:
    """Agrupa múltiples exportadores y los trata como uno solo."""
    def __init__(self, exporters: Sequence[EventExporter]):
        self._exporters = list(exporters)
    def emit(self, event: dict) -> None:
        for exporter in self._exporters:
            exporter.emit(event)
    def close(self) -> None:
        for exporter in self._exporters:
            exporter.close()
# Anomalías
def a_alt_neg(evt: dict, fl: Flight): evt["altitude"] = -abs(evt["altitude"]); fl.anomaly = "ALT<0"
def a_speed_impossible(evt: dict, fl: Flight): evt["speed_knots"] = random.uniform(1500, 3000); fl.anomaly="SPD>1500"
def a_dup_icao(evt: dict, fl: Flight, dup_with: str): evt["icao"]=dup_with; fl.anomaly="DUP ICAO"
def a_teleport(evt: dict, fl: Flight):
    """Teletransporta el avión a una nueva posición aleatoria global."""
    evt["lat"] = random.uniform(-60, 80)
    evt["lon"] = random.uniform(-180, 180)
    # Actualiza el propio vuelo para que la visualización sea coherente
    fl.lat = evt["lat"]
    fl.lon = evt["lon"]
    fl.trail.clear()
    fl.anomaly = "TELEPORT"
ANOMAP = {
    "alt_neg": a_alt_neg, 
    "speed_impossible": a_speed_impossible,
    "dup_icao": a_dup_icao,
    "teleport": a_teleport
}
# Aeropuertos (código, lat, lon)
AIRPORTS: List[Tuple[str, float, float]] = [
    ("MAD", 40.472, -3.561), ("BCN", 41.297, 2.078), ("CDG", 49.009, 2.55),
    ("LHR", 51.470, -0.454), ("FRA", 50.037, 8.562), ("AMS", 52.310, 4.768),
    ("PMI", 39.551, 2.738),  ("AGP", 36.676, -4.499), ("SVQ", 37.418, -5.898),
]
# Región de mapa
MAP_LAT_MIN, MAP_LAT_MAX = 30.0, 60.0
MAP_LON_MIN, MAP_LON_MAX = -20.0, 40.0
def geo_to_grid(lat: float, lon: float, rows: int, cols: int) -> Tuple[int, int]:
    """Convierte (lat, lon) a coordenadas (y, x) dentro de una rejilla de tamaño rows x cols."""
    # área central para el mapa (bordes los pinta el render)
    lat = max(MAP_LAT_MIN, min(MAP_LAT_MAX, lat))
    lon = max(MAP_LON_MIN, min(MAP_LON_MAX, lon))
    yf = (MAP_LAT_MAX - lat) / (MAP_LAT_MAX - MAP_LAT_MIN)  # arriba->abajo
    xf = (lon - MAP_LON_MIN) / (MAP_LON_MAX - MAP_LON_MIN)
    y = int(yf * (rows - 2)) + 1
    x = int(xf * (cols - 2)) + 1
    return y, x
# ---------------------- Widgets ----------------------
class MapWidget(Widget):
    """Widget de mapa con estética enriquecida: fondo temático, aeropuertos destacados y aviones coloreados por altitud."""
    flights: List[Flight] = []
    trails_enabled: bool = True
    wind_dir_deg: float = 0.0
    wind_speed_kt: float = 0.0
    PLANE_SET = ["➤", "⬈", "⬆", "⬉", "⬅", "⬋", "⬇", "⬊"]  # 8 direcciones estilizadas
    TRAIL_COLORS = ["#f8fafc", "#e2e8f0", "#cbd5f5", "#94a3b8", "#64748b", "#475569"]
    AIRPORT_SYMBOL = "🛬"
    SEA_GRADIENT = ("#021734", "#06477a")
    LAND_GRADIENT = ("#0f3b21", "#1f6f3b")
    @staticmethod
    def heading_to_arrow(heading: float) -> str:
        # 0°=→, 45°=↗, 90°=↑, ..., 315°=↘
        idx = int(((heading % 360) + 22.5) // 45) % 8
        return MapWidget.PLANE_SET[idx]
    @staticmethod
    def altitude_style(alt_ft: float) -> Style:
        # Colorea por nivel de vuelo: bajo=verde, medio=amarillo, alto=cyan-neón
        if alt_ft < 10000:
            return Style(color="#22c55e", bold=True)
        if alt_ft < 20000:
            return Style(color="#facc15", bold=True)
        return Style(color="#38bdf8", bold=True)
    @staticmethod
    def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
        value = value.lstrip("#")
        return tuple(int(value[idx: idx + 2], 16) for idx in (0, 2, 4))
    @classmethod
    def _blend(cls, start: str, end: str, factor: float) -> str:
        factor = max(0.0, min(1.0, factor))
        sr, sg, sb = cls._hex_to_rgb(start)
        er, eg, eb = cls._hex_to_rgb(end)
        r = int(round(sr + (er - sr) * factor))
        g = int(round(sg + (eg - sg) * factor))
        b = int(round(sb + (eb - sb) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"
    @classmethod
    def _mix(cls, base: str, overlay: str, weight: float) -> str:
        weight = max(0.0, min(1.0, weight))
        br, bg, bb = cls._hex_to_rgb(base)
        or_, og, ob = cls._hex_to_rgb(overlay)
        r = int(round(br * (1 - weight) + or_ * weight))
        g = int(round(bg * (1 - weight) + og * weight))
        b = int(round(bb * (1 - weight) + ob * weight))
        return f"#{r:02x}{g:02x}{b:02x}"
    @staticmethod
    def _land_score(lat: float, lon: float) -> float:
        score = 0.0
        for _, alat, alon in AIRPORTS:
            d_lat = (lat - alat) / 3.5
            d_lon = (lon - alon) / 4.0
            score += math.exp(-(d_lat ** 2 + d_lon ** 2))
        return min(score, 1.0)
    @staticmethod
    def _grid_to_geo(y: int, x: int, rows: int, cols: int) -> Tuple[float, float]:
        usable_rows = max(1, rows - 2)
        usable_cols = max(1, cols - 2)
        yy = min(max(y - 1, 0), usable_rows - 1)
        xx = min(max(x - 1, 0), usable_cols - 1)
        lat_range = MAP_LAT_MAX - MAP_LAT_MIN
        lon_range = MAP_LON_MAX - MAP_LON_MIN
        lat = MAP_LAT_MAX - (yy / max(1, usable_rows - 1)) * lat_range
        lon = MAP_LON_MIN + (xx / max(1, usable_cols - 1)) * lon_range
        return lat, lon
    def _wind_arrow(self) -> str:
        idx = int(((self.wind_dir_deg % 360) + 22.5) // 45) % 8
        arrows = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"]
        return arrows[idx]
    def render(self) -> Panel:
        def _coerce(value: int, minimum: int) -> int:
            try:
                coerced = int(value)
            except (TypeError, ValueError):
                coerced = 0
            return max(minimum, coerced)
        width = _coerce(getattr(self.size, "width", 0), 68)
        height = _coerce(getattr(self.size, "height", 0), 24)
        # Matrices de caracteres y estilos
        grid = [[" " for _ in range(width)] for _ in range(height)]
        styles: List[List[Optional[Style]]] = [[None for _ in range(width)] for _ in range(height)]
        # Fondo temático (mar/continente) basado en aeropuertos
        for y in range(height):
            for x in range(width):
                lat, lon = self._grid_to_geo(y, x, height, width)
                lat_factor = (MAP_LAT_MAX - lat) / max(1e-6, (MAP_LAT_MAX - MAP_LAT_MIN))
                sea = self._blend(*self.SEA_GRADIENT, lat_factor)
                land = self._blend(*self.LAND_GRADIENT, lat_factor)
                land_weight = self._land_score(lat, lon)
                bg_hex = self._mix(sea, land, land_weight)
                styles[y][x] = Style(bgcolor=bg_hex)
        def put(y: int, x: int, ch: str, style: Optional[Style | str] = None, overwrite: bool = False):
            if 0 <= y < height and 0 <= x < width:
                base = styles[y][x]
                if overwrite or grid[y][x] == " ":
                    grid[y][x] = ch
                if style is None:
                    styles[y][x] = base
                else:
                    rich_style = style if isinstance(style, Style) else Style.parse(style)
                    styles[y][x] = (base or Style()) + rich_style
        # Bordes exteriores
        border_style = Style(color="grey70", bold=True)
        for x in range(width):
            put(0, x, "─", border_style, overwrite=True)
            put(height - 1, x, "─", border_style, overwrite=True)
        for y in range(height):
            put(y, 0, "│", border_style, overwrite=True)
            put(y, width - 1, "│", border_style, overwrite=True)
        put(0, 0, "┌", border_style, overwrite=True)
        put(0, width - 1, "┐", border_style, overwrite=True)
        put(height - 1, 0, "└", border_style, overwrite=True)
        put(height - 1, width - 1, "┘", border_style, overwrite=True)
        # Cuadrícula suave (lat/lon) con semitransparencia
        grid_style = Style(color="#94a3b8")
        for y in range(2, height - 1, 4):
            for x in range(1, width - 1):
                if grid[y][x] == " ":
                    put(y, x, "·", grid_style)
        for x in range(6, width - 1, 8):
            for y in range(1, height - 1):
                if grid[y][x] == " ":
                    put(y, x, "·", grid_style)
        # Aeropuertos: símbolo destacado + etiqueta con halo
        airport_label_style = Style(color="#facc15", bold=True)
        for code, alat, alon in AIRPORTS:
            y, x = geo_to_grid(alat, alon, height, width)
            if 1 <= y < height - 1 and 1 <= x < width - 1:
                put(y, x, self.AIRPORT_SYMBOL, Style(color="#fde047", bold=True), overwrite=True)
                label = f" {code}"
                for i, ch in enumerate(label, start=1):
                    if x + i < width - 1:
                        put(y, x + i, ch, airport_label_style)
        # Estelas con desvanecido
        if self.trails_enabled:
            for fl in self.flights:
                if not fl.trail:
                    continue
                trail_points = list(fl.trail)[-min(32, len(fl.trail)):]
                for idx, (tlat, tlon) in enumerate(trail_points):
                    ty, tx = geo_to_grid(tlat, tlon, height, width)
                    if 1 <= ty < height - 1 and 1 <= tx < width - 1 and grid[ty][tx] == " ":
                        ci = int((idx / max(1, len(trail_points) - 1)) * (len(self.TRAIL_COLORS) - 1))
                        shade = self.TRAIL_COLORS[-1 - ci]
                        put(ty, tx, "•", Style(color=shade, dim=ci < len(self.TRAIL_COLORS) // 2))
        # Aviones: glifo direccional y etiqueta con altitud
        for fl in self.flights:
            y, x = geo_to_grid(fl.lat, fl.lon, height, width)
            if not (1 <= y < height - 1 and 1 <= x < width - 1):
                continue
            if fl.anomaly:
                put(y, x, "✖", Style(color="#f87171", bold=True), overwrite=True)
                label = f" {fl.callsign[:6]}"
                for i, ch in enumerate(label, start=1):
                    if x + i < width - 1 and grid[y][x + i] == " ":
                        put(y, x + i, ch, Style(color="#fca5a5", italic=True))
                continue
            glyph = self.heading_to_arrow(fl.heading)
            color = self.altitude_style(fl.altitude)
            put(y, x, glyph, color, overwrite=True)
            label = f" {fl.callsign[:6]} {int(fl.altitude/1000)}k"
            for i, ch in enumerate(label, start=1):
                if x + i < width - 1 and grid[y][x + i] == " ":
                    put(y, x + i, ch, Style(color="#e2e8f0"))
        # Construcción Rich Text con estilos por celda
        out = Text()
        for yy in range(height):
            line = Text()
            for xx in range(width):
                st = styles[yy][xx]
                if st:
                    line.append(grid[yy][xx], style=st)
                else:
                    line.append(grid[yy][xx])
            out.append(line)
            if yy < height - 1:
                out.append("\n")
        wind_info = Text()
        wind_info.append(" Viento ", style="grey70")
        wind_info.append(f"{self._wind_arrow()} ", style="bold cyan")
        wind_info.append(f"{self.wind_dir_deg:03.0f}°/{self.wind_speed_kt:.0f}kt  ", style="cyan")
        wind_info.append("Vuelos ", style="grey70")
        wind_info.append(f"{len(self.flights):02d}  ", style="bold white")
        wind_info.append("Trails ", style="grey70")
        wind_info.append("ON  " if self.trails_enabled else "OFF  ", style="cyan" if self.trails_enabled else "grey50")
        content = Group(wind_info, out)
        title = f" MAPA ATC  lat[{MAP_LAT_MIN}-{MAP_LAT_MAX}] lon[{MAP_LON_MIN}-{MAP_LON_MAX}] "
        return Panel(content, title=title, border_style="cyan", box=ROUNDED)
class Legend(Static):
    def render(self):
        t = Text()
        t.append("Leyenda: ", style="bold")
        t.append("➤ avión ", style="#38bdf8 bold")
        t.append("✖ anomalía ", style="#f87171 bold")
        t.append("🛬 aeropuerto ", style="#fde047 bold")
        t.append("• estela ", style="#94a3b8")
        t.append("· rejilla", style="grey50")
        return Panel(t, title="Ayuda rápida", border_style="cyan", box=ROUNDED)
class StatusBar(Static):
    rate = reactive(10)
    fps = reactive(0.0)
    paused = reactive(False)
    anomalies_on = reactive(True)
    trails_on = reactive(True)
    emitted = reactive(0)
    remaining = reactive(0)
    def render(self):
        txt = Text()
        txt.append(f" Evts/s: {self.rate}  ", style="bold")
        if self.fps:
            txt.append(f"FPS: {self.fps:.1f}  ", style="bold")
        txt.append("PAUSADO  " if self.paused else "RUN  ", style="yellow" if self.paused else "green")
        txt.append("Anom: ON  " if self.anomalies_on else "Anom: OFF  ", style="red" if self.anomalies_on else "grey50")
        txt.append("Trails: ON  " if self.trails_on else "Trails: OFF  ", style="cyan" if self.trails_on else "grey50")
        txt.append(f"Emitted: {self.emitted}  ", style="magenta")
        if self.remaining > 0:
            txt.append(f"Remaining: {self.remaining}s  ", style="magenta")
        txt.append(f"UTC: {datetime.utcnow().strftime('%H:%M:%S')}  ", style="white")
        return Panel(txt, border_style="cyan", box=ROUNDED)
# ---------------------- App ----------------------
class ATCApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #main {
        height: 1fr;
    }
    #left {
        width: 1fr;
    }
    #right {
        width: 68;
        min-width: 52;
    }
    DataTable {
        height: 1fr;
    }
    """
    BINDINGS = [
        ("q", "quit", "Salir"),
        ("p", "toggle_pause", "Pausar"),
        ("t", "toggle_trails", "Estelas"),
        ("a", "toggle_anomalies", "Anomalías ON/OFF"),
        ("+", "inc_rate", "Más ritmo"),
        ("-", "dec_rate", "Menos ritmo"),
        ("h", "toggle_help", "Ayuda"),
        ("?", "toggle_help", "Ayuda"),
        ("f", "filter_callsign_current", "Filtro CALL"),
        ("F1", "toggle_filter_anomalies", "Solo anom"),
        ("F2", "cycle_filter_squawk", "Filtro SQK"),
    ]
    def __init__(self, *, output: str, flights: int, rate: int, duration: int,
                 anomalies: List[str], elastic_config: Optional[ElasticConfig] = None):
        super().__init__()
        self.output_path = output
        self.n_flights = flights
        self.rate = rate  # eventos por segundo
        self.duration = duration
        self.anomaly_kinds = anomalies
        self.anomalies_enabled = True if anomalies else False
        self.paused = False
        self.emitted = 0
        self.start_ts = time.time()
        self.dup_target: Optional[str] = None
        self.elastic_config = elastic_config or ElasticConfig()
        # estado de simulación
        self.flights: List[Flight] = [Flight() for _ in range(self.n_flights)]
        if "dup_icao" in self.anomaly_kinds:
            self.dup_target = random.choice(self.flights).icao
        # Salidas de eventos (archivo y plantilla Elastic)
        self.exporter = MultiExporter([
            JsonlExporter(self.output_path),
            ElasticTemplateExporter(self.elastic_config),
        ])
        # Frecuencia de actualización (ticks por segundo)
        self.tick_interval = 0.1  # 10 Hz
        self._event_carry = 0.0   # acumulador para repartir eventos por tick
        self._tick_times: Deque[float] = deque(maxlen=100)
        # Último evento por vuelo (para reflejar anomalías en la tabla)
        self.last_events: Dict[str, dict] = {}
        self._table_columns: List[str] = []
        # Filtros
        self.filter_anomalies_only: bool = False
        self.filter_squawk: Optional[str] = None
        self.filter_callsign_substr: Optional[str] = None
        self._table_supports_clear_columns: Optional[bool] = None
        # Viento (dirección de donde SOPLA)
        self.wind_dir_deg: float = random.uniform(180, 240)
        self.wind_speed_kt: float = random.uniform(5, 25)
        self._last_wind_update = time.time()
        # Inyección de anomalías: cooldown por vuelo
        self._last_inject_ts: Dict[str, float] = {}
        self._inject_cooldown_sec = 12.0
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main"):
            with Horizontal():
                self.map = MapWidget(id="left")
                yield self.map
                with Vertical(id="right"):
                    self.table = DataTable(zebra_stripes=True)
                    yield self.table
                    yield Legend()
            self.status = StatusBar()
            yield self.status
        yield Footer()
    def on_mount(self) -> None:
        """Inicializa la interfaz y programa el temporizador de simulación."""
        # Config tabla
        self._table_columns = ["ICAO", "CALL", "FL", "GS", "IAS", "VS", "MACH", "BANK", "SQK", "ANOM"]
        self.table.add_columns(*self._table_columns)
        self.table.cursor_type = "row"
        self.table.zebra_stripes = True
        # Timer de simulación a 10 Hz
        self.set_interval(self.tick_interval, self._tick)
        # Crea rutas aleatorias sencillas para algunos vuelos (LNAV demo)
        for fl in self.flights:
            if random.random() < 0.4:
                # Generar dos o tres waypoints dentro del mapa
                wps = []
                for _ in range(random.randint(2, 3)):
                    wps.append((random.uniform(MAP_LAT_MIN + 2, MAP_LAT_MAX - 2),
                                random.uniform(MAP_LON_MIN + 2, MAP_LON_MAX - 2)))
                fl.route = wps
                # VNAV: escoger un target de alt aleatorio razonable
                fl.vnav_target_alt = random.choice([12000.0, 18000.0, 24000.0, 28000.0])
    def _push_table(self):
        """Refresca el panel de tabla con un subconjunto de vuelos utilizando el último evento."""
        if self._table_supports_clear_columns is None:
            try:
                self.table.clear(columns=False)
                self._table_supports_clear_columns = True
            except TypeError:
                self._table_supports_clear_columns = False
                self.table.clear()
                if hasattr(self.table, 'columns') and not self.table.columns:
                    self.table.add_columns(*self._table_columns)
        else:
            if self._table_supports_clear_columns:
                self.table.clear(columns=False)
            else:
                self.table.clear()
                if hasattr(self.table, 'columns') and not self.table.columns:
                    self.table.add_columns(*self._table_columns)
        # Aplica filtros
        filtered: List[Flight] = []
        for fl in self.flights:
            evt = self.last_events.get(fl.icao, {})
            if self.filter_anomalies_only and not (evt.get("anomaly") or fl.anomaly):
                continue
            if self.filter_squawk and evt.get("squawk", getattr(fl, "squawk", None)) != self.filter_squawk:
                continue
            if self.filter_callsign_substr and self.filter_callsign_substr.upper() not in fl.callsign.upper():
                continue
            filtered.append(fl)
        show = sorted(filtered, key=lambda f: f.altitude, reverse=True)[: max(10, len(filtered))]
        for fl in show:
            last_evt = self.last_events.get(fl.icao, {})
            # Usa valores del último evento si existen (refleja anomalías)
            alt = float(last_evt.get("altitude", fl.altitude))
            fl_str = f"{int(alt/100):03d}"
            gs = int(last_evt.get("gs_knots", getattr(fl, "gs_knots", fl.speed)))
            ias = int(last_evt.get("ias_knots", fl.speed))
            vs = int(last_evt.get("vertical_rate", fl.vrate))
            mach = last_evt.get("mach", 0.0)
            bank = int(last_evt.get("bank_deg", 0.0))
            sqk = last_evt.get("squawk", getattr(fl, "squawk", "7000"))
            an_text = last_evt.get("anomaly") or fl.anomaly or ""
            # Severidad
            severity = self._severity_of(an_text)
            row_styles = {
                None: None,
                "warn": "yellow",
                "critical": "bold red",
            }
            style = row_styles[severity]
            def cell(text: str) -> Text:
                t = Text(text)
                if style:
                    t.stylize(style)
                return t
            self.table.add_row(
                cell(fl.icao),
                cell(fl.callsign[:8]),
                cell(fl_str),
                cell(f"{gs}"),
                cell(f"{ias}"),
                cell(f"{vs}"),
                cell(f"{mach:.2f}"),
                cell(f"{bank}"),
                cell(f"{sqk}"),
                cell(an_text),
            )
    def _save_event(self, evt: dict):
        """Escribe un evento en el fichero JSONL y actualiza el contador."""
        self.exporter.emit(evt)
        self.emitted += 1
    def _tick(self):
        """Un ciclo de simulación/render. Se invoca cada tick."""
        # Marca tiempo para calcular FPS
        now = time.time()
        self._tick_times.append(now)
        if len(self._tick_times) >= 2:
            dt_total = self._tick_times[-1] - self._tick_times[0]
            if dt_total > 0:
                self.status.fps = (len(self._tick_times) - 1) / dt_total
        # Actualiza barra de estado
        remaining = max(0, int(self.duration - (time.time() - self.start_ts))) if self.duration > 0 else 0
        self.status.rate = self.rate
        self.status.paused = self.paused
        self.status.anomalies_on = self.anomalies_enabled
        self.status.trails_on = self.map.trails_enabled
        self.status.emitted = self.emitted
        self.status.remaining = remaining
        if self.duration and time.time() - self.start_ts >= self.duration:
            self.exit()
        if self.paused:
            return
        # Emite eventos proporcionalmente a 'rate' (eventos/segundo) usando acumulador
        self._event_carry += self.rate * self.tick_interval
        events_this_tick = int(self._event_carry)
        self._event_carry -= events_this_tick
        if events_this_tick == 0 and self.rate > 0:
            events_this_tick = 1  # asegura movimiento fluido con tasas bajas
        # Actualiza viento lentamente (~cada segundo, pequeña deriva)
        if now - self._last_wind_update > 1.0:
            self._last_wind_update = now
            self.wind_dir_deg = (self.wind_dir_deg + random.uniform(-2, 2)) % 360
            self.wind_speed_kt = max(0.0, min(40.0, self.wind_speed_kt + random.uniform(-1.0, 1.0)))
        for i in range(events_this_tick):
            fl = self.flights[(self.emitted + i) % len(self.flights)]
            # Avanza el modelo con el dt del tick
            # LNAV: rumbo a siguiente waypoint si existe
            lnav_brg = None
            if fl.route:
                wp = fl.route[fl.wp_index % len(fl.route)]
                lnav_brg = bearing_to(fl.lat, fl.lon, wp[0], wp[1])
                # Si está cerca del waypoint, avanzar
                if abs(fl.lat - wp[0]) < 0.15 and abs(fl.lon - wp[1]) < 0.15:
                    fl.wp_index = (fl.wp_index + 1) % len(fl.route)
            # VNAV
            vnav_alt = fl.vnav_target_alt
            fl.step(dt=self.tick_interval, wind_dir_deg=self.wind_dir_deg, wind_speed_kt=self.wind_speed_kt,
                    lnav_bearing=lnav_brg, vnav_target_alt=vnav_alt)
            fl.anomaly = None  # se recalcula por evento
            evt = fl.snapshot()
            # Inyección de anomalías
            if self.anomalies_enabled and self.anomaly_kinds:
                last = self._last_inject_ts.get(fl.icao, 0.0)
                if (now - last) > self._inject_cooldown_sec and random.random() < 0.01:
                    choice = random.choice(self.anomaly_kinds)
                    if choice == "dup_icao" and self.dup_target:
                        ANOMAP[choice](evt, fl, self.dup_target)
                    else:
                        ANOMAP[choice](evt, fl)
                    self._last_inject_ts[fl.icao] = now
            # Detección de anomalías (reglas avanzadas)
            self._detect_and_mark_anomalies(fl, evt)
            # Guarda último evento para reflejar valores anómalos en UI
            self.last_events[fl.icao] = evt
            self._save_event(evt)
        # refresca vistas
        self.map.flights = self.flights
        self.map.wind_dir_deg = self.wind_dir_deg
        self.map.wind_speed_kt = self.wind_speed_kt
        self._push_table()
        self.map.refresh()
    # -------------- Acciones / teclas --------------
    def action_quit(self):
        self.exit()
    def action_toggle_pause(self):
        self.paused = not self.paused
    def action_toggle_trails(self):
        self.map.trails_enabled = not self.map.trails_enabled
        self.map.refresh()
    def action_toggle_anomalies(self):
        self.anomalies_enabled = not self.anomalies_enabled
    def action_inc_rate(self):
        self.rate = min(self.rate + 1, 200)
    def action_dec_rate(self):
        self.rate = max(self.rate - 1, 0)
    def action_toggle_help(self):
        self.push_screen(HelpScreen())
    # --------- Acciones de filtros ---------
    def action_toggle_filter_anomalies(self):
        self.filter_anomalies_only = not self.filter_anomalies_only
    def action_cycle_filter_squawk(self):
        order = [None, "7500", "7600", "7700", "7000", None]
        try:
            idx = order.index(self.filter_squawk)
        except ValueError:
            idx = 0
        self.filter_squawk = order[(idx + 1) % len(order)]
    def action_filter_callsign_current(self):
        # Usa la fila seleccionada (si hay) para tomar el callsign y usarlo como filtro (prefijo)
        try:
            row = self.table.cursor_row
            if row is not None and 0 <= row < len(self.flights):
                # Recupera valor visible en la tabla (2ª columna)
                # Si no se puede, usa el de la lista
                fl = self.flights[row]
                prefix = fl.callsign[:3]
                if self.filter_callsign_substr == prefix:
                    self.filter_callsign_substr = None
                else:
                    self.filter_callsign_substr = prefix
            else:
                self.filter_callsign_substr = None
        except Exception:
            self.filter_callsign_substr = None
    def on_unmount(self) -> None:
        try:
            self.exporter.close()
        except Exception:
            pass
    # --------- Utilidades de severidad ---------
    def _severity_of(self, anomaly_text: str) -> Optional[str]:
        if not anomaly_text:
            return None
        crit_tokens = ["EMERGENCY", "LOW_IAS_HIGH_ALT", "VRATE_ABN"]
        warn_tokens = ["250@10k", "ALT_MISMATCH", "LOW_QOS", "SPEED_JUMP", "ALT<0", "SPD>1500", "DUP ICAO", "TELEPORT"]
        for t in crit_tokens:
            if t in anomaly_text:
                return "critical"
        for t in warn_tokens:
            if t in anomaly_text:
                return "warn"
        return "warn"
    # --------- Detección avanzada de anomalías ---------
    def _detect_and_mark_anomalies(self, fl: Flight, evt: dict) -> None:
        """Aplica reglas de aviación para marcar anomalías complejas en el evento."""
        anomalies: List[str] = []
        # Velocidad sobre 250 KIAS por debajo de 10k ft
        if evt.get("baro_altitude", 99999) < 10000 and evt.get("ias_knots", 0) > 260:
            anomalies.append("250@10k")
        # Razón vertical excesiva
        if abs(evt.get("vertical_rate", 0)) > 6000:
            anomalies.append("VRATE_ABN")
        # Desajuste baro vs geométrico
        if abs(evt.get("altitude", 0) - evt.get("baro_altitude", 0)) > 400:
            anomalies.append("ALT_MISMATCH")
        # IAS muy baja a gran altitud (riesgo de pérdida)
        if evt.get("altitude", 0) > 20000 and evt.get("ias_knots", 999) < 140:
            anomalies.append("LOW_IAS_HIGH_ALT")
        # Calidad ADS-B baja
        if evt.get("nic", 10) < 5 or evt.get("nacp", 10) < 7 or evt.get("sil", 3) < 2:
            anomalies.append("LOW_QOS")
        # Emergencias por SQK
        if evt.get("squawk") in {"7500", "7600", "7700"}:
            anomalies.append("EMERGENCY")
        # Saltos bruscos de velocidad
        last = self.last_events.get(fl.icao)
        if last:
            if abs(evt.get("speed_knots", 0) - last.get("speed_knots", 0)) > 180:
                anomalies.append("SPEED_JUMP")
        if anomalies:
            tag = ";".join(anomalies)
            evt["anomaly"] = tag
            fl.anomaly = tag
# ---------------------- Help Screen ----------------------
class HelpScreen(Screen):
    def on_mount(self):
        txt = Text()
        txt.append("\nControles\n", style="bold underline")
        txt.append(
            " q  → salir\n"
            " p  → pausar/reanudar\n"
            " t  → alternar estelas\n"
            " a  → alternar anomalías\n"
            " + / -  → ritmo +/-\n"
            " h / ?  → esta ayuda\n\n"
        )
        txt.append("Leyenda:\n", style="bold")
        txt.append(" ➤ avión | ✖ anomalía | 🛬 aeropuerto | • estela | · rejilla\n\n", style="grey70")
        # Monta un widget estático con el panel de ayuda
        self.mount(Static(Panel(Align.left(txt), title="Ayuda", border_style="magenta", box=ROUNDED)))
    async def on_key(self, _: Key):
        # cerrar con cualquier tecla
        await self.app.pop_screen()
# ---------------------- CLI ----------------------
def parse_args():
    p = argparse.ArgumentParser(description="ADS-B ATC Textual TUI")
    p.add_argument("-o", "--output", required=True, help="Ruta del JSONL (append).")
    p.add_argument("-n", "--flights", type=int, default=20, help="Número de vuelos simultáneos.")
    p.add_argument("-r", "--rate", type=int, default=10, help="Eventos por tick (por segundo).")
    p.add_argument("-d", "--duration", type=int, default=0, help="Duración en segundos (0 = infinito).")
    p.add_argument("-A", "--anomalies", type=str, default="", help="Lista separada por comas: alt_neg,speed_impossible,dup_icao,teleport")
    p.add_argument("--elastic-endpoint", type=str, default=None,
                   help="URL del cluster Elastic (https://...). Si no se indica, se omite la exportación.")
    p.add_argument("--elastic-api-key", type=str, default=None,
                   help="API Key para autenticación con Elastic (formato id:api_key).")
    p.add_argument("--elastic-index", type=str, default=None,
                   help="Nombre del índice destino para los eventos.")
    p.add_argument("--elastic-batch-size", type=int, default=200,
                   help="Tamaño de lote para envíos bulk (placeholder).")
    p.add_argument("--elastic-skip-verify", action="store_true",
                   help="Desactiva la verificación TLS (solo laboratorios).")
    return p.parse_args()
def main():
    args = parse_args()
    anomalies = [x.strip() for x in args.anomalies.split(",") if x.strip()]
    elastic_cfg = ElasticConfig(
        endpoint=args.elastic_endpoint,
        api_key=args.elastic_api_key,
        index=args.elastic_index,
        batch_size=args.elastic_batch_size,
        verify_certs=not args.elastic_skip_verify,
    )
    app = ATCApp(
        output=args.output,
        flights=args.flights,
        rate=args.rate,
        duration=args.duration,
        anomalies=anomalies,
        elastic_config=elastic_cfg,
    )
    app.run()
    
if __name__ == "__main__":
    main()