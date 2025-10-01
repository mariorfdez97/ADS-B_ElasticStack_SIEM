from __future__ import annotations

from datetime import datetime

from rich.box import ROUNDED
from rich.panel import Panel
from rich.text import Text
from textual.reactive import reactive
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Static
from textual.events import Key


class Legend(Static):
    def render(self):  # type: ignore[override]
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

    def render(self):  # type: ignore[override]
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


class HelpScreen(Screen):
    def on_mount(self):  # type: ignore[override]
        from rich.align import Align

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
        self.mount(Static(Panel(Align.left(txt), title="Ayuda", border_style="magenta", box=ROUNDED)))

    async def on_key(self, _: Key):  # type: ignore[override]
        await self.app.pop_screen()
