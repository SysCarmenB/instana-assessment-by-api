from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml

from .csv_export import write_csv
from .instana_client import InstanaAuthError, InstanaClient
from .recommendations import build_recommendations
from .report import build_html
from .scoring import Rubric, score_assessment


def _load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_evidence_csv(path: str) -> dict[str, dict[str, str]]:
    """
    Lee un CSV de evidencia ya calificada a mano (columnas: app_name,apm,rum,slo,
    alerts,dashboard,infra,events,governance con valores Si/Parcial/No). Util para
    validar el pipeline de scoring/reporte sin conectarse a Instana, o para
    digitalizar un assessment manual existente.
    """
    label_to_key = {"si": "full", "sí": "full", "parcial": "partial", "no": "none"}
    evidence: dict[str, dict[str, str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            app_name = row["app_name"]
            dims = {
                k: label_to_key.get(v.strip().lower(), "none")
                for k, v in row.items()
                if k != "app_name"
            }
            evidence[app_name] = dims
    return evidence


def _read_evidence_live(
    config: dict,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    from .collectors import collect_all

    client = InstanaClient.from_config(config["instana"])
    return collect_all(client, config)


def run(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    rubric = Rubric.load(config.get("rubric_path", "config/rubric.yaml"))

    trace_by_app: dict[str, dict[str, str]] = {}
    if args.source == "csv":
        if not args.input:
            print("--input es requerido cuando --source csv", file=sys.stderr)
            return 2
        evidence_by_app = _read_evidence_csv(args.input)
        source_label = f"CSV manual ({args.input})"
    else:
        try:
            evidence_by_app, trace_by_app = _read_evidence_live(config)
        except InstanaAuthError as e:
            print(f"Error de autenticacion con Instana: {e}", file=sys.stderr)
            return 1
        source_label = f"Instana API ({config['instana']['base_url']})"

    if not evidence_by_app:
        print("No se obtuvo evidencia de ninguna aplicacion. Revisar filtro/config.", file=sys.stderr)
        return 1

    result = score_assessment(evidence_by_app, rubric)
    recommendations = build_recommendations(result)

    # Timestamp para evitar sobreescribir entre ejecuciones: YYYYMMDD_HHMMSS
    import datetime as _dt
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    def _stamped(path: Path) -> Path:
        """Inserta el timestamp antes de la extension: report.html -> report_20250101_120000.html"""
        return path.with_stem(f"{path.stem}_{ts}")

    base_html = Path(args.out or config.get("output", {}).get("html_path", "out/report.html"))
    out_path = _stamped(base_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    html_content = build_html(
        result=result,
        recommendations=recommendations,
        rubric=rubric,
        client_name=config.get("client_name", "Cliente"),
        source_label=source_label,
        trace_by_app=trace_by_app,
    )
    out_path.write_text(html_content, encoding="utf-8")
    print(f"Reporte HTML generado: {out_path.resolve()}")

    # CSV — ruta explícita (se le añade timestamp igual) o derivada del HTML
    csv_path = _stamped(Path(args.csv)) if args.csv else out_path.with_suffix(".csv")
    write_csv(result, rubric, csv_path, trace_by_app=trace_by_app)
    print(f"Reporte CSV generado:  {csv_path.resolve()}")

    print(f"Apps evaluadas: {len(result.app_scores)} | Score promedio: {result.average_score} | Nivel estimado: {result.estimated_level['level']}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assessment de madurez en observabilidad Instana."
    )
    parser.add_argument(
        "--config", default="config/client.yaml",
        help="Path al config del cliente (ver config/client.example.yaml)",
    )
    parser.add_argument(
        "--source", choices=["csv", "live"], default="csv",
        help="csv = evidencia pre-calificada en un CSV; live = consulta la API de Instana",
    )
    parser.add_argument(
        "--input", help="Path al CSV de evidencia (requerido si --source csv)",
    )
    parser.add_argument(
        "--out", help="Path de salida del HTML (por defecto: output.html_path del config)",
    )
    parser.add_argument(
        "--csv", help="Path de salida del CSV (por defecto: mismo nombre que --out con extension .csv)",
    )
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
