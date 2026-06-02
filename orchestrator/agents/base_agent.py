import json
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_URL, DEEPSEEK_MODEL
from core.runner_client import ejecutar_en_docker

_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_URL)

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
    }
]


class BaseAgent:
    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt
        self.historial = [{"role": "system", "content": system_prompt}]

    def preguntar(self, mensaje: str) -> str | None:
        self.historial.append({"role": "user", "content": mensaje})

        while True:
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
                print("Escogio calls")
                tool_call = choice.message.tool_calls[0]
                self.historial.append(choice.message)

                args = json.loads(tool_call.function.arguments)
                print(f"[TOOL CALL] {args}")
                output = ejecutar_en_docker(
                    f"{args['tool']} {args.get('options', '')} {args['target']}".strip()
                )
                print(f"[DOCKER OUTPUT]\n{output}")

                self.historial.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": output,
                })

            else:
                texto = choice.message.content.strip()
                self.historial.append({"role": "assistant", "content": texto})
                return texto
