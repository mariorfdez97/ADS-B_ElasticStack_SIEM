from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence


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

    def _notify_placeholder(self) -> None:
        if not (self.config.emit_placeholders and not self._warned):
            self._buffer.clear()
            return
        self._warned = True
        sys.stderr.write(
            "[ElasticTemplate] Integración pendiente: se descartan " f"{len(self._buffer)} eventos."
        )
        sys.stderr.write(
            "\nConfigure endpoint/index y reemplace ElasticTemplateExporter.emit() "
            "con la llamada Bulk API de Elastic para activar la ingesta.\n"
        )
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
