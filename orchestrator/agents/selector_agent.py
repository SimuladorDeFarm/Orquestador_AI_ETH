"""Agente Selector de Herramientas.

Dado el catálogo completo del runner, elige el SUBCONJUNTO (pool) de herramientas
pertinente para una tarea, según el objetivo de la misión y el rol del agente que
las usará (reconocimiento, explotación, etc.).

Motivo: el catálogo crecerá; pasarle todas las herramientas a cada agente gasta
tokens y lo confunde. Este agente entrega un pool acotado y relevante. Es genérico:
lo usa cualquier agente que lance comandos (Explorador, Explotador).
"""

import json
from agents.base_agent import BaseAgent, _client
from config import DEEPSEEK_MODEL
from core import event_bus


def _render_catalogo(catalogo: list[dict]) -> str:
    """Render breve del catálogo para la decisión (sin esquema_input, que no aporta aquí)."""
    lineas = []
    for h in catalogo:
        nombre = h.get("nombre", "?")
        categoria = h.get("categoria", "")
        descripcion = h.get("descripcion", "")
        usos = ", ".join(h.get("casos_usos", []) or [])
        linea = f"- {nombre} ({categoria}): {descripcion}"
        if usos:
            linea += f" | usos: {usos}"
        lineas.append(linea)
    return "\n".join(lineas)


def _tool_seleccionar(nombres: list[str]) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": "seleccionar_herramientas",
                "description": "Selecciona el subconjunto de herramientas pertinente para la tarea.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "herramientas": {
                            "type": "array",
                            "items": {"type": "string", "enum": nombres},
                            "description": "Nombres de las herramientas elegidas del catálogo",
                        },
                        "razon": {
                            "type": "string",
                            "description": "Breve justificación de la selección",
                        },
                    },
                    "required": ["herramientas"],
                },
            },
        }
    ]


class SelectorAgent(BaseAgent):
    def seleccionar(self, catalogo: list[dict], objetivo: str, rol: str = "reconocimiento") -> list[dict]:
        """Devuelve el subconjunto del catálogo relevante para (objetivo, rol).

        Stateless. Si la llamada falla o no elige nada, devuelve el catálogo
        completo (fallback seguro: mejor de más que dejar al agente sin tools).
        """
        if not catalogo:
            return []

        nombres = [h.get("nombre") for h in catalogo]
        mensaje = (
            f"ROL DEL AGENTE QUE USARÁ LAS HERRAMIENTAS: {rol}\n\n"
            f"OBJETIVO DE LA MISIÓN:\n{objetivo}\n\n"
            f"CATÁLOGO DE HERRAMIENTAS DISPONIBLES:\n{_render_catalogo(catalogo)}\n\n"
            "Elige el subconjunto de herramientas pertinente para este rol y objetivo "
            "usando la tool seleccionar_herramientas."
        )
        try:
            response = _client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": mensaje},
                ],
                tools=_tool_seleccionar(nombres),
                tool_choice={"type": "function", "function": {"name": "seleccionar_herramientas"}},
            )
            tool_call = response.choices[0].message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            elegidas = args.get("herramientas", [])
            print(f"[SELECTOR] rol={rol} eligió: {elegidas} — {args.get('razon', '')}")
            seleccion = [h for h in catalogo if h.get("nombre") in elegidas]
            if not seleccion:
                print(f"[SELECTOR] selección vacía → fallback: uso TODAS ({nombres})")
                event_bus.emitir(
                    "tool_selection",
                    "selector",
                    {"rol": rol, "elegidas": nombres, "fallback": True, "razon": "selección vacía → uso todas"},
                )
                return catalogo
            event_bus.emitir(
                "tool_selection",
                "selector",
                {"rol": rol, "elegidas": elegidas, "fallback": False, "razon": args.get("razon", "")},
            )
            return seleccion
        except Exception as e:
            print(f"[ERROR seleccionar] {e}")
            print(f"[SELECTOR] fallback por error → uso TODAS ({nombres})")
            event_bus.emitir("error", "selector", {"origen": "seleccionar", "mensaje": str(e)})
            event_bus.emitir(
                "tool_selection",
                "selector",
                {"rol": rol, "elegidas": nombres, "fallback": True, "razon": "error → uso todas"},
            )
            return catalogo
