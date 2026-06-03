import json
from agents.base_agent import BaseAgent, _client
from config import DEEPSEEK_MODEL

_tool_decidir = [
    {
        "type": "function",
        "function": {
            "name": "finalizar_iteracion",
            "description": "Indica que la exploración está completa y no se necesitan más iteraciones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "razon": {"type": "string", "description": "Motivo por el que considera que la exploración está completa"},
                },
                "required": ["razon"],
            },
        },
    },
]


class IterableAgent(BaseAgent):
    def __init__(self, system_prompt: str):
        super().__init__(system_prompt)
        self.continuar_iteracion = True

    def decidir_iteracion(self, mensaje: str) -> None:
        try:
            response = _client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=self.historial + [{"role": "user", "content": mensaje}],
                tools=_tool_decidir,
                tool_choice="auto",
            )
            choice = response.choices[0]
            if choice.finish_reason == "tool_calls":
                tool_call = choice.message.tool_calls[0]
                args = json.loads(tool_call.function.arguments)
                self.continuar_iteracion = False
                print(f"\n[DECISION] La IA eligió TERMINAR iteraciones.")
                print(f"[RAZON] {args.get('razon', '')}")
            else:
                print(f"\n[DECISION] La IA eligió CONTINUAR iterando.")
                print(f"[RAZON] {choice.message.content.strip()}")
        except Exception as e:
            print(f"[ERROR decidir_iteracion] {e}")
