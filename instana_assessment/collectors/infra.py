"""
Dimension Infraestructura (peso 10).

El colector original llamaba a /api/infrastructure-monitoring/snapshots con
q="" y recibia HTTP 400: "query should not be empty or wildcard(*)". Se
interpreto como endpoint no disponible y la dimension puntuaba 0 en todas las
apps. El parametro correcto se llama 'query' y exige un valor real.

Enfoque: en vez de bajar todos los snapshots y cruzar nombres, se desciende
desde la aplicacion. Los endpoints exponen 'technologies' (kubernetesService,
pythonRuntimePlatform, ...), que ya identifica la capa de ejecucion sobre la
que corre la app.
"""
from __future__ import annotations

from ..instana_client import InstanaClient
from .result import CollectorResult
from .topology import Topology


def infra_evidence(client: InstanaClient, topology: Topology) -> CollectorResult:
    """
    full     -> se conoce la tecnologia de ejecucion Y hay entidades de
                infraestructura monitoreadas en el tenant
    partial  -> la app tiene servicios pero no se pudo identificar la capa
    none     -> sin vinculo con infraestructura
    """
    state = client.monitoring_state()
    has_monitored_infra = bool(state.get("hasEntities")) or bool(state.get("hostCount"))
    host_count = state.get("hostCount", "?")

    evidence: dict[str, str] = {}
    trace: dict[str, str] = {}
    for app in topology.apps:
        if app.technologies and has_monitored_infra:
            evidence[app.label] = "full"
            trace[app.label] = (
                f"technologies={sorted(app.technologies)} "
                f"(tenant con {host_count} host(s) monitoreados)"
            )
        elif app.service_ids:
            evidence[app.label] = "partial"
            trace[app.label] = "tiene servicios pero sin technologies identificadas"
        else:
            evidence[app.label] = "none"
            trace[app.label] = "sin servicios ni technologies"
    return CollectorResult(evidence=evidence, trace=trace)
