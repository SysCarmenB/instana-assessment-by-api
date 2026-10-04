"""
Prueba cada endpoint de instana_client.py contra un tenant real y reporta,
por endpoint: si respondio OK, cuantos items trajo, y las claves (keys) del
primer item -- sin imprimir valores completos, para no volcar datos del
cliente en la salida.

Uso:
    set INSTANA_API_TOKEN=...          (PowerShell: $env:INSTANA_API_TOKEN="...")
    python scripts/smoke_test.py --config config/client.yaml
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from instana_assessment.instana_client import InstanaAuthError, InstanaClient


def describe(label: str, items) -> None:
    if items is None:
        print(f"[{label}] -> SIN DATOS: revisar el [WARN] de arriba "
              "(permiso faltante del token o endpoint ausente en este tenant)")
        return
    if isinstance(items, dict):
        print(f"[{label}] -> OK, objeto con claves: {sorted(items.keys())}")
        return
    if not isinstance(items, list):
        print(f"[{label}] -> respuesta inesperada: {type(items)}")
        return
    print(f"[{label}] -> OK, {len(items)} items")
    if items and isinstance(items[0], dict):
        print(f"    keys del primer item: {sorted(items[0].keys())}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/client.yaml")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    try:
        client = InstanaClient.from_config(config["instana"])
    except InstanaAuthError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Los metodos del cliente convierten un error (403, 404...) en lista vacia,
    # lo que se veria como "OK, 0 items". Se registran las llamadas que
    # devolvieron None para poder distinguir "no hay datos" de "no se pudo leer".
    failed_paths: list[str] = []
    original_get = client._get

    def tracking_get(path, params=None, quiet_404=False):
        result = original_get(path, params=params, quiet_404=quiet_404)
        if result is None:
            failed_paths.append(path)
        return result

    client._get = tracking_get  # type: ignore[method-assign]

    checks = [
        ("applications", client.list_applications),
        ("websites", client.list_websites),
        ("mobile_apps", client.list_mobile_apps),
        ("slo_configs", client.list_slo_configs),
        ("application_alert_configs", client.list_application_alert_configs),
        ("website_alert_configs", client.list_website_alert_configs),
        ("custom_dashboards", client.list_custom_dashboards),
        ("synthetic_tests (requiere canViewSyntheticTests)", client.list_synthetic_tests),
        ("automation_actions", client.list_automation_actions),
        ("infra monitoring_state", client.monitoring_state),
    ]

    for label, fn in checks:
        try:
            failed_paths.clear()
            result = fn()
            if failed_paths:
                print(f"[{label}] -> SIN DATOS: no se pudo leer {failed_paths[0]} "
                      "(permiso faltante del token o modulo ausente; ver [WARN] arriba si existe)")
                continue
            describe(label, result)
        except Exception as e:  # noqa: BLE001 - smoke test, queremos ver todos los fallos
            print(f"[{label}] -> ERROR: {type(e).__name__}: {e}")

    try:
        now_ms = int(time.time() * 1000)
        events = client.list_events(now_ms - 7 * 24 * 60 * 60 * 1000, now_ms)
        describe("events (7 dias)", events)
    except Exception as e:  # noqa: BLE001
        print(f"[events] -> ERROR: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
