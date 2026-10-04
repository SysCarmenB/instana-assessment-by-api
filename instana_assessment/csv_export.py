"""
Exporta el resultado del assessment a CSV con el mismo formato de columnas
que la hoja 'Scoring Top 20 PROD' del Excel manual (Assessment Madurez Instana.xlsx),
mas un bloque de columnas de detalle al final (no en el Excel original).

Columnas generadas:
  N°, Aplicación/flujo, Entidad APM,
  Web/Mobile/Synthetic, SLO/Apdex (ev.), Smart Alerts (ev.), Dashboard (ev.), Infra (ev.),
  APM, RUM/Mobile, SLO/Apdex score, Alertas, Dashboard score, Infra score, Eventos, Gobierno,
  Score, Nivel, Brecha principal,
  Detalle: APM, Detalle: RUM/Mobile/Synthetic, Detalle: SLO/Apdex, Detalle: Smart Alerts,
  Detalle: Dashboard, Detalle: Infraestructura, Detalle: Eventos/Diagnostico, Detalle: Gobierno

El bloque "Detalle: *" nombra el objeto real de Instana que sustenta el
veredicto de cada dimension -el SLO, la alerta, el dashboard, el test
sintetico...- en vez de solo Si/Parcial/No. Se agrega AL FINAL, sin tocar
ni reordenar las columnas que replican el Excel, para no romper nada que ya
dependa de esas posiciones.

Solo se completa en modo --source live (viene de trace_by_app, ver
collectors/result.py). En modo --source csv (Excel digitalizado a mano)
queda vacio: esa evidencia nunca tuvo el detalle de origen.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .scoring import AssessmentResult, Rubric

# Mapeo evidencia interna -> etiqueta legible (igual que el Excel)
_EVIDENCE_LABEL: dict[str, str] = {
    "full":    "Si",
    "partial": "Parcial",
    "none":    "No evidenciado",
}

# Orden de dimensiones tal como aparece en el Excel (columnas de evidencia cualitativa)
_EVIDENCE_COLS: list[tuple[str, str]] = [
    # (dim_key,   cabecera_excel)
    ("rum",        "Web/Mobile/Synthetic"),
    ("slo",        "SLO/Apdex (ev.)"),
    ("alerts",     "Smart Alerts (ev.)"),
    ("dashboard",  "Dashboard (ev.)"),
    ("infra",      "Infra (ev.)"),
]

# Orden de dimensiones tal como aparece en el Excel (columnas de score numérico)
_SCORE_COLS: list[tuple[str, str]] = [
    # (dim_key,   cabecera_excel)
    ("apm",        "APM"),
    ("rum",        "RUM/Mobile"),
    ("slo",        "SLO/Apdex score"),
    ("alerts",     "Alertas"),
    ("dashboard",  "Dashboard score"),
    ("infra",      "Infra score"),
    ("events",     "Eventos"),
    ("governance", "Gobierno"),
]


def write_csv(
    result: AssessmentResult,
    rubric: Rubric,
    out_path: str | Path,
    trace_by_app: dict[str, dict[str, str]] | None = None,
) -> None:
    """Escribe el CSV de scoring por aplicacion en out_path.

    trace_by_app: { app_name: { dim_key: "detalle legible" } }. Opcional -
    en modo --source csv no existe y las columnas "Detalle: *" quedan vacias.
    """
    trace_by_app = trace_by_app or {}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Orden y nombres de las columnas de detalle: se toman de rubric.yaml
    # (mismo orden que la dimension_scores/evidence), no se duplican aqui.
    detail_cols = [(d["key"], f"Detalle: {d['name']}") for d in rubric.dimensions]

    # Cabeceras: igual al Excel + bloque de detalle al final
    headers = (
        ["N°", "Aplicación/flujo", "Entidad APM"]
        + [col for _, col in _EVIDENCE_COLS]
        + [col for _, col in _SCORE_COLS]
        + ["Score", "Nivel", "Brecha principal"]
        + [col for _, col in detail_cols]
    )

    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for i, app in enumerate(result.app_scores, start=1):
            # Evidencia cualitativa
            ev_cells = [
                _EVIDENCE_LABEL.get(app.evidence.get(key, "none"), "No evidenciado")
                for key, _ in _EVIDENCE_COLS
            ]
            # Scores numericos por dimension
            score_cells = [
                f"{app.dimension_scores.get(key, 0):.0f}"
                for key, _ in _SCORE_COLS
            ]
            # Detalle: objeto real de Instana que sustenta cada veredicto
            app_trace = trace_by_app.get(app.app_name, {})
            detail_cells = [app_trace.get(key, "") for key, _ in detail_cols]

            writer.writerow(
                [i, app.app_name, app.app_name]   # Entidad APM = label de la app
                + ev_cells
                + score_cells
                + [f"{app.total_score:.0f}", app.level["level"], app.top_gap]
                + detail_cells
            )
