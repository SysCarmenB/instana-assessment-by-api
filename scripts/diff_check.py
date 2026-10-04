"""
Verificacion diferencial: compara los objetos que ve el cliente Python (REST
directo) contra lo que devuelve el servidor MCP, sobre una muestra.

Esto NO es un test automatizado (el MCP no es accesible desde un script
standalone, solo desde una sesion con las herramientas MCP cargadas). Este
script prepara el lado Python; el contraste con MCP se hace a mano,
comparando su salida con las consultas equivalentes por MCP.

Uso:
    export INSTANA_API_TOKEN=...
    python scripts/diff_check.py --config config/client.yaml
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# La consola de Windows usa cp1252 por defecto. Los datos de Instana traen
# emoji con cierta frecuencia (nombres de dashboard, tags): sin esto el
# script revienta con UnicodeEncodeError en mitad de una corrida.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from instana_assessment.instana_client import InstanaClient
from instana_assessment.collectors.aggregate import apply_scope
from instana_assessment.collectors.topology import build_topology


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/client.yaml")
    args = parser.parse_args()

    config = yaml.safe_load(open(args.config, encoding="utf-8"))
    client = InstanaClient.from_config(config["instana"])
    scope = config.get("scope", {}) or {}
    window_ms = int(scope.get("window_hours", 24)) * 3_600_000

    topology = build_topology(client, window_ms=window_ms)
    topology = apply_scope(topology, scope)

    print(f"=== Muestra: {len(topology.apps)} aplicaciones en alcance ===\n")

    for app in topology.apps:
        print(f"--- {app.label} ---")
        print(f"  applicationId: {app.id}")
        print(f"  serviceIds:    {sorted(app.service_ids)}")
        print(f"  endpointIds:   {sorted(app.endpoint_ids)}")

    slos = client.list_slo_configs()
    print(f"\n=== SLOs vistos por REST: {len(slos)} ===")
    by_app = topology.by_app_id()
    by_svc = topology.by_service_id()
    by_ep = topology.by_endpoint_id()
    for slo in slos:
        entity = slo.get("entity") or {}
        matched = (
            by_app.get(entity.get("applicationId"))
            or by_svc.get(entity.get("serviceId"))
            or by_ep.get(entity.get("endpointId"))
        )
        print(
            f"  {slo['id']}  {slo['name']!r:40s} "
            f"-> {matched.label if matched else '(sin enlace por ID)'}"
        )

    alerts = client.list_application_alert_configs()
    print(f"\n=== Alert configs vistos por REST: {len(alerts)} ===")
    for cfg in alerts:
        app_ids = {cfg.get("applicationId")} | set((cfg.get("applications") or {}).keys())
        app_ids.discard(None)
        matches = [by_app[i].label for i in app_ids if i in by_app]
        if matches:
            print(f"  {cfg['id']}  {cfg['name']!r:40s} -> {matches}")

    dashboards = client.list_custom_dashboards()
    print(f"\n=== Dashboards vistos por REST: {len(dashboards)} ===")
    for d in dashboards:
        print(f"  {d['id']}  {d.get('title')!r}")


if __name__ == "__main__":
    main()
