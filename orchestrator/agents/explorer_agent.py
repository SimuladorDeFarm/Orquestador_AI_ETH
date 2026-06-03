import json
from agents.iterable_agent import IterableAgent, _client
from config import DEEPSEEK_MODEL
from core.runner_client import ejecutar_en_docker

_tools = [
    {
        "type": "function",
        "function": {
            "name": "ejecutar_comando",
            "description": "Ejecuta un comando de reconocimiento o explotación en el entorno objetivo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool":    {"type": "string", "description": "Herramienta a ejecutar (nmap, ffuf, sqlmap, etc.)"},
                    "target":  {"type": "string", "description": "IP o dominio objetivo"},
                    "options": {"type": "string", "description": "Flags y opciones del comando"},
                },
                "required": ["tool", "target"],
            },
        },
    },
]

_tool_planificar = [
    {
        "type": "function",
        "function": {
            "name": "planificar_tareas",
            "description": "Genera la lista de tareas de reconocimiento a ejecutar basándose en los hallazgos del scan inicial.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tareas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de comandos a ejecutar en orden",
                    }
                },
                "required": ["tareas"],
            },
        },
    }
]


class ExplorerAgent(IterableAgent):
    def __init__(self, system_prompt: str):
        super().__init__(system_prompt)
        self.lista_tareas = []

    def preguntar(self, mensaje: str, usar_tools: bool = True) -> str | None:
        if not usar_tools:
            return super().preguntar(mensaje)

        self.historial.append({"role": "user", "content": mensaje})
        try:
            response = _client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=self.historial,
                tools=_tools,
                tool_choice="auto",
            )
        except Exception as e:
            print(f"[ERROR DeepSeek] {e}")
            return None

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls":
            tool_call = choice.message.tool_calls[0]
            self.historial.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                ],
            })
            args = json.loads(tool_call.function.arguments)
            print(f"[TOOL CALL] {tool_call.function.name} {args}")
            output = ejecutar_en_docker(
                f"{args['tool']} {args.get('options', '')} {args['target']}".strip()
            )
            print(f"[DOCKER OUTPUT]\n{output}")
            self.historial.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": output,
            })
            return output
        else:
            texto = choice.message.content.strip()
            self.historial.append({"role": "assistant", "content": texto})
            return texto

    def generar_tareas(self, mensaje: str) -> list:
        try:
            response = _client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=self.historial + [{"role": "user", "content": mensaje}],
                tools=_tool_planificar,
                tool_choice={"type": "function", "function": {"name": "planificar_tareas"}},
            )
            tool_call = response.choices[0].message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            self.lista_tareas = args["tareas"]
            print(f"[TAREAS GENERADAS] {self.lista_tareas}")
            return self.lista_tareas
        except Exception as e:
            print(f"[ERROR generar_tareas] {e}")
            return []
