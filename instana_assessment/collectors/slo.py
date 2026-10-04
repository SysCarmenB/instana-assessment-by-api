"""
Dimension SLO/Apdex (peso 15).

Enlace determinista: cada SLO trae entity.applicationId / serviceId /
endpointId. Verificado contra el tenant. No hace falta adivinar por nombre.
"""
from __future__ import annotations

from ..instana_client import InstanaClient
from .match import find_match
from .result import CollectorResult
from .topology import Topology


def slo_evidence(client: InstanaClient, topology: Topology) -> CollectorResult:
    """
    full     -> existe un SLO que apunta por ID a la app, a uno de sus
                servicios o a uno de sus endpoints
    partial  -> solo hay coincidencia por nombre (vinculo no formal)
    none     -> sin SLO
    """
    slos = client.list_slo_configs()

    by_app = topology.by_app_id()
    by_svc = topology.by_service_id()
    by_ep = topology.by_endpoint_id()

    evidence: dict[str, str] = {a.label: "none" for a in topology.apps}
    trace: dict[str, str] = {}
    name_candidates: list[str] = []

    for slo in slos:
        entity = slo.get("entity") or {}
        matched = None
        via = ""
        if entity.get("applicationId"):
            matched = by_app.get(entity["applicationId"])
            via = "applicationId"
        if matched is None and entity.get("serviceId"):
            matched = by_svc.get(entity["serviceId"])
            via = "serviceId"
        if matched is None and entity.get("endpointId"):
            matched = by_ep.get(entity["endpointId"])
            via = "endpointId"

        if matched is not None:
            evidence[matched.label] = "full"
            trace[matched.label] = f"SLO {slo['id']} {slo['name']!r} (enlace por {via})"
        else:
            name = slo.get("name")
            if name:
                name_candidates.append(name)

    for app in topology.apps:
        if evidence[app.label] == "none":
            m = find_match(app.label, name_candidates)
            if m:
                evidence[app.label] = "partial"
                trace[app.label] = f"SLO {m!r} (solo coincidencia de nombre, sin ID)"

    return CollectorResult(evidence=evidence, trace=trace)
