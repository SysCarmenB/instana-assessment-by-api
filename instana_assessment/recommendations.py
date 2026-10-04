"""
Generador de recomendaciones deterministico (sin LLM) a partir del resultado de
scoring.py. Reglas simples y auditables: cada recomendacion es trazable a un
numero (pct_of_weight de una dimension, o conteo de apps en nivel bajo), igual
que el criterio "se puntua evidencia observable" de la hoja Metodologia.
"""
from __future__ import annotations

from dataclasses import dataclass

from .scoring import AssessmentResult

_DIMENSION_TEMPLATES: dict[str, dict[str, str]] = {
    "rum": {
        "recommendation": "Extender RUM/Mobile/Synthetic al resto de aplicaciones evaluadas",
        "justification": "Solo el {pct:.0f}% del peso de RUM/Mobile/Synthetic esta evidenciado en promedio",
        "impact": "Visibilidad de experiencia de usuario end-to-end",
    },
    "slo": {
        "recommendation": "Definir SLO/Apdex en las aplicaciones criticas sin cobertura",
        "justification": "Solo el {pct:.0f}% del peso de SLO/Apdex esta evidenciado en promedio",
        "impact": "Evolucion hacia gestion por confiabilidad",
    },
    "alerts": {
        "recommendation": "Revisar cobertura y accionabilidad de Smart Alerts por aplicacion",
        "justification": "Solo el {pct:.0f}% del peso de Smart Alerts esta evidenciado en promedio",
        "impact": "Menos ruido, alertas con valor operativo real",
    },
    "dashboard": {
        "recommendation": "Formalizar dashboards productivos con owner y proposito claro",
        "justification": "Solo el {pct:.0f}% del peso de Dashboard esta evidenciado en promedio",
        "impact": "Mayor adopcion y gobernanza de los dashboards existentes",
    },
    "infra": {
        "recommendation": "Completar tagging/zonificacion de infraestructura por aplicacion",
        "justification": "Solo el {pct:.0f}% del peso de Infraestructura esta evidenciado en promedio",
        "impact": "Mejor correlacion entre infraestructura y aplicaciones",
    },
    "events": {
        "recommendation": "Habilitar diagnostico de eventos/incidentes por aplicacion",
        "justification": "Solo el {pct:.0f}% del peso de Eventos/Diagnostico esta evidenciado en promedio",
        "impact": "Investigacion de incidentes mas rapida",
    },
    "governance": {
        "recommendation": "Definir owner, team y runbook por aplicacion critica",
        "justification": "Solo el {pct:.0f}% del peso de Gobierno esta evidenciado en promedio",
        "impact": "Mayor accionabilidad y soporte operativo",
    },
    "apm": {
        "recommendation": "Revisar la cobertura APM del set de aplicaciones evaluadas",
        "justification": "Solo el {pct:.0f}% del peso de APM esta evidenciado en promedio",
        "impact": "Base de observabilidad tecnica consistente",
    },
}


@dataclass
class Recommendation:
    priority: str
    recommendation: str
    justification: str
    impact: str


def _priority_for_pct(pct: float) -> str | None:
    if pct < 45:
        return "Alta"
    if pct < 70:
        return "Media"
    return None  # Fuerte: no se genera recomendacion


def build_recommendations(result: AssessmentResult) -> list[Recommendation]:
    recs: list[Recommendation] = []

    for dim in result.dimension_summary:
        priority = _priority_for_pct(dim["pct_of_weight"])
        if priority is None:
            continue
        template = _DIMENSION_TEMPLATES.get(dim["key"])
        if not template:
            continue
        recs.append(
            Recommendation(
                priority=priority,
                recommendation=template["recommendation"],
                justification=template["justification"].format(pct=dim["pct_of_weight"]),
                impact=template["impact"],
            )
        )

    low_level_apps = [
        a.app_name for a in result.app_scores if a.level["level"] <= 2
    ]
    if low_level_apps:
        sample = ", ".join(low_level_apps[:5])
        more = f" (+{len(low_level_apps) - 5} mas)" if len(low_level_apps) > 5 else ""
        recs.append(
            Recommendation(
                priority="Alta",
                recommendation="Priorizar mejora de observabilidad en apps de nivel 1-2",
                justification=f"{len(low_level_apps)} aplicaciones estan en nivel 1-2: {sample}{more}",
                impact="Reduccion de riesgo operativo en el segmento mas rezagado",
            )
        )

    order = {"Alta": 0, "Media": 1, "Baja": 2}
    recs.sort(key=lambda r: order.get(r.priority, 3))
    return recs
