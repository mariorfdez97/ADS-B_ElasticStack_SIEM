from __future__ import annotations

import random
import time
from collections import deque
from typing import Deque, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header

from .anomalies import ANOMAP
from .exporters import ElasticConfig, ElasticTemplateExporter, JsonlExporter, MultiExporter
from .model import Flight
from .ui_components import HelpScreen, Legend, StatusBar
from .ui_widgets import MapWidget
from .utils import MAP_LAT_MAX, MAP_LAT_MIN, MAP_LON_MAX, MAP_LON_MIN, bearing_to


class ATCApp(App):
    CSS = """
    Screen { layout: vertical; }
    #main { height: 1fr; }
    #left { width: 1fr; }
    #right { width: 68; min-width: 52; }
    DataTable { height: 1fr; }
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

    def __init__(
        self,
        *,
        output: str,
        flights: int,
        rate: int,
        duration: int,
        anomalies: List[str],
        elastic_config: Optional[ElasticConfig] = None,
    ):
        super().__init__()
        self.output_path = output
        self.n_flights = flights
        self.rate = rate
        self.duration = duration
        self.anomaly_kinds = anomalies
        self.anomalies_enabled = True if anomalies else False
        self.paused = False
        self.emitted = 0
        self.start_ts = time.time()
        self.dup_target: Optional[str] = None
        self.elastic_config = elastic_config or ElasticConfig()

        self.flights: List[Flight] = [Flight() for _ in range(self.n_flights)]
        if "dup_icao" in self.anomaly_kinds:
            self.dup_target = random.choice(self.flights).icao

        self.exporter = MultiExporter([
            JsonlExporter(self.output_path),
            ElasticTemplateExporter(self.elastic_config),
        ])

        self.tick_interval = 0.1  # 10 Hz
        self._event_carry = 0.0
        self._tick_times: Deque[float] = deque(maxlen=100)
        self.last_events: Dict[str, dict] = {}
        self._table_columns: List[str] = []
        self.filter_anomalies_only: bool = False
        self.filter_squawk: Optional[str] = None
        self.filter_callsign_substr: Optional[str] = None
        self._table_supports_clear_columns: Optional[bool] = None
        self.wind_dir_deg: float = random.uniform(180, 240)
        self.wind_speed_kt: float = random.uniform(5, 25)
        self._last_wind_update = time.time()
        self._last_inject_ts: Dict[str, float] = {}
        self._inject_cooldown_sec = 12.0

    def compose(self) -> ComposeResult:  # type: ignore[override]
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

    def on_mount(self) -> None:  # type: ignore[override]
        self._table_columns = ["ICAO", "CALL", "FL", "GS", "IAS", "VS", "MACH", "BANK", "SQK", "ANOM"]
        self.table.add_columns(*self._table_columns)
        self.table.cursor_type = "row"
        self.table.zebra_stripes = True
        self.set_interval(self.tick_interval, self._tick)
        for fl in self.flights:
            if random.random() < 0.4:
                wps = []
                for _ in range(random.randint(2, 3)):
                    wps.append(
                        (
                            random.uniform(MAP_LAT_MIN + 2, MAP_LAT_MAX - 2),
                            random.uniform(MAP_LON_MIN + 2, MAP_LON_MAX - 2),
                        )
                    )
                fl.route = wps
                fl.vnav_target_alt = random.choice([12000.0, 18000.0, 24000.0, 28000.0])

    def _push_table(self):
        if self._table_supports_clear_columns is None:
            try:
                self.table.clear(columns=False)
                self._table_supports_clear_columns = True
            except TypeError:
                self._table_supports_clear_columns = False
                self.table.clear()
                if hasattr(self.table, "columns") and not self.table.columns:
                    self.table.add_columns(*self._table_columns)
        else:
            if self._table_supports_clear_columns:
                self.table.clear(columns=False)
            else:
                self.table.clear()
                if hasattr(self.table, "columns") and not self.table.columns:
                    self.table.add_columns(*self._table_columns)

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
            alt = float(last_evt.get("altitude", fl.altitude))
            fl_str = f"{int(alt/100):03d}"
            gs = int(last_evt.get("gs_knots", getattr(fl, "gs_knots", fl.speed)))
            ias = int(last_evt.get("ias_knots", fl.speed))
            vs = int(last_evt.get("vertical_rate", fl.vrate))
            mach = last_evt.get("mach", 0.0)
            bank = int(last_evt.get("bank_deg", 0.0))
            sqk = last_evt.get("squawk", getattr(fl, "squawk", "7000"))
            an_text = last_evt.get("anomaly") or fl.anomaly or ""

            def cell(text: str):
                from rich.text import Text

                t = Text(text)
                severity = self._severity_of(an_text)
                row_styles = {None: None, "warn": "yellow", "critical": "bold red"}
                style = row_styles[severity]
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
        self.exporter.emit(evt)
        self.emitted += 1

    def _tick(self):
        now = time.time()
        self._tick_times.append(now)
        if len(self._tick_times) >= 2:
            dt_total = self._tick_times[-1] - self._tick_times[0]
            if dt_total > 0:
                self.status.fps = (len(self._tick_times) - 1) / dt_total

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

        self._event_carry += self.rate * self.tick_interval
        events_this_tick = int(self._event_carry)
        self._event_carry -= events_this_tick
        if events_this_tick == 0 and self.rate > 0:
            events_this_tick = 1

        if now - self._last_wind_update > 1.0:
            self._last_wind_update = now
            self.wind_dir_deg = (self.wind_dir_deg + random.uniform(-2, 2)) % 360
            self.wind_speed_kt = max(0.0, min(40.0, self.wind_speed_kt + random.uniform(-1.0, 1.0)))

        for i in range(events_this_tick):
            fl = self.flights[(self.emitted + i) % len(self.flights)]
            lnav_brg = None
            if fl.route:
                wp = fl.route[fl.wp_index % len(fl.route)]
                lnav_brg = bearing_to(fl.lat, fl.lon, wp[0], wp[1])
                if abs(fl.lat - wp[0]) < 0.15 and abs(fl.lon - wp[1]) < 0.15:
                    fl.wp_index = (fl.wp_index + 1) % len(fl.route)
            vnav_alt = fl.vnav_target_alt
            fl.step(
                dt=self.tick_interval,
                wind_dir_deg=self.wind_dir_deg,
                wind_speed_kt=self.wind_speed_kt,
                lnav_bearing=lnav_brg,
                vnav_target_alt=vnav_alt,
            )
            fl.anomaly = None
            evt = fl.snapshot()
            if self.anomalies_enabled and self.anomaly_kinds:
                last = self._last_inject_ts.get(fl.icao, 0.0)
                if (now - last) > self._inject_cooldown_sec and random.random() < 0.01:
                    choice = random.choice(self.anomaly_kinds)
                    if choice == "dup_icao" and self.dup_target:
                        ANOMAP[choice](evt, fl, self.dup_target)
                    else:
                        ANOMAP[choice](evt, fl)
                    self._last_inject_ts[fl.icao] = now
            self._detect_and_mark_anomalies(fl, evt)
            self.last_events[fl.icao] = evt
            self._save_event(evt)

        self.map.flights = self.flights
        self.map.wind_dir_deg = self.wind_dir_deg
        self.map.wind_speed_kt = self.wind_speed_kt
        self._push_table()
        self.map.refresh()

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
        try:
            row = self.table.cursor_row
            if row is not None and 0 <= row < len(self.flights):
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

    def on_unmount(self) -> None:  # type: ignore[override]
        try:
            self.exporter.close()
        except Exception:
            pass

    def _severity_of(self, anomaly_text: str):
        if not anomaly_text:
            return None
        crit_tokens = ["EMERGENCY", "LOW_IAS_HIGH_ALT", "VRATE_ABN"]
        warn_tokens = [
            "250@10k",
            "ALT_MISMATCH",
            "LOW_QOS",
            "SPEED_JUMP",
            "ALT<0",
            "SPD>1500",
            "DUP ICAO",
            "TELEPORT",
        ]
        for t in crit_tokens:
            if t in anomaly_text:
                return "critical"
        for t in warn_tokens:
            if t in anomaly_text:
                return "warn"
        return "warn"

    def _detect_and_mark_anomalies(self, fl: Flight, evt: dict) -> None:
        anomalies: List[str] = []
        if evt.get("baro_altitude", 99999) < 10000 and evt.get("ias_knots", 0) > 260:
            anomalies.append("250@10k")
        if abs(evt.get("vertical_rate", 0)) > 6000:
            anomalies.append("VRATE_ABN")
        if abs(evt.get("altitude", 0) - evt.get("baro_altitude", 0)) > 400:
            anomalies.append("ALT_MISMATCH")
        if evt.get("altitude", 0) > 20000 and evt.get("ias_knots", 999) < 140:
            anomalies.append("LOW_IAS_HIGH_ALT")
        if evt.get("nic", 10) < 5 or evt.get("nacp", 10) < 7 or evt.get("sil", 3) < 2:
            anomalies.append("LOW_QOS")
        if evt.get("squawk") in {"7500", "7600", "7700"}:
            anomalies.append("EMERGENCY")
        last = self.last_events.get(fl.icao)
        if last:
            if abs(evt.get("speed_knots", 0) - last.get("speed_knots", 0)) > 180:
                anomalies.append("SPEED_JUMP")
        if anomalies:
            tag = ";".join(anomalies)
            evt["anomaly"] = tag
            fl.anomaly = tag
