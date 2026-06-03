from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_URL, DEEPSEEK_MODEL

_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_URL)


class BaseAgent:
    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt
        self.historial = [{"role": "system", "content": system_prompt}]

    def preguntar(self, mensaje: str) -> str | None:
        self.historial.append({"role": "user", "content": mensaje})
        try:
            response = _client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=self.historial,
            )
            texto = response.choices[0].message.content.strip()
            self.historial.append({"role": "assistant", "content": texto})
            return texto
        except Exception as e:
            print(f"[ERROR DeepSeek] {e}")
            return None
