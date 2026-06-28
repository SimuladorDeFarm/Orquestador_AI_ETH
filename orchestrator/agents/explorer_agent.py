import json
from agents.iterable_agent import IterableAgent, _client, _tool_decidir
from config import DEEPSEEK_MODEL
from core.runner_client import ejecutar, formatear_resultado
from core import event_bus
from agents.summarizer_agent import memoria_vacia, formatear_memoria
from metricas.collector import coleccion_activa


def _tools_ejecutar(nombres: list[str]) -> list:
    """Tool para ejecutar UNA herramienta del runner con params estructurados."""
    return [
        {
            "type": "function",
            "function": {
                "name": "ejecutar_herramienta",
                "description": (
                    "Ejecuta una herramienta del runner sobre el objetivo. "
                    "Los parámetros van en 'params' según el esquema_input de cada herramienta."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "herramienta": {
                            "type": "string",
                            "enum": nombres,
                            "description": "Nombre exacto de una herramienta disponible",
                        },
                        "params": {
                            "type": "object",
                            "description": "Parámetros de la herramienta según su esquema_input",
                        },
                    },
                    "required": ["herramienta", "params"],
                },
            },
        }
    ]


def _tools_planificar(nombres: list[str]) -> list:
    """Tool para planificar una lista de tareas (cada una herramienta + params)."""
    return [
        {
            "type": "function",
            "function": {
                "name": "planificar_tareas",
                "description": "Genera la lista de tareas de reconocimiento a ejecutar, en orden.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tareas": {
                            "type": "array",
                            "description": "Lista de tareas a ejecutar en orden",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "herramienta": {"type": "string", "enum": nombres},
                                    "params": {"type": "object"},
                                },
                                "required": ["herramienta", "params"],
                            },
                        }
                    },
                    "required": ["tareas"],
                },
            },
        }
    ]


