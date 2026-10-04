"""
Dimension RUM/Mobile/Synthetic (peso 15).

CORRECCION 1 (sesion anterior): la parte "Synthetic" nunca se evaluaba.
rum_evidence() solo consultaba websites (RUM) y mobile apps -que en este
tenant dan 404-, sin llamar nunca a /api/synthetics/settings/tests. 11 de
53 tests traen 'applicationId' poblado: enlace formal, verificado.

CORRECCION 2 (esta sesion): el 'appName' de un website NO es un vinculo
real con una aplicacion backend. Se asumio que si lo era ("full") y era
falso: verificado contra las 34 webapps del tenant, appName == name del
propio website en el 100% de los casos, sin una sola excepcion. Es un
autoetiquetado interno de Instana, no una referencia cruzada a otro
modulo. Tratarlo como vinculo formal daba un falso "Si" cada vez que el
nombre de una webapp coincidia (por diseño o por casualidad) con el de
una Application Perspective real -exactamente el tipo de falso positivo
que este assessment existe para evitar.

El vinculo real entre una webapp y su backend en Instana es por
correlacion de trazas distribuidas (tag beacon.backend.correlationAttempted
en Unbounded Analytics de websites), no un campo estatico de config. No se
implementa aqui: consultarlo exige una llamada de analytics por website
(cara) y en el tenant de demo no hay trafico de beacon en absoluto en 30
dias para probarlo contra datos reales. Documentado como limitacion
conocida, no resuelto con un campo que parecia servir pero no servia.

Fuente de vinculo formal (da "full"), la unica que sobrevive verificada:
  - test sintetico con applicationId que apunta a la app (Synthetic)

Fallback por nombre (da "partial") para todo lo demas, incluido el
appName de website que antes se trataba como formal:
  - website/mobile app cuyo nombre solo se parece al de la app
  - test sintetico sin applicationId cuyo label solo se parece al de la app

Distinguirlos importa porque la recomendacion #1 del assessment es
precisamente normalizar el naming entre capacidades: una app que solo empata
por nombre no deberia puntuar igual que una formalmente vinculada.
"""
from __future__ import annotations

from ..instana_client import InstanaClient
from .match import find_match
from .result import CollectorResult
from .topology import Topology


def rum_evidence(client: InstanaClient, topology: Topology) -> CollectorResult:
    websites = client.list_websites()
    mobile_apps = client.list_mobile_apps()
    synthetic_tests = client.list_synthetic_tests()

    loose_names: list[str] = []

    for site in websites:
        # appName == name siempre (verificado, ver docstring): no aporta
        # mas certeza que el propio nombre del website. Va al pool de
        # coincidencia por nombre, nunca a "full".
        site_name = site.get("name") or site.get("appName") or site.get("label") or ""
        if site_name:
            loose_names.append(site_name)

    for m in mobile_apps:
        name = m.get("label") or m.get("name")
        if name:
            loose_names.append(name)

    # Tests sinteticos: separar los que traen applicationId (enlace formal,
    # verificado independiente -no es un autoetiquetado) de los que solo
    # tienen label (van al fallback por nombre).
    synthetic_by_app_id: dict[str, list[str]] = {}
    for test in synthetic_tests:
        app_ids: set[str] = set()
        if test.get("applicationId"):
            app_ids.add(test["applicationId"])
        for aid in test.get("applications") or []:
            if isinstance(aid, str):
                app_ids.add(aid)
        label = test.get("label") or ""
        if app_ids:
            for aid in app_ids:
                synthetic_by_app_id.setdefault(aid, []).append(label)
        elif label:
            loose_names.append(label)

    evidence: dict[str, str] = {}
    trace: dict[str, str] = {}
    for app in topology.apps:
        synth_labels = synthetic_by_app_id.get(app.id)
        if synth_labels:
            evidence[app.label] = "full"
            trace[app.label] = (
                f"test sintetico {synth_labels[0]!r} "
                f"(applicationId={app.id!r}, vinculo formal"
                + (f", +{len(synth_labels) - 1} mas" if len(synth_labels) > 1 else "")
                + ")"
            )
        else:
            m = find_match(app.label, loose_names)
            if m:
                evidence[app.label] = "partial"
                trace[app.label] = (
                    f"website/mobile {m!r} (solo coincidencia de nombre; "
                    "appName de website no cuenta como vinculo formal, ver docstring)"
                )
            else:
                evidence[app.label] = "none"
    return CollectorResult(evidence=evidence, trace=trace)
