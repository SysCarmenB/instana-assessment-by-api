"""
Dimension Eventos/Diagnostico (peso 10).

Hallazgo que cambia el enfoque: en una ventana de 6 horas /api/events devolvio
9.787 eventos, de los cuales 9.778 eran INFRASTRUCTURE y solo 9 de aplicacion,
servicio o endpoint. Cruzar nombres de app contra diez mil etiquetas de pods es
caro y genera falsos positivos. Se filtra por entityType primero.

Donde esta el ID determinista (verificado, difiere segun el tipo):
  APPLICATION -> snapshotId  es el applicationId
  SERVICE     -> metrics[].entityId.steadyId  es el serviceId
  ENDPOINT    -> metrics[].entityId.steadyId  es el endpointId

Nota: /api/events devuelve entityLabel PLANO. Es el servidor MCP el que lo
anida en entity.label; el cliente REST no.
"""
from __future__ import annotations

import time
from typing import Any

from ..instana_client import InstanaClient
from .result import CollectorResult
from .topology import Topology

_RELEVANT_TYPES = {"APPLICATION", "SERVICE", "ENDPOINT"}


def _steady_ids(event: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for metric in event.get("metrics") or []:
        entity_id = metric.get("entityId") or {}
        steady = entity_id.get("steadyId")
        if steady:
            out.add(steady)
    for key in ("applicationId", "serviceId", "endpointId", "endpointServiceId"):
        if event.get(key):
            out.add(event[key])
    return out


def events_evidence(
    client: InstanaClient, topology: Topology, lookback_days: int = 7
) -> CollectorResult:
    """
    full     -> hay al menos un evento de tipo 'issue' enlazado por ID
    partial  -> solo hay eventos de cambio/estado, o el enlace fue por nombre
    none     -> sin evidencia de diagnostico
    """
    now_ms = int(time.time() * 1000)
    from_ms = now_ms - lookback_days * 24 * 60 * 60 * 1000
    events = client.list_events(from_ms, now_ms)

    by_app = topology.by_app_id()
    by_svc = topology.by_service_id()
    by_ep = topology.by_endpoint_id()
    labels = {a.label: a for a in topology.apps}

    evidence: dict[str, str] = {a.label: "none" for a in topology.apps}
    trace: dict[str, str] = {}
    rank = {"none": 0, "partial": 1, "full": 2}

    def bump(app_label: str, level: str, reason: str) -> None:
        if rank[level] > rank[evidence[app_label]]:
            evidence[app_label] = level
            trace[app_label] = reason

    for event in events:
        if event.get("entityType") not in _RELEVANT_TYPES:
            continue

        matched = None
        snapshot_id = event.get("snapshotId")
        if snapshot_id:
            matched = by_app.get(snapshot_id) or by_svc.get(snapshot_id) or by_ep.get(snapshot_id)
        if matched is None:
            for ident in _steady_ids(event):
                matched = by_app.get(ident) or by_svc.get(ident) or by_ep.get(ident)
                if matched is not None:
                    break

        level = "full" if event.get("type") == "issue" else "partial"
        problem = event.get("problem", "?")
        reason = (
            f"evento {event.get('eventId', '?')} {problem!r} "
            f"(tipo={event.get('type')}, enlace por ID)"
        )

        if matched is not None:
            bump(matched.label, level, reason)
            continue

        label = event.get("entityLabel")
        if label and label in labels:
            bump(
                label, "partial",
                f"evento {event.get('eventId', '?')} {problem!r} "
                "(sin ID de enlace, coincidencia exacta de entityLabel)",
            )

    return CollectorResult(evidence=evidence, trace=trace)