class ExplorerAgent(IterableAgent):
    """Explorador con memoria estructurada.

    En vez de arrastrar todo el transcript (outputs crudos), mantiene una KB
    compacta (`self.memoria`) que el Summarizer actualiza tras cada comando.
    Todas las llamadas al LLM usan esa memoria como contexto, no el historial,
    lo que reduce tokens y evita confundir al modelo con texto redundante.
    """

    def __init__(
        self,
        system_prompt: str,
        herramientas: list[dict] | None = None,
        sesion_id: int = 1,
        summarizer=None,
        objetivo: str = "",
    ):
        super().__init__(system_prompt)
        self.lista_tareas = []
        self.sesion_id = sesion_id
        self.herramientas = herramientas or []
        nombres = [h.get("nombre") for h in self.herramientas]
        self._tools = _tools_ejecutar(nombres)
        self._tool_planificar = _tools_planificar(nombres)

        self.summarizer = summarizer
        self.memoria = memoria_vacia(objetivo)
        self.registro = []  # outputs crudos, para auditoría/Reporter (fuera del contexto LLM)

    # --- contexto / memoria ---

    def _contexto(self) -> list:
        """Mensajes base de cada llamada: system prompt + memoria de trabajo."""
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": formatear_memoria(self.memoria)},
        ]

    def ingerir(self, herramienta: str, params: dict, resultado: str) -> None:
        """Guarda el output crudo aparte y actualiza la memoria vía Summarizer."""
        self.registro.append({"herramienta": herramienta, "params": params, "resultado": resultado})
        if self.summarizer is not None:
            self.memoria = self.summarizer.actualizar_memoria(self.memoria, herramienta, params, resultado)
            memoria_txt = formatear_memoria(self.memoria)
            crudo_acumulado = sum(len(r["resultado"]) for r in self.registro)
            print("\n" + "-" * 50)
            print(f"  MEMORIA ACTUALIZADA (historial reducido)  "
                  f"[{len(self.registro)} comandos · crudo acumulado: {crudo_acumulado} chars "
                  f"→ memoria: {len(memoria_txt)} chars]")
            print("-" * 50)
            print(memoria_txt)
            event_bus.emitir(
                "memory_update",
                "summarizer",
                {
                    "comandos_acumulados": len(self.registro),
                    "chars_crudo": crudo_acumulado,
                    "chars_memoria": len(memoria_txt),
                    "memoria": memoria_txt,
                },
            )

            col = coleccion_activa()
            if col is not None:
                col.registrar_ingesta(crudo_acumulado, len(memoria_txt))

    def ejecutar_tareas(self, control=None) -> None:
        """Ejecuta en orden las tareas de `self.lista_tareas` vía el runner.

        Cada resultado se ingiere en la memoria (KB). Lógica compartida por el
        Explorador y el Explotador: ambos planifican tareas y las ejecutan igual.
        `control`, si se entrega, permite pausar/detener en cada tarea.
        """
        i = 0
        while self.lista_tareas:
            if control is not None:
                control.checkpoint()
            tarea_actual = self.lista_tareas[0]
            print(f"\n[TAREA {i + 1}] {tarea_actual}")
            herramienta = tarea_actual.get("herramienta")
            if not herramienta:
                print(f"[SKIP] Tarea sin herramienta: {tarea_actual}")
                event_bus.emitir("task_skipped", "explorer", {"numero": i + 1, "tarea": tarea_actual})
            else:
                params = tarea_actual.get("params", {})
                event_bus.emitir(
                    "task_start",
                    "explorer",
                    {"numero": i + 1, "herramienta": herramienta, "params": params},
                )
                tarea_res = ejecutar(herramienta, params, self.sesion_id)
                output = formatear_resultado(tarea_res)
                print(output)
                event_bus.emitir(
                    "tool_result",
                    "explorer",
                    {"herramienta": herramienta, "params": params, "output": output, "chars": len(output)},
                )
                # El crudo se guarda aparte y la memoria se actualiza vía Summarizer;
                # no se acumula en el contexto del agente.
                self.ingerir(herramienta, params, output)
            self.lista_tareas.pop(0)
            i += 1

    # --- llamadas al LLM (basadas en memoria, no en historial) ---

    def preguntar(self, mensaje: str, usar_tools: bool = True) -> str | None:
        messages = self._contexto() + [{"role": "user", "content": mensaje}]

        if not usar_tools:
            try:
                response = _client.chat.completions.create(model=DEEPSEEK_MODEL, messages=messages)
                return (response.choices[0].message.content or "").strip()
            except Exception as e:
                print(f"[ERROR DeepSeek] {e}")
                event_bus.emitir("error", "explorer", {"origen": "preguntar", "mensaje": str(e)})
                return None

        try:
            response = _client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                tools=self._tools,
                tool_choice="auto",
            )
        except Exception as e:
            print(f"[ERROR DeepSeek] {e}")
            event_bus.emitir("error", "explorer", {"origen": "preguntar", "mensaje": str(e)})
            return None

        choice = response.choices[0]
        if choice.finish_reason == "tool_calls":
            tool_call = choice.message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            print(f"[TOOL CALL] {tool_call.function.name} {args}")
            event_bus.emitir(
                "tool_call",
                "explorer",
                {"herramienta": args["herramienta"], "params": args.get("params", {})},
            )
            tarea = ejecutar(args["herramienta"], args.get("params", {}), self.sesion_id)
            output = formatear_resultado(tarea)
            print(f"[RESULTADO]\n{output}")
            event_bus.emitir(
                "tool_result",
                "explorer",
                {
                    "herramienta": args["herramienta"],
                    "params": args.get("params", {}),
                    "output": output,
                    "chars": len(output),
                },
            )
            self.ingerir(args["herramienta"], args.get("params", {}), output)
            return output
        else:
            return (choice.message.content or "").strip()

    def generar_tareas(self, mensaje: str) -> list:
        try:
            response = _client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=self._contexto() + [{"role": "user", "content": mensaje}],
                tools=self._tool_planificar,
                tool_choice={"type": "function", "function": {"name": "planificar_tareas"}},
            )
            tool_call = response.choices[0].message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            self.lista_tareas = args["tareas"]
            print(f"[TAREAS GENERADAS] {self.lista_tareas}")
            event_bus.emitir(
                "tasks_planned",
                "explorer",
                {"cantidad": len(self.lista_tareas), "tareas": self.lista_tareas},
            )
            col = coleccion_activa()
            if col is not None:
                col.registrar_tareas_generadas(len(self.lista_tareas))
            return self.lista_tareas
        except Exception as e:
            print(f"[ERROR generar_tareas] {e}")
            event_bus.emitir("error", "explorer", {"origen": "generar_tareas", "mensaje": str(e)})
            return []

    def decidir_iteracion(self, mensaje: str) -> None:
        """Decide si continuar iterando, evaluando la memoria (no el historial)."""
        try:
            response = _client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=self._contexto() + [{"role": "user", "content": mensaje}],
                tools=_tool_decidir,
                tool_choice="auto",
            )
            choice = response.choices[0]
            col = coleccion_activa()
            if choice.finish_reason == "tool_calls":
                tool_call = choice.message.tool_calls[0]
                args = json.loads(tool_call.function.arguments)
                self.continuar_iteracion = False
                print("\n[DECISION] La IA eligió TERMINAR iteraciones.")
                print(f"[RAZON] {args.get('razon', '')}")
                event_bus.emitir(
                    "iteration_decision",
                    "explorer",
                    {"continuar": False, "razon": args.get("razon", "")},
                )
                if col is not None:
                    col.registrar_decision_ia(continuar=False, razon=args.get("razon", ""))
            else:
                razon = (choice.message.content or "").strip()
                print("\n[DECISION] La IA eligió CONTINUAR iterando.")
                print(f"[RAZON] {razon}")
                event_bus.emitir(
                    "iteration_decision",
                    "explorer",
                    {"continuar": True, "razon": razon},
                )
                if col is not None:
                    col.registrar_decision_ia(continuar=True, razon=razon)
        except Exception as e:
            print(f"[ERROR decidir_iteracion] {e}")
            event_bus.emitir("error", "explorer", {"origen": "decidir_iteracion", "mensaje": str(e)})
