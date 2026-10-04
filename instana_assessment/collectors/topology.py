"""
Topologia de aplicaciones: se construye UNA vez y la reutilizan todas las
dimensiones para enlazar por ID en vez de por coincidencia de nombre.

El colector original cruzaba todo con substring sobre nombres normalizados.
Eso falla en las dos direcciones y esta comprobado contra el tenant:

  - Falso negativo: un SLO llamado "Latencia de pagos" apunta por
    applicationId a una aplicacion llamada "Servicios generales": su nombre
    no contiene el de la aplicacion. Por nombre no se encuentra nunca.
  - Falso positivo: una app llamada "SAS" normaliza a "sas" y hace match
    con cualquier candidato que contenga esa subcadena.

La propia hoja de Recomendaciones del assessment senala como brecha #1 que
la nomenclatura NO esta normalizada, asi que apoyarse en ella es apoyarse
justo en lo que el assessment declara roto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..instana_client import InstanaClient


@dataclass
class App:
    id: str
    label: str
    service_ids: set[str] = field(default_factory=set)
    endpoint_ids: set[str] = field(default_factory=set)
    service_labels: set[str] = field(default_factory=set)
    technologies: set[str] = field(default_factory=set)


@dataclass
class Topology:
    apps: list[App]

    @property
    def labels(self) -> list[str]:
        return [a.label for a in self.apps]

    def by_app_id(self) -> dict[str, App]:
        return {a.id: a for a in self.apps}

    def by_service_id(self) -> dict[str, App]:
        out: dict[str, App] = {}
        for a in self.apps:
            for sid in a.service_ids:
                out.setdefault(sid, a)
        return out

    def by_endpoint_id(self) -> dict[str, App]:
        out: dict[str, App] = {}
        for a in self.apps:
            for eid in a.endpoint_ids:
                out.setdefault(eid, a)
        return out


def build_topology(
    client: InstanaClient,
    max_apps: int | None = None,
    window_ms: int = 86_400_000,
) -> Topology:
    """
    Descubre aplicaciones y desciende a sus servicios y endpoints.

    Cuesta 2 llamadas por aplicacion, pero es lo que habilita el enlace por ID
    en SLO, alertas, eventos e infraestructura. Se paga una vez y lo aprovechan
    cinco dimensiones.

    window_ms importa mucho: la API usa 10 minutos por defecto, lo que hace
    parecer vacias a las aplicaciones sin trafico reciente.
    """
    raw_apps = client.list_applications()
    if max_apps:
        raw_apps = raw_apps[:max_apps]

    apps: list[App] = []
    for raw in raw_apps:
        app_id = raw.get("id") or ""
        label = raw.get("label") or raw.get("name") or ""
        if not app_id or not label:
            continue
        app = App(id=app_id, label=label)

        for svc in client.list_application_services(app_id, window_ms=window_ms):
            sid = svc.get("id")
            if sid:
                app.service_ids.add(sid)
            slabel = svc.get("label") or svc.get("name")
            if slabel:
                app.service_labels.add(slabel)

        for ep in client.list_application_endpoints(app_id, window_ms=window_ms):
            eid = ep.get("id")
            if eid:
                app.endpoint_ids.add(eid)
            sid = ep.get("serviceId")
            if sid:
                app.service_ids.add(sid)
            for tech in ep.get("technologies") or []:
                app.technologies.add(tech)

        apps.append(app)

    return Topology(apps=apps)
