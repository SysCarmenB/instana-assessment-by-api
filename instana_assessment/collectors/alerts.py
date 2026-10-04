"""
Dimension Smart Alerts (peso 15).

Dos correcciones sobre el colector original:

1. Endpoint. Usaba /api/events/settings/event-specifications/custom, que son
   custom events, no las Smart Alerts de aplicacion. El endpoint correcto es
   /api/events/settings/application-alert-configs (el antiguo
   /api/application-alert-configs da 404).

2. Enlace. Cada config trae applicationId y un mapa 'applications' indexado por
   applicationId. Enlace por ID, no por nombre.

Ademas el config expone 'enabled' y 'alertChannelIds', que es lo que distingue
una alerta accionable de ruido inactivo: la recomendacion del Excel sobre
revisar el volumen de Smart Alerts.
"""
from __future__ import annotations

from ..instana_client import InstanaClient
from .result import CollectorResult
from .topology import Topology


def alerts_evidence(client: InstanaClient, topology: Topology) -> CollectorResult:
    """
    full     -> alerta habilitada que cubre la app por ID y tiene canal de aviso
    partial  -> alerta que cubre la app pero esta deshabilitada o sin canal
    none     -> ninguna alerta la cubre
    """
    configs = client.list_application_alert_configs()

    evidence: dict[str, str] = {a.label: "none" for a in topology.apps}
    trace: dict[str, str] = {}
    by_app = topology.by_app_id()
    rank = {"none": 0, "partial": 1, "full": 2}

    for cfg in configs:
        app_ids: set[str] = set()
        if cfg.get("applicationId"):
            app_ids.add(cfg["applicationId"])
        for key, val in (cfg.get("applications") or {}).items():
            app_ids.add(key)
            if isinstance(val, dict) and val.get("applicationId"):
                app_ids.add(val["applicationId"])

        enabled = cfg.get("enabled", True)
        has_channel = bool(cfg.get("alertChannelIds") or cfg.get("alertChannels"))
        level = "full" if (enabled and has_channel) else "partial"
        reason = "habilitada + canal" if level == "full" else "deshabilitada o sin canal"

        for app_id in app_ids:
            app = by_app.get(app_id)
            if app is None:
                continue
            if rank[level] > rank[evidence[app.label]]:
                evidence[app.label] = level
                trace[app.label] = f"alerta {cfg['id']} {cfg['name']!r} ({reason})"

    return CollectorResult(evidence=evidence, trace=trace)
