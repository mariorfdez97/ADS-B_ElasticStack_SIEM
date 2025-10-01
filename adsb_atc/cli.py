from __future__ import annotations

import argparse

from .app import ATCApp
from .exporters import ElasticConfig


def parse_args():
    p = argparse.ArgumentParser(description="ADS-B ATC Textual TUI")
    p.add_argument("-o", "--output", required=True, help="Ruta del JSONL (append).")
    p.add_argument("-n", "--flights", type=int, default=20, help="Número de vuelos simultáneos.")
    p.add_argument("-r", "--rate", type=int, default=10, help="Eventos por tick (por segundo).")
    p.add_argument("-d", "--duration", type=int, default=0, help="Duración en segundos (0 = infinito).")
    p.add_argument(
        "-A",
        "--anomalies",
        type=str,
        default="",
        help="Lista separada por comas: alt_neg,speed_impossible,dup_icao,teleport",
    )
    p.add_argument(
        "--elastic-endpoint",
        type=str,
        default=None,
        help="URL del cluster Elastic (https://...). Si no se indica, se omite la exportación.",
    )
    p.add_argument(
        "--elastic-api-key",
        type=str,
        default=None,
        help="API Key para autenticación con Elastic (formato id:api_key).",
    )
    p.add_argument("--elastic-index", type=str, default=None, help="Nombre del índice destino para los eventos.")
    p.add_argument("--elastic-batch-size", type=int, default=200, help="Tamaño de lote para envíos bulk (placeholder).")
    p.add_argument("--elastic-skip-verify", action="store_true", help="Desactiva la verificación TLS (solo laboratorios).")
    return p.parse_args()


def main() -> None:
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


if __name__ == "__main__":  # pragma: no cover
    main()
