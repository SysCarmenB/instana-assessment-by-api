"""
Genera un reporte HTML autocontenido (CSS inline, sin dependencias externas de
JS/CDN) a partir del resultado de scoring.py y recommendations.py. Sin Jinja2 a
proposito: mantiene el set de dependencias minimo (requests + pyyaml) para que
sea facil de correr localmente.
"""
from __future__ import annotations

import datetime
import html
from typing import Any

from .recommendations import Recommendation
from .scoring import AssessmentResult, Rubric

_PRIORITY_COLOR = {"Alta": "#c0392b", "Media": "#b7791f", "Baja": "#2f6f4e"}
_READING_COLOR = {"Fuerte": "#2f6f4e", "Media": "#b7791f", "Baja": "#c0392b"}


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _bar(pct: float, color: str = "#2c5f8a") -> str:
    pct = max(0.0, min(100.0, pct))
    return (
        f'<div class="bar-track"><div class="bar-fill" '
        f'style="width:{pct:.0f}%;background:{color};"></div></div>'
    )


def _executive_reading(result: AssessmentResult, rubric: Rubric) -> str:
    strongest = max(result.dimension_summary, key=lambda d: d["pct_of_weight"])
    weakest = min(result.dimension_summary, key=lambda d: d["pct_of_weight"])
    return (
        f"Fuerte en {strongest['name']} ({strongest['pct_of_weight']:.0f}%), "
        f"con la brecha principal en {weakest['name']} ({weakest['pct_of_weight']:.0f}%)."
    )


