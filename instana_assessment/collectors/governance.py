"""
Dimension Gobierno (peso 5).

El README original afirmaba que esta dimension es 100% manual porque no vive en
Instana. Es parcialmente incorrecto: parte si vive en Instana.

  - Runbooks -> Automation Actions (/api/automation/actions, verificado).
    El catalogo existe (93 acciones en el tenant de demo) y se puede cruzar
    por aplicacion.
  - Owner/team -> los custom dashboards traen ownerId.

Lo que si queda fuera de Instana es la integracion con ITSM y la formalizacion
del ownership, que se siguen leyendo del CSV manual.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .match import find_match
from .result import CollectorResult
from .topology import Topology


def governance_evidence(
    topology: Topology,
    csv_path: str,
    dashboard_owners: dict[str, str] | None = None,
    automation_actions: list[dict] | None = None,
) -> CollectorResult:
    """
    Suma senales. Con 2 o mas -> full, con 1 -> partial, con 0 -> none.

    Senales posibles por aplicacion:
      - owner declarado en el CSV manual
      - team declarado en el CSV manual
      - runbook (CSV manual, o accion de automatizacion que la referencia)
      - ITSM integrado (CSV manual)
      - ownerId de un dashboard asociado a la app
    """
    rows_by_app: dict[str, dict[str, str]] = {}
    path = Path(csv_path)
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows_by_app[row["app_name"]] = row

    dashboard_owners = dashboard_owners or {}
    action_names = [
        a.get("name", "") for a in (automation_actions or []) if a.get("name")
    ]

    evidence: dict[str, str] = {}
    trace: dict[str, str] = {}
    for app in topology.apps:
        signals: list[str] = []
        row = rows_by_app.get(app.label, {})

        for field in ("owner", "team"):
            if row.get(field, "").strip():
                signals.append(f"{field}={row[field].strip()!r} (CSV)")
        for field in ("runbook", "itsm_integrated"):
            if row.get(field, "").strip().lower() in ("si", "sí", "yes"):
                signals.append(f"{field}=si (CSV)")

        if app.label in dashboard_owners:
            signals.append(f"ownerId={dashboard_owners[app.label]!r} (dashboard)")

        matched_action = find_match(app.label, action_names) if action_names else None
        if matched_action:
            signals.append(f"accion de automatizacion {matched_action!r}")

        if len(signals) >= 2:
            evidence[app.label] = "full"
        elif len(signals) == 1:
            evidence[app.label] = "partial"
        else:
            evidence[app.label] = "none"
        trace[app.label] = "; ".join(signals) if signals else "sin señales"

    return CollectorResult(evidence=evidence, trace=trace)
