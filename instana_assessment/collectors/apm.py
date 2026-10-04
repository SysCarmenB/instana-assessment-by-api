"""
Dimension APM (peso 20).

Criterio del Excel: "Aplicacion visible, servicios, calls, latencia, error rate
y health."

El colector original devolvia "full" para toda aplicacion seleccionada, por
definicion. La dimension de mayor peso repartia el maximo sin comprobar nada:
en la corrida contra el tenant de demo, 50 de 50 apps sacaban 20/20. Una
dimension que puntua igual a todos no aporta informacion.
"""
from __future__ import annotations

from .result import CollectorResult
from .topology import Topology


def apm_evidence(topology: Topology) -> CollectorResult:
    """
    full     -> la aplicacion tiene servicios Y endpoints descubiertos
    partial  -> tiene una de las dos cosas (instrumentacion incompleta)
    none     -> entidad vacia: existe en el catalogo pero no se observa nada
    """
    evidence: dict[str, str] = {}
    trace: dict[str, str] = {}
    for app in topology.apps:
        n_svc, n_ep = len(app.service_ids), len(app.endpoint_ids)
        has_services = n_svc > 0
        has_endpoints = n_ep > 0
        if has_services and has_endpoints:
            evidence[app.label] = "full"
        elif has_services or has_endpoints:
            evidence[app.label] = "partial"
        else:
            evidence[app.label] = "none"
        trace[app.label] = f"{n_svc} servicio(s), {n_ep} endpoint(s) descubiertos"
    return CollectorResult(evidence=evidence, trace=trace)
