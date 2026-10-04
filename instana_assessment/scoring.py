from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class Rubric:
    dimensions: list[dict[str, Any]]
    levels: list[dict[str, Any]]
    multipliers: dict[str, float]

    @classmethod
    def load(cls, path: str) -> "Rubric":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(
            dimensions=data["dimensions"],
            levels=data["levels"],
            multipliers=data["evidence_multipliers"],
        )

    def total_weight(self) -> float:
        return sum(d["weight"] for d in self.dimensions)

    def level_for_score(self, score: float) -> dict[str, Any]:
        for lvl in self.levels:
            if lvl["min_score"] <= score <= lvl["max_score"]:
                return lvl
        # score fuera de rango (no deberia pasar si min/max cubren 0-100)
        return self.levels[-1] if score > 0 else self.levels[0]


@dataclass
class AppScore:
    app_name: str
    dimension_scores: dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    level: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)
    top_gap: str = ""


def score_app(app_name: str, evidence: dict[str, str], rubric: Rubric) -> AppScore:
    dimension_scores: dict[str, float] = {}
    total = 0.0
    for dim in rubric.dimensions:
        key = dim["key"]
        level = evidence.get(key, "none")
        multiplier = rubric.multipliers.get(level, 0.0)
        dim_score = dim["weight"] * multiplier
        dimension_scores[key] = dim_score
        total += dim_score

    level = rubric.level_for_score(total)
    top_gap = _identify_top_gap(dimension_scores, rubric)

    return AppScore(
        app_name=app_name,
        dimension_scores=dimension_scores,
        total_score=round(total, 1),
        level=level,
        evidence=evidence,
        top_gap=top_gap,
    )


def _identify_top_gap(dimension_scores: dict[str, float], rubric: Rubric) -> str:
    """Dimension con mayor brecha absoluta (peso - score obtenido), como texto legible."""
    worst_key = None
    worst_gap = -1.0
    for dim in rubric.dimensions:
        key = dim["key"]
        gap = dim["weight"] - dimension_scores.get(key, 0.0)
        if gap > worst_gap:
            worst_gap = gap
            worst_key = dim["name"]
    if worst_key and worst_gap > 0:
        return worst_key
    return "Sin brecha relevante"


@dataclass
class AssessmentResult:
    app_scores: list[AppScore]
    dimension_summary: list[dict[str, Any]]
    level_distribution: dict[int, int]
    average_score: float
    max_score: float
    min_score: float
    estimated_level: dict[str, Any]


def score_assessment(
    evidence_by_app: dict[str, dict[str, str]], rubric: Rubric
) -> AssessmentResult:
    app_scores = [
        score_app(app_name, evidence, rubric)
        for app_name, evidence in evidence_by_app.items()
    ]
    app_scores.sort(key=lambda a: a.total_score, reverse=True)

    n = len(app_scores) or 1
    dimension_summary = []
    for dim in rubric.dimensions:
        key = dim["key"]
        avg = sum(a.dimension_scores.get(key, 0.0) for a in app_scores) / n
        pct = (avg / dim["weight"]) * 100 if dim["weight"] else 0.0
        dimension_summary.append(
            {
                "key": key,
                "name": dim["name"],
                "weight": dim["weight"],
                "avg_score": round(avg, 2),
                "pct_of_weight": round(pct, 0),
                "reading": _reading_label(pct),
            }
        )

    level_distribution: dict[int, int] = {lvl["level"]: 0 for lvl in rubric.levels}
    for a in app_scores:
        level_distribution[a.level["level"]] += 1

    scores = [a.total_score for a in app_scores] or [0.0]
    average_score = round(sum(scores) / len(scores), 1)

    return AssessmentResult(
        app_scores=app_scores,
        dimension_summary=dimension_summary,
        level_distribution=level_distribution,
        average_score=average_score,
        max_score=max(scores),
        min_score=min(scores),
        estimated_level=rubric.level_for_score(average_score),
    )


def _reading_label(pct: float) -> str:
    if pct >= 70:
        return "Fuerte"
    if pct >= 45:
        return "Media"
    return "Baja"
