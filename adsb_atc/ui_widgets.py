from __future__ import annotations

import math
from typing import List, Optional, Tuple

from rich.box import ROUNDED
from rich.console import Group
from rich.panel import Panel
from rich.style import Style
from rich.text import Text
from textual.widget import Widget

from .model import Flight
from .utils import AIRPORTS, MAP_LAT_MAX, MAP_LAT_MIN, MAP_LON_MAX, MAP_LON_MIN, geo_to_grid


class MapWidget(Widget):
    """Widget de mapa con estética enriquecida: fondo temático, aeropuertos destacados y aviones coloreados por altitud."""

    flights: List[Flight] = []
    trails_enabled: bool = True
    wind_dir_deg: float = 0.0
    wind_speed_kt: float = 0.0

    PLANE_SET = ["➤", "⬈", "⬆", "⬉", "⬅", "⬋", "⬇", "⬊"]
    TRAIL_COLORS = ["#f8fafc", "#e2e8f0", "#cbd5f5", "#94a3b8", "#64748b", "#475569"]
    AIRPORT_SYMBOL = "🛬"
    SEA_GRADIENT = ("#021734", "#06477a")
    LAND_GRADIENT = ("#0f3b21", "#1f6f3b")

    @staticmethod
    def heading_to_arrow(heading: float) -> str:
        idx = int(((heading % 360) + 22.5) // 45) % 8
        return MapWidget.PLANE_SET[idx]

    @staticmethod
    def altitude_style(alt_ft: float) -> Style:
        if alt_ft < 10000:
            return Style(color="#22c55e", bold=True)
        if alt_ft < 20000:
            return Style(color="#facc15", bold=True)
        return Style(color="#38bdf8", bold=True)

    @staticmethod
    def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
        value = value.lstrip("#")
        return tuple(int(value[idx : idx + 2], 16) for idx in (0, 2, 4))

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

        grid = [[" " for _ in range(width)] for _ in range(height)]
        styles: List[List[Optional[Style]]] = [[None for _ in range(width)] for _ in range(height)]

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

        grid_style = Style(color="#94a3b8")
        for y in range(2, height - 1, 4):
            for x in range(1, width - 1):
                if grid[y][x] == " ":
                    put(y, x, "·", grid_style)
        for x in range(6, width - 1, 8):
            for y in range(1, height - 1):
                if grid[y][x] == " ":
                    put(y, x, "·", grid_style)

        airport_label_style = Style(color="#facc15", bold=True)
        for code, alat, alon in AIRPORTS:
            y, x = geo_to_grid(alat, alon, height, width)
            if 1 <= y < height - 1 and 1 <= x < width - 1:
                put(y, x, self.AIRPORT_SYMBOL, Style(color="#fde047", bold=True), overwrite=True)
                label = f" {code}"
                for i, ch in enumerate(label, start=1):
                    if x + i < width - 1:
                        put(y, x + i, ch, airport_label_style)

        if self.trails_enabled:
            for fl in self.flights:
                if not fl.trail:
                    continue
                trail_points = list(fl.trail)[-min(32, len(fl.trail)) :]
                for idx, (tlat, tlon) in enumerate(trail_points):
                    ty, tx = geo_to_grid(tlat, tlon, height, width)
                    if 1 <= ty < height - 1 and 1 <= tx < width - 1 and grid[ty][tx] == " ":
                        ci = int((idx / max(1, len(trail_points) - 1)) * (len(self.TRAIL_COLORS) - 1))
                        shade = self.TRAIL_COLORS[-1 - ci]
                        put(ty, tx, "•", Style(color=shade, dim=ci < len(self.TRAIL_COLORS) // 2))

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


def build_legend_panel() -> Panel:
    t = Text()
    t.append("Leyenda: ", style="bold")
    t.append("➤ avión ", style="#38bdf8 bold")
    t.append("✖ anomalía ", style="#f87171 bold")
    t.append("🛬 aeropuerto ", style="#fde047 bold")
    t.append("• estela ", style="#94a3b8")
    t.append("· rejilla", style="grey50")
    return Panel(t, title="Ayuda rápida", border_style="cyan", box=ROUNDED)
