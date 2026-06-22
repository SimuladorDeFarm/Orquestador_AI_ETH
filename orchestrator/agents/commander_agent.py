"""Agente Comandante (Commander): coordinador del Multi-Agent System.

Es el primer agente en ejecutarse. Recibe el alcance (scope) y, en cada paso,
decide qué fase/agente actúa a continuación a partir de los reportes acumulados.
No ejecuta herramientas ni explora: SOLO dirige.

El diseño es modular vía un registro de `Fase`: hoy solo conoce la exploración,
pero añadir la explotación es registrar otra `Fase` (ver agents/commander.py).
"""

import json
from dataclasses import dataclass
from typing import Callable

from agents.base_agent import BaseAgent, _client
from config import DEEPSEEK_MODEL
from metricas.collector import coleccion_activa


@dataclass
class Fase:
    """Una fase de la campaña que el Commander puede asignar.

    `ejecutar(target, sesion_id, control, contexto) -> list[str]` corre el flujo
    completo del agente responsable de la fase y devuelve los reportes que produjo.
    `contexto` es un dict compartido entre fases (p. ej. la exploración deja ahí su
    KB y la explotación la lee). Esta indirección permite enchufar nuevos agentes
    sin tocar al Commander: basta registrar otra `Fase`.
    """

    nombre: str
    descripcion: str
    ejecutar: Callable[..., list]


def _tools_decidir(nombres: list[str]) -> list:
    """Tools de decisión del Commander: asignar una fase o cerrar la campaña."""
    return [
        {
            "type": "function",
            "function": {
                "name": "asignar_fase",
                "description": "Asigna la siguiente fase de la campaña al agente correspondiente.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "fase": {
                            "type": "string",
                            "enum": nombres,
                            "description": "Nombre exacto de la fase a ejecutar a continuación",
                        },
                        "razon": {
                            "type": "string",
                            "description": "Por qué esta fase es la siguiente",
                        },
                    },
                    "required": ["fase"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finalizar_campana",
                "description": (
                    "Indica que no quedan fases útiles por ejecutar y la campaña debe "
                    "cerrarse con el reporte ejecutivo final."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "razon": {"type": "string", "description": "Motivo del cierre"},
                    },
                    "required": ["razon"],
                },
            },
        },
    ]


class CommanderAgent(BaseAgent):
    """Coordinador del MAS. Decide la secuencia de fases de la campaña."""

    def decidir_fase(
        self,
        scope: dict,
        fases_disponibles: list[Fase],
        fases_completadas: list[str],
        reportes: list[str],
    ) -> str | None:
        """Elige la siguiente fase a ejecutar entre las disponibles.

        Devuelve el nombre de la fase elegida, o None para finalizar la campaña.
        Fallback seguro (como el Selector): ante error, decisión vacía o fase
        inválida, asigna la primera fase disponible en vez de quedarse sin actuar.
        """
        nombres = [f.nombre for f in fases_disponibles]
        col = coleccion_activa()
        if not nombres:
            if col is not None:
                col.registrar_decision_commander(None, "no quedan fases disponibles")
            return None

        catalogo_fases = "\n".join(f"- {f.nombre}: {f.descripcion}" for f in fases_disponibles)
        completadas = ", ".join(fases_completadas) if fases_completadas else "ninguna"
        resumen_reportes = "\n\n---\n\n".join(reportes) if reportes else "Aún no hay reportes."

        mensaje = (
            "ESTADO DE LA CAMPAÑA\n"
            f"- Objetivo (target): {scope.get('target')}\n"
            f"- Misión: {scope.get('mision')}\n"
            f"- Fases ya completadas: {completadas}\n\n"
            f"FASES DISPONIBLES (elige UNA con asignar_fase):\n{catalogo_fases}\n\n"
            f"REPORTES RECIBIDOS HASTA AHORA:\n{resumen_reportes}\n\n"
            "Decide la siguiente fase. Si ninguna fase disponible aporta valor (la misión ya "
            "está cumplida o no hay nada más que hacer), usa finalizar_campana."
        )

        try:
            response = _client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": mensaje},
                ],
                tools=_tools_decidir(nombres),
                tool_choice="auto",
            )
            choice = response.choices[0]
            if choice.finish_reason == "tool_calls":
                tool_call = choice.message.tool_calls[0]
                args = json.loads(tool_call.function.arguments)
                razon = args.get("razon", "")
                if tool_call.function.name == "finalizar_campana":
                    print(f"\n[COMMANDER] Finaliza la campaña — {razon}")
                    if col is not None:
                        col.registrar_decision_commander(None, razon)
                    return None
                fase = args.get("fase")
                if fase in nombres:
                    print(f"\n[COMMANDER] Asigna fase '{fase}' — {razon}")
                    if col is not None:
                        col.registrar_decision_commander(fase, razon)
                    return fase
                print(f"[COMMANDER] Fase '{fase}' inválida → fallback: {nombres[0]}")
                if col is not None:
                    col.registrar_decision_commander(nombres[0], f"fallback (fase '{fase}' inválida)")
                return nombres[0]

            # Respondió texto sin usar tool: no deja la campaña sin avanzar.
            print(f"[COMMANDER] Sin decisión explícita → fallback: {nombres[0]}")
            if col is not None:
                col.registrar_decision_commander(nombres[0], "fallback (sin decisión explícita)")
            return nombres[0]
        except Exception as e:  # noqa: BLE001 - el fallback mantiene viva la campaña
            print(f"[ERROR decidir_fase] {e}")
            print(f"[COMMANDER] fallback por error → {nombres[0]}")
            if col is not None:
                col.registrar_decision_commander(nombres[0], f"fallback por error: {e}")
            return nombres[0]
