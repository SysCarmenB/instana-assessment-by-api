from __future__ import annotations

from typing import Any

from ..instana_client import InstanaClient
from . import alerts, apm, dashboards, events, governance, infra, rum, slo
from .topology import Topology, build_topology


def apply_scope(topology: Topology, scope: dict[str, Any]) -> Topology:
    """
    Reduce el catalogo descubierto al conjunto que el assessment debe evaluar.

    scope admite:
      name_filter      substring case-insensitive sobre el nombre (p.ej. "PROD")
      require_traffic  descarta perspectivas sin servicios ni endpoints
      top_n            se queda con las N de mayor volumen observable
    """
    apps = list(topology.apps)

    name_filter = (scope.get("name_filter") or "").strip().lower()
    if name_filter:
        apps = [a for a in apps if name_filter in a.label.lower()]

    if scope.get("require_traffic", True):
        apps = [a for a in apps if a.service_ids or a.endpoint_ids]

    # Proxy de volumen observable: cuantos endpoints y servicios se le ven.
    apps.sort(key=lambda a: (len(a.endpoint_ids), len(a.service_ids)), reverse=True)

    top_n = scope.get("top_n")
    if top_n:
        apps = apps[: int(top_n)]

    return Topology(apps=apps)


def collect_all(
    client: InstanaClient, config: dict[str, Any]
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """
    Corre todos los collectors contra la API de Instana y arma dos
    diccionarios en paralelo, ambos { app_name: { dim_key: valor } }:

      evidence -> "full"/"partial"/"none". Va a scoring.py, exactamente el
                  mismo shape que produce la lectura del CSV manual.
      trace    -> texto legible de que objeto (SLO, alerta, dashboard,
                  evento...) sustenta ese veredicto. Solo existe en modo
                  live; en modo --source csv queda {} porque el Excel
                  digitalizado no trae esa informacion.

    La topologia (apps -> servicios -> endpoints) se construye una sola vez y
    la reutilizan cinco dimensiones para enlazar por ID.
    """
    scope = config.get("scope", {}) or {}
    max_apps = scope.get("max_apps")

    print("  [1/9] descubriendo topologia (apps, servicios, endpoints)...")
    window_ms = int(scope.get("window_hours", 24)) * 3_600_000
    topology = build_topology(client, max_apps=max_apps, window_ms=window_ms)
    discovered = len(topology.apps)

    # Alcance. La metodologia del assessment manual evalua el "Top N con
    # nomenclatura PROD, priorizado por volumen", no el catalogo entero. Un
    # tenant acumula perspectivas de aplicacion abandonadas sin trafico:
    # puntuarlas hunde el promedio y no dice nada del estado real.
    topology = apply_scope(topology, scope)
    print(f"        {discovered} aplicaciones descubiertas -> {len(topology.apps)} en alcance")
    if not topology.apps:
        print("  [AVISO] el filtro de alcance dejo 0 aplicaciones; revisar 'scope' en el config")

    print("  [2/9] APM")
    apm_res = apm.apm_evidence(topology)
    print("  [3/9] RUM/Mobile/Synthetic")
    rum_res = rum.rum_evidence(client, topology)
    print("  [4/9] SLO/Apdex")
    slo_res = slo.slo_evidence(client, topology)
    print("  [5/9] Smart Alerts")
    alerts_res = alerts.alerts_evidence(client, topology)
    print("  [6/9] Dashboards")
    dash_res = dashboards.dashboards_evidence(client, topology)
    print("  [7/9] Infraestructura")
    infra_res = infra.infra_evidence(client, topology)
    print("  [8/9] Eventos")
    lookback = int(scope.get("events_lookback_days", 7))
    events_res = events.events_evidence(client, topology, lookback_days=lookback)
    print("  [9/9] Gobierno")
    gov_res = governance.governance_evidence(
        topology,
        config["governance"]["csv_path"],
        dashboard_owners=dash_res.owners_by_app,
        automation_actions=client.list_automation_actions(),
    )

    results = {
        "apm": apm_res,
        "rum": rum_res,
        "slo": slo_res,
        "alerts": alerts_res,
        "dashboard": dash_res,
        "infra": infra_res,
        "events": events_res,
        "governance": gov_res,
    }

    labels = topology.labels
    evidence: dict[str, dict[str, str]] = {name: {} for name in labels}
    trace_by_app: dict[str, dict[str, str]] = {name: {} for name in labels}
    for dim_key, res in results.items():
        for name in labels:
            evidence[name][dim_key] = res.evidence.get(name, "none")
            t = res.trace.get(name)
            if t:
                trace_by_app[name][dim_key] = t

    print(f"  Llamadas a la API: {client.call_count}")
    return evidence, trace_by_app
