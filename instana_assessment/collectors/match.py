"""
Utilidad de matching de nombres. Desde las Fases 1-2 esto es el FALLBACK, no
el metodo principal: cada dimension que puede enlazar por ID lo hace primero
(topology.py) y solo recurre a find_match() cuando la API no ofrece un ID
compartido - p.ej. un SLO de tipo "synthetic" que no apunta a una aplicacion,
o un dashboard cuyo widget no trae tagFilterExpression.

Un match por find_match() nunca produce 'full': el criterio consolidado en
rubric.yaml (seccion evidence_criteria) es que el vinculo por nombre, al no
ser formal, tope siempre en 'partial'. La hoja "Recomendaciones" del ejemplo
manual senala como brecha #1 la falta de naming/tags normalizados entre
capacidades - apoyarse en el nombre para dar evidencia completa seria
apoyarse en lo que el propio assessment declara roto.
"""
from __future__ import annotations

import re


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def find_match(app_name: str, candidate_names: list[str]) -> str | None:
    """Devuelve el primer candidate_name que matchea app_name, o None."""
    norm_app = normalize(app_name)
    if not norm_app:
        return None
    for candidate in candidate_names:
        norm_candidate = normalize(candidate)
        if not norm_candidate:
            continue
        if norm_app == norm_candidate:
            return candidate
        if norm_app in norm_candidate or norm_candidate in norm_app:
            return candidate
    return None
