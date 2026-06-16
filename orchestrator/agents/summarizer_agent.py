"""Agente Summarizer: mantiene la memoria de trabajo del pentest.

Convierte el flujo de "transcript que crece" en una memoria estructurada y
compacta (una KB). Es modular y stateless: cada llamada es una función pura
(memoria_actual, nuevo_resultado) -> memoria_actualizada, sin acumular historial.
Pensado para que el Explorador (u otro agente) lo consuma más adelante.
"""

import json
from agents.base_agent import BaseAgent, _client
from config import DEEPSEEK_MODEL

# Secciones de la memoria que son listas (todas salvo "objetivo").
CAMPOS_LISTA = ["servicios", "rutas", "archivos", "flags", "hallazgos", "pendientes", "descartado"]


def memoria_vacia(objetivo: str = "") -> dict:
    """Devuelve una KB vacía con todas sus secciones."""
    kb = {"objetivo": objetivo}
    for campo in CAMPOS_LISTA:
        kb[campo] = []
    return kb


def normalizar_memoria(datos: dict, objetivo: str = "") -> dict:
    """Asegura que la KB tenga todas las secciones y los tipos correctos."""
    kb = memoria_vacia(datos.get("objetivo") or objetivo)
    for campo in CAMPOS_LISTA:
        valor = datos.get(campo)
        if isinstance(valor, list):
            kb[campo] = valor
    return kb


def formatear_memoria(memoria: dict) -> str:
    """Renderiza la KB en texto compacto para inyectar en el prompt de un agente."""
    lineas = ["MEMORIA DE EXPLORACIÓN"]
    if memoria.get("objetivo"):
        lineas.append(f"Objetivo: {memoria['objetivo']}")

    def bloque(titulo, items, render):
        if not items:
            return
        lineas.append(f"{titulo}:")
        for it in items:
            lineas.append(f"  - {render(it)}")

    bloque("Servicios", memoria.get("servicios", []),
           lambda s: f"{s.get('puerto','?')}/{s.get('protocolo','tcp')} "
                     f"{s.get('servicio','')} {s.get('version','')}".strip())
    bloque("Rutas", memoria.get("rutas", []),
           lambda r: f"{r.get('url','')} [{r.get('estado','')}] {r.get('nota','')}".strip())
    bloque("Archivos", memoria.get("archivos", []),
           lambda a: f"{a.get('path','')} — {a.get('nota','')}".strip(" —"))
    bloque("Flags", memoria.get("flags", []), lambda f: str(f))
    bloque("Hallazgos", memoria.get("hallazgos", []), lambda h: str(h))
    bloque("Pendientes", memoria.get("pendientes", []), lambda p: str(p))
    bloque("Descartado", memoria.get("descartado", []), lambda d: str(d))

    return "\n".join(lineas)


_tool_memoria = [
    {
        "type": "function",
        "function": {
            "name": "actualizar_memoria",
            "description": "Devuelve la memoria de exploración COMPLETA y actualizada tras integrar el nuevo resultado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "servicios": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "puerto": {"type": "integer"},
                                "protocolo": {"type": "string"},
                                "servicio": {"type": "string"},
                                "version": {"type": "string"},
                            },
                        },
                    },
                    "rutas": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string"},
                                "estado": {"type": "string"},
                                "nota": {"type": "string"},
                            },
                        },
                    },
                    "archivos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "nota": {"type": "string"},
                            },
                        },
                    },
                    "flags": {"type": "array", "items": {"type": "string"}},
                    "hallazgos": {"type": "array", "items": {"type": "string"}},
                    "pendientes": {"type": "array", "items": {"type": "string"}},
                    "descartado": {"type": "array", "items": {"type": "string"}},
                },
                "required": CAMPOS_LISTA,
            },
        },
    }
]


class SummarizerAgent(BaseAgent):
    def actualizar_memoria(self, memoria: dict, herramienta: str, params: dict, resultado: str) -> dict:
        """Integra el resultado de un comando en la memoria y devuelve la KB nueva.

        Stateless: no usa historial acumulado. Si la llamada falla, devuelve la
        memoria sin cambios para no perder el estado.
        """
        mensaje = (
            "MEMORIA ACTUAL (JSON):\n"
            + json.dumps(memoria, ensure_ascii=False, indent=2)
            + "\n\nNUEVO RESULTADO DE UN COMANDO:\n"
            + f"herramienta: {herramienta}\nparams: {json.dumps(params, ensure_ascii=False)}\n"
            + f"salida:\n{resultado}\n\n"
            + "Integra este resultado en la memoria y devuelve la memoria COMPLETA "
            + "actualizada con la tool actualizar_memoria."
        )
        try:
            response = _client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": mensaje},
                ],
                tools=_tool_memoria,
                tool_choice={"type": "function", "function": {"name": "actualizar_memoria"}},
            )
            tool_call = response.choices[0].message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            return normalizar_memoria(args, objetivo=memoria.get("objetivo", ""))
        except Exception as e:
            print(f"[ERROR actualizar_memoria] {e}")
            return memoria