def build_html(
    result: AssessmentResult,
    recommendations: list[Recommendation],
    rubric: Rubric,
    client_name: str,
    source_label: str,
    trace_by_app: dict[str, dict[str, str]] | None = None,
) -> str:
    trace_by_app = trace_by_app or {}
    has_trace = any(trace_by_app.values())
    today = datetime.date.today().isoformat()
    n_apps = len(result.app_scores)

    dim_rows = "\n".join(
        f"<tr><td>{_esc(d['name'])}</td><td>{d['weight']}</td>"
        f"<td>{d['avg_score']:.1f}</td>"
        f"<td>{_bar(d['pct_of_weight'])}</td>"
        f"<td>{d['pct_of_weight']:.0f}%</td>"
        f"<td><span class=\"pill\" style=\"background:{_READING_COLOR.get(d['reading'], '#666')}\">"
        f"{_esc(d['reading'])}</span></td></tr>"
        for d in result.dimension_summary
    )

    level_rows = "\n".join(
        f"<tr><td>Nivel {lvl}</td><td>{count}</td></tr>"
        for lvl, count in sorted(result.level_distribution.items())
    )

    app_rows = []
    dim_keys = [d["key"] for d in rubric.dimensions]
    for a in result.app_scores:
        app_trace = trace_by_app.get(a.app_name, {})
        cells = []
        for k in dim_keys:
            score_text = f"{a.dimension_scores.get(k, 0):.0f}"
            reason = app_trace.get(k)
            if reason:
                cells.append(f'<td class="has-trace" title="{_esc(reason)}">{score_text}</td>')
            else:
                cells.append(f"<td>{score_text}</td>")
        app_rows.append(
            f"<tr><td>{_esc(a.app_name)}</td>{''.join(cells)}"
            f"<td><b>{a.total_score:.0f}</b></td>"
            f"<td><span class=\"pill\" style=\"background:#2c5f8a\">Nivel {a.level['level']}</span></td>"
            f"<td>{_esc(a.top_gap)}</td></tr>"
        )
    app_rows_html = "\n".join(app_rows)
    dim_headers = "".join(f"<th>{_esc(d['name'])}</th>" for d in rubric.dimensions)
    trace_note = (
        '<p class="note">Las celdas subrayadas de la tabla de scoring tienen '
        "evidencia: pase el cursor sobre el numero para ver que objeto de "
        "Instana (SLO, alerta, dashboard, evento...) sustenta ese veredicto.</p>"
        if has_trace
        else ""
    )

    rec_rows = "\n".join(
        f"<tr><td><span class=\"pill\" style=\"background:{_PRIORITY_COLOR.get(r.priority, '#666')}\">"
        f"{_esc(r.priority)}</span></td>"
        f"<td>{_esc(r.recommendation)}</td>"
        f"<td>{_esc(r.justification)}</td>"
        f"<td>{_esc(r.impact)}</td></tr>"
        for r in recommendations
    )

    method_rows = "\n".join(
        f"<tr><td>{_esc(d['name'])}</td><td>{d['weight']}</td>"
        f"<td>{_esc(d['evidence'])}</td>"
        f"<td>{_esc('API Instana' if d['source'] == 'instana_api' else 'Manual (CSV)')}</td></tr>"
        for d in rubric.dimensions
    )

    _src_label = {"instana_api": "API Instana", "manual": "Manual (CSV)", "hibrido": "Hibrido (API + CSV)"}
    _src_color = {"instana_api": "#2c5f8a", "manual": "#666", "hibrido": "#b7791f"}
    scope_rows = "\n".join(
        f"<tr><td>{_esc(d['name'])}</td>"
        f"<td><span class=\"pill\" style=\"background:{_src_color.get(d.get('source'), '#666')}\">"
        f"{_esc(_src_label.get(d.get('source'), d.get('source', '')))}</span></td>"
        f"<td>{_esc(d.get('criteria', {}).get('full', '—'))}</td>"
        f"<td>{_esc(d.get('criteria', {}).get('partial', '—'))}</td>"
        f"<td>{_esc(d.get('criteria', {}).get('none', '—'))}</td></tr>"
        for d in rubric.dimensions
    )

    level_def_rows = "\n".join(
        f"<tr><td>Nivel {lvl['level']}</td><td>{_esc(lvl['name'])}</td>"
        f"<td>{_esc(lvl['definition'].strip())}</td></tr>"
        for lvl in rubric.levels
    )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Assessment de Instana - {_esc(client_name)}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; margin: 0; padding: 32px;
         color: #1a1a1a; background: #f7f8fa; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  h2 {{ font-size: 17px; margin-top: 36px; border-bottom: 2px solid #e2e5e9; padding-bottom: 6px; }}
  .subtitle {{ color: #555; margin-bottom: 24px; }}
  .kpis {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0 28px; }}
  .kpi {{ background: #fff; border: 1px solid #e2e5e9; border-radius: 8px; padding: 14px 20px; min-width: 160px; }}
  .kpi .label {{ font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: .03em; }}
  .kpi .value {{ font-size: 24px; font-weight: 600; margin-top: 4px; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 13px; }}
  th, td {{ border: 1px solid #e2e5e9; padding: 6px 10px; text-align: left; vertical-align: middle; }}
  th {{ background: #eef1f5; font-weight: 600; }}
  .pill {{ color: #fff; padding: 2px 9px; border-radius: 10px; font-size: 12px; white-space: nowrap; }}
  .bar-track {{ background: #e2e5e9; border-radius: 4px; height: 10px; width: 120px; }}
  .bar-fill {{ height: 10px; border-radius: 4px; }}
  .table-wrap {{ overflow-x: auto; }}
  .note {{ color: #666; font-size: 12px; margin-top: 8px; }}
  td.has-trace {{ text-decoration: underline dotted #999; text-underline-offset: 3px; cursor: help; }}
</style>
</head>
<body>
  <h1>Assessment de Instana</h1>
  <div class="subtitle">{_esc(client_name)} &middot; corte {today} &middot; fuente de datos: {_esc(source_label)} &middot; {n_apps} aplicaciones evaluadas</div>

  <div class="kpis">
    <div class="kpi"><div class="label">Score promedio</div><div class="value">{result.average_score:.1f}</div></div>
    <div class="kpi"><div class="label">Nivel estimado</div><div class="value">Nivel {result.estimated_level['level']}</div></div>
    <div class="kpi"><div class="label">Score max / min</div><div class="value">{result.max_score:.0f} / {result.min_score:.0f}</div></div>
    <div class="kpi"><div class="label">Lectura ejecutiva</div><div class="value" style="font-size:13px;font-weight:400;">{_esc(_executive_reading(result, rubric))}</div></div>
  </div>

  <h2>Score por dimension</h2>
  <div class="table-wrap"><table>
    <tr><th>Dimension</th><th>Peso</th><th>Promedio obtenido</th><th></th><th>% sobre peso</th><th>Lectura</th></tr>
    {dim_rows}
  </table></div>

  <h2>Distribucion por nivel</h2>
  <div class="table-wrap"><table>
    <tr><th>Nivel</th><th>Cantidad de apps</th></tr>
    {level_rows}
  </table></div>

  <h2>Scoring por aplicacion</h2>
  {trace_note}
  <div class="table-wrap"><table>
    <tr><th>Aplicacion</th>{dim_headers}<th>Score</th><th>Nivel</th><th>Brecha principal</th></tr>
    {app_rows_html}
  </table></div>

  <h2>Recomendaciones</h2>
  <div class="table-wrap"><table>
    <tr><th>Prioridad</th><th>Recomendacion</th><th>Justificacion</th><th>Impacto esperado</th></tr>
    {rec_rows}
  </table></div>

  <h2>Metodologia</h2>
  <div class="table-wrap"><table>
    <tr><th>Dimension</th><th>Peso</th><th>Criterio de evidencia</th><th>Fuente</th></tr>
    {method_rows}
  </table></div>
  <p class="note">Principio de scoring: se puntua evidencia observable en la herramienta, no capacidades declaradas pero no evidenciadas.
  Multiplicadores: Si = 100% del peso, Parcial = 50%, No evidenciado = 0%.</p>

  <h2>Alcance por dimension</h2>
  <div class="table-wrap"><table>
    <tr><th>Dimension</th><th>Fuente</th><th>Si (evidencia completa)</th><th>Parcial</th><th>No evidenciado</th></tr>
    {scope_rows}
  </table></div>
  <p class="note">Regla que se repite en casi todas las dimensiones: un vinculo por ID (aplicacion,
  servicio o endpoint) da "Si". Un vinculo solo por coincidencia de nombre nunca pasa de "Parcial"
  -el nombre no es una fuente fiable (ver Recomendaciones del assessment manual, brecha #1: naming
  no normalizado entre capacidades de Instana).</p>

  <h2>Niveles de madurez</h2>
  <div class="table-wrap"><table>
    <tr><th>Nivel</th><th>Nombre</th><th>Definicion</th></tr>
    {level_def_rows}
  </table></div>

</body>
</html>
"""
