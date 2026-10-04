"""
Dimension Dashboard (peso 10).

Dos correcciones sobre el colector original:

1. Endpoint. /api/custom-dashboards da 404; el correcto es
   /api/custom-dashboard, en SINGULAR. Por eso la dimension puntuaba 0 en las
   50 apps del tenant, cuando en realidad hay 11 dashboards.

2. Evidencia. El titulo de un dashboard no prueba nada. Lo que prueba
   asociacion son los filtros de sus widgets: cada widget lleva un
   tagFilterExpression con elementos application.name / service.name /
   endpoint.name. Eso es evidencia dura.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..instana_client import InstanaClient
from .match import find_match
from .topology import Topology

_ENTITY_TAGS = ("application.name", "service.name", "endpoint.name")


@dataclass
class DashboardResult:
    evidence: dict[str, str]
    # app_label -> ownerId del dashboard que la referencia. Lo reutiliza
    # governance.py; se devuelve explicito en vez de como atributo mutable
    # de la funcion para que el orden de llamada no importe.
    owners_by_app: dict[str, str] = field(default_factory=dict)
    trace: dict[str, str] = field(default_factory=dict)


def _collect_filter_values(node: Any, out: dict[str, set[str]]) -> None:
    """Recorre un tagFilterExpression (anidado) y junta los valores por tag."""
    if isinstance(node, dict):
        name = node.get("name")
        value = node.get("value")
        if name in _ENTITY_TAGS and isinstance(value, str):
            out.setdefault(name, set()).add(value)
        for val in node.values():
            _collect_filter_values(val, out)
    elif isinstance(node, list):
        for item in node:
            _collect_filter_values(item, out)


def dashboards_evidence(client: InstanaClient, topology: Topology) -> DashboardResult:
    """
    full     -> algun widget filtra explicitamente por esta aplicacion
                (o por uno de sus servicios)
    partial  -> solo coincide el titulo del dashboard
    none     -> ningun dashboard la referencia

    LIMITACION CONOCIDA: el matching (por ID de widget o por titulo) exige
    la MISMA cadena. Una app llamada "Aplicacion X" no enlaza con un
    dashboard llamado "Aplicaciones de X" pese a ser, con alta
    probabilidad, la misma aplicacion: son nombres distintos entre modulos
    de Instana. Es un caso real de la brecha #1 del assessment manual
    (naming no normalizado). No se afloja el matcher para cubrir este caso:
    hacerlo mas permisivo introduce falsos positivos de peor calidad
    (ver docstring de match.py, caso "SAS"). Queda como falso negativo
    aceptado, documentado en vez de escondido.
    """
    listing = client.list_custom_dashboards()

    app_names_in_widgets: set[str] = set()
    service_names_in_widgets: set[str] = set()
    titles: list[str] = []
    owners_by_value: dict[str, str] = {}
    # value (application.name / service.name / titulo) -> id del dashboard,
    # solo para poder citarlo en el trace.
    source_dash_by_value: dict[str, str] = {}
    title_by_id: dict[str, str] = {}

    for entry in listing:
        title = entry.get("title") or entry.get("name") or ""
        dash_id = entry.get("id") or ""
        if title:
            titles.append(title)
            if dash_id:
                title_by_id[title] = dash_id
        if not dash_id:
            continue
        full = client.get_custom_dashboard(dash_id)
        if not full:
            continue
        found: dict[str, set[str]] = {}
        _collect_filter_values(full.get("widgets"), found)
        for value in found.get("application.name", set()):
            app_names_in_widgets.add(value)
            source_dash_by_value.setdefault(value, dash_id)
            if full.get("ownerId"):
                owners_by_value.setdefault(value, full["ownerId"])
        for value in found.get("service.name", set()):
            service_names_in_widgets.add(value)
            source_dash_by_value.setdefault(value, dash_id)

    evidence: dict[str, str] = {}
    trace: dict[str, str] = {}
    for app in topology.apps:
        if app.label in app_names_in_widgets:
            evidence[app.label] = "full"
            trace[app.label] = (
                f"dashboard {source_dash_by_value.get(app.label, '?')} "
                f"(widget filtra por application.name={app.label!r})"
            )
        elif app.service_labels & service_names_in_widgets:
            evidence[app.label] = "full"
            matched_svc = next(iter(app.service_labels & service_names_in_widgets))
            trace[app.label] = (
                f"dashboard {source_dash_by_value.get(matched_svc, '?')} "
                f"(widget filtra por service.name={matched_svc!r})"
            )
        else:
            m = find_match(app.label, titles)
            if m:
                evidence[app.label] = "partial"
                trace[app.label] = (
                    f"dashboard {title_by_id.get(m, '?')} titulado {m!r} "
                    "(solo coincidencia de nombre, sin filtro en el widget)"
                )
            else:
                evidence[app.label] = "none"
    return DashboardResult(evidence=evidence, owners_by_app=owners_by_value, trace=trace)
