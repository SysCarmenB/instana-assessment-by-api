"""
Forma comun que devuelven los collectors desde la Fase 7: no solo el
veredicto (full/partial/none), tambien de que objeto sale ese veredicto.

Antes de esto, el reporte decia "SLO/Apdex: Si" y no habia forma de saber
si eso salio de un SLO real enlazado por ID o de un match de nombre
debil, sin ir a leer el codigo. Ahora cada dimension deja un rastro
legible por app: id del objeto, su nombre y como se enlazo.

trace es opcional en la practica: el modo --source csv (evidencia
digitalizada a mano desde el Excel) no tiene de donde sacarlo, y queda
vacio. El reporte debe funcionar igual de bien con trace={}.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CollectorResult:
    evidence: dict[str, str]
    trace: dict[str, str] = field(default_factory=dict)
