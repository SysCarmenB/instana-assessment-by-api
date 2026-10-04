"""
Wrapper delgado sobre la REST API de Instana.

Endpoints verificados uno por uno contra un tenant SaaS de pruebas
(2026-09-15). Las lineas marcadas CORREGIDO son las que antes apuntaban a una
URL o parametro equivocado y devolvian 404/400, lo que anulaba en silencio
dimensiones completas del assessment:

  OK        GET /api/application-monitoring/applications
  OK        GET /api/application-monitoring/applications;id=<id>/services
  OK        GET /api/application-monitoring/applications;id=<id>/services/endpoints
  OK        GET /api/website-monitoring/config
  OK        GET /api/settings/slo
  OK        GET /api/events
  CORREGIDO GET /api/custom-dashboard                 (antes /api/custom-dashboards -> 404)
  CORREGIDO GET /api/events/settings/application-alert-configs
                                                      (antes /api/application-alert-configs -> 404)
  CORREGIDO GET /api/infrastructure-monitoring/snapshots?query=...
                                                      (antes ?q= vacio -> 400)
  N/D       GET /api/mobile-app-monitoring/apps       -> 404 real en este tenant
  N/D       GET /api/synthetics/settings/tests        -> 403, el token no tiene permiso
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests


class InstanaAuthError(RuntimeError):
    pass


class InstanaClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout_seconds: int = 30,
        verify_ssl: bool = True,
    ) -> None:
        if not api_token:
            raise InstanaAuthError(
                "Falta el API token de Instana. Configuralo en la variable de entorno "
                "indicada por 'instana.api_token_env' en el config del cliente."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"apiToken {api_token}",
                "Accept": "application/json",
            }
        )
        self.verify_ssl = verify_ssl
        self.call_count = 0

    @classmethod
    def from_config(cls, instana_cfg: dict[str, Any]) -> "InstanaClient":
        token_env = instana_cfg["api_token_env"]
        token = os.environ.get(token_env, "")
        return cls(
            base_url=instana_cfg["base_url"],
            api_token=token,
            timeout_seconds=instana_cfg.get("timeout_seconds", 30),
            verify_ssl=instana_cfg.get("verify_ssl", True),
        )

    # --- helpers internos --------------------------------------------------

    @staticmethod
    def _normalize_list(
        data: Any,
        *,
        wrapper_keys: tuple[str, ...] = (
            "items", "applications", "websites", "mobileApps",
            "slos", "alerts", "dashboards", "snapshots", "events",
        ),
        str_label_key: str = "label",
    ) -> list[dict[str, Any]]:
        """Normaliza cualquier respuesta de la API a lista de dicts."""
        if not data:
            return []
        if isinstance(data, dict):
            for key in wrapper_keys:
                if key in data:
                    data = data[key]
                    break
            else:
                return [data]
        if not isinstance(data, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, str):
                normalized.append({str_label_key: item})
            elif isinstance(item, dict):
                normalized.append(item)
        return normalized

    def _respect_rate_limit(self, resp: requests.Response) -> None:
        """La API expone X-RateLimit-Remaining / -Reset. Esperar en vez de fallar."""
        try:
            remaining = int(resp.headers.get("X-RateLimit-Remaining", "9999"))
        except ValueError:
            return
        if remaining > 20:
            return
        try:
            reset_epoch = int(resp.headers.get("X-RateLimit-Reset", "0"))
        except ValueError:
            return
        wait = max(0, min(60, reset_epoch - int(time.time())))
        if wait:
            print(f"  [RATE] quedan {remaining} llamadas; esperando {wait}s")
            time.sleep(wait)

    def _get(self, path: str, params: dict[str, Any] | None = None,
             quiet_404: bool = False) -> Any:
        url = f"{self.base_url}{path}"
        self.call_count += 1
        resp = self.session.get(
            url, params=params, timeout=self.timeout_seconds, verify=self.verify_ssl
        )
        self._respect_rate_limit(resp)
        if resp.status_code == 401:
            raise InstanaAuthError(f"Instana respondio 401 (token invalido/expirado) en {path}")
        if resp.status_code == 404 and quiet_404:
            return None
        if not resp.ok:
            print(f"  [WARN] {path} -> HTTP {resp.status_code} (dimension omitida)")
            return None
        if not resp.content:
            return None
        return resp.json()

    def _get_paginated(self, path: str, params: dict[str, Any] | None = None,
                       page_size: int = 200, max_pages: int = 50) -> list[dict[str, Any]]:
        """
        Recorre todas las paginas de un endpoint con wrapper {items, page, totalHits}.
        El colector anterior leia solo la primera pagina: en un tenant con cientos
        de objetos eso descarta datos en silencio.
        """
        out: list[dict[str, Any]] = []
        page = 1
        while page <= max_pages:
            p = dict(params or {})
            p.update({"page": page, "pageSize": page_size})
            data = self._get(path, params=p)
            if data is None:
                break
            items = self._normalize_list(data)
            out.extend(items)
            if not isinstance(data, dict):
                break
            total = data.get("totalHits")
            if total is None or len(out) >= total or not items:
                break
            page += 1
        return out

    # --- APM ---------------------------------------------------------------
    def list_applications(self) -> list[dict[str, Any]]:
        """GET /api/application-monitoring/applications -> [{id,label,...}]"""
        return self._get_paginated("/api/application-monitoring/applications")

    def list_application_services(
        self, app_id: str, window_ms: int = 86_400_000
    ) -> list[dict[str, Any]]:
        """Servicios de una aplicacion. Ruta con matrix param: applications;id=<id>/services

        OJO CON LA VENTANA: si no se pasa windowSize, la API usa 600000 ms (10
        minutos). Una aplicacion sin trafico en esos 10 minutos devuelve cero
        servicios y parece vacia. Con la ventana por defecto de 24 h el
        resultado refleja la instrumentacion real, no el trafico del momento.
        """
        data = self._get(
            f"/api/application-monitoring/applications;id={app_id}/services",
            params={"windowSize": window_ms},
        )
        return self._normalize_list(data)

    def list_application_endpoints(
        self, app_id: str, window_ms: int = 86_400_000
    ) -> list[dict[str, Any]]:
        """Endpoints de una aplicacion. Traen serviceId y technologies.
        Misma advertencia de ventana que list_application_services."""
        data = self._get(
            f"/api/application-monitoring/applications;id={app_id}/services/endpoints",
            params={"windowSize": window_ms},
        )
        return self._normalize_list(data)

    # --- RUM / Websites -----------------------------------------------------
    def list_websites(self) -> list[dict[str, Any]]:
        """GET /api/website-monitoring/config -> [{id,name,appName,...}]

        CORREGIDO: 'appName' NO es un vinculo real con una app backend.
        Verificado contra las 34 webapps del tenant: appName == name en el
        100% de los casos, sin excepcion. Es un autoetiquetado interno, no
        una referencia cruzada. rum.py lo trata como coincidencia de
        nombre (partial como maximo), nunca como enlace formal."""
        data = self._get("/api/website-monitoring/config")
        return self._normalize_list(data, str_label_key="name")

    def list_mobile_apps(self) -> list[dict[str, Any]]:
        """404 real en este tenant; se tolera en silencio."""
        data = self._get("/api/mobile-app-monitoring/apps", quiet_404=True)
        return self._normalize_list(data, str_label_key="label")

    def list_synthetic_tests(self) -> list[dict[str, Any]]:
        """CORREGIDO (no existia): GET /api/synthetics/settings/tests.
        Nunca se llamaba, asi que la "Synthetic" de la dimension
        RUM/Mobile/Synthetic no se evaluaba en absoluto.

        Requiere el permiso canViewSyntheticTests -devuelve 403 sin el,
        con mensaje explicito de que permiso falta. quiet_404=False porque
        un 403 no debe pasar en silencio (a diferencia de un modulo
        genuinamente ausente): que la dimension quede en 0 por falta de
        permiso es distinto de que quede en 0 porque no hay tests.

        Devuelve lista plana, sin wrapper de paginacion (verificado: 53
        tests en el tenant de demo, ?page= no cambia el resultado).
        Cada test trae 'applicationId'/'applications' cuando esta
        formalmente vinculado a una aplicacion -enlace por ID, igual que
        SLO/alertas/dashboards."""
        data = self._get("/api/synthetics/settings/tests")
        return self._normalize_list(data, str_label_key="label")

    # --- SLO ----------------------------------------------------------------
    def list_slo_configs(self) -> list[dict[str, Any]]:
        """GET /api/settings/slo -> items con entity.applicationId/serviceId/endpointId."""
        return self._get_paginated("/api/settings/slo")

    # --- Smart Alerts -------------------------------------------------------
    def list_application_alert_configs(self) -> list[dict[str, Any]]:
        """CORREGIDO. Alertas de aplicacion reales, con applicationId y mapa
        'applications'. Antes se usaba event-specifications/custom, que son
        custom events y no las Smart Alerts de aplicacion."""
        data = self._get("/api/events/settings/application-alert-configs")
        return self._normalize_list(data, str_label_key="name")

    def list_custom_event_specs(self) -> list[dict[str, Any]]:
        """Custom event specifications. Se mantiene como senal secundaria."""
        data = self._get("/api/events/settings/event-specifications/custom")
        return self._normalize_list(data, str_label_key="name")

    def list_website_alert_configs(self) -> list[dict[str, Any]]:
        data = self._get("/api/events/settings/website-alert-configs", quiet_404=True)
        return self._normalize_list(data, str_label_key="name")

    # --- Dashboards ---------------------------------------------------------
    def list_custom_dashboards(self) -> list[dict[str, Any]]:
        """CORREGIDO: /api/custom-dashboard en SINGULAR. El plural da 404."""
        data = self._get("/api/custom-dashboard")
        return self._normalize_list(data, str_label_key="title")

    def get_custom_dashboard(self, dashboard_id: str) -> dict[str, Any] | None:
        """Un dashboard completo, con sus widgets. La lista no los incluye, y los
        widgets son los que llevan el tagFilterExpression con application.name."""
        return self._get(f"/api/custom-dashboard/{dashboard_id}")

    # --- Infraestructura ----------------------------------------------------
    def list_infrastructure_snapshots(
        self, query: str, size: int = 200
    ) -> list[dict[str, Any]]:
        """CORREGIDO: el parametro es 'query', no 'q', y no admite vacio ni '*'."""
        data = self._get(
            "/api/infrastructure-monitoring/snapshots",
            params={"query": query, "size": size},
        )
        return self._normalize_list(data, str_label_key="label")

    def monitoring_state(self) -> dict[str, Any]:
        """Conteo global de entidades monitoreadas (hosts, serverless, otel)."""
        return self._get("/api/infrastructure-monitoring/monitoring-state") or {}

    # --- Automatizacion (Gobierno) -----------------------------------------
    def list_automation_actions(self) -> list[dict[str, Any]]:
        """CORREGIDO. Verificado: /api/automation/actions (plural) -> 200, lista
        plana de 93 acciones en el tenant de demo. Las otras rutas probadas
        antes (singular, v1) daban 404 y la dimension quedaba en 0 en silencio.

        Retorna 117 KB (incluye el contenido base64 de cada script), asi que
        solo se llama una vez por corrida y se reutiliza."""
        data = self._get("/api/automation/actions")
        return self._normalize_list(data, str_label_key="name")

    # --- Eventos ------------------------------------------------------------
    def list_events(self, from_ts_ms: int, to_ts_ms: int) -> list[dict[str, Any]]:
        """GET /api/events -> lista plana con entityType/entityLabel/snapshotId.
        Verificado: devuelve entityLabel PLANO (el MCP es quien lo anida)."""
        data = self._get("/api/events", params={"from": from_ts_ms, "to": to_ts_ms})
        return self._normalize_list(data, str_label_key="entityLabel")
