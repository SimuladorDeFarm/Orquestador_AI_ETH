import json
from agents.base_agent import BaseAgent, _client
from config import DEEPSEEK_MODEL
from core import event_bus
from metricas.collector import coleccion_activa

_tool_aprobar = [
    {
        "type": "function",
        "function": {
            "name": "aprobar_exploracion",
            "description": "Aprueba el reporte de exploración indicando que la información es suficiente para continuar con la fase de explotación.",
            "parameters": {
                "type": "object",
                "properties": {
                    "razon": {"type": "string", "description": "Motivo por el que considera que la exploración fue suficiente"},
                },
                "required": ["razon"],
            },
        },
    },
]


class JudgeAgent(BaseAgent):
    def __init__(self, system_prompt: str):
        super().__init__(system_prompt)
        self.aprueba = False

    def evaluar_reporte(self, reporte: str) -> None:
        try:
            response = _client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=self.historial + [{"role": "user", "content": reporte}],
                tools=_tool_aprobar,
                tool_choice="auto",
            )
            choice = response.choices[0]
            col = coleccion_activa()
            if choice.finish_reason == "tool_calls":
                tool_call = choice.message.tool_calls[0]
                args = json.loads(tool_call.function.arguments)
                self.aprueba = True
                razon = args.get("razon", "")
                print(f"\n[JUEZ] APROBADO — {razon}")
                event_bus.emitir("judge_verdict", "judge", {"aprobado": True, "razon": razon})
                if col is not None:
                    col.registrar_decision_juez(aprueba=True, razon=razon)
            else:
                feedback = choice.message.content.strip()
                print(f"\n[JUEZ] RECHAZADO — Se requiere otra iteración.")
                print(f"[JUEZ] Feedback: {feedback}")
                event_bus.emitir("judge_verdict", "judge", {"aprobado": False, "feedback": feedback})
                if col is not None:
                    col.registrar_decision_juez(aprueba=False, razon=feedback)
        except Exception as e:
            print(f"[ERROR evaluar_reporte] {e}")
            event_bus.emitir("error", "judge", {"origen": "evaluar_reporte", "mensaje": str(e)})
