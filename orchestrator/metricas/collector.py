"""Recolector de métricas de una campaña del orquestador.

Diseño:
- Un único `MetricsCollector` activo por campaña (sesión única, igual que el
  resto del sistema). Se accede vía `coleccion_activa()`.
- Las llamadas al LLM se capturan de forma CENTRAL envolviendo el cliente OpenAI
  compartido (`agents.base_agent._client`): todos los agentes lo usan, así que
  con un solo wrapper se miden tokens y latencia de cada llamada sin tocar a cada
  agente. El agente que hizo la llamada se infiere de su system prompt.
- El resto de eventos (tareas del runner, decisiones, ingestas de memoria) se
  registran con pequeñas llamadas explícitas en los puntos del flujo.

Todo es best-effort: si algo falla al medir, no debe romper la campaña.
"""

import time
from dataclasses import dataclass, field

# Tarifas aproximadas de DeepSeek deepseek-chat (USD por 1M tokens).
# Son orientativas y pueden cambiar; ajústalas si la facturación real difiere.
USD_POR_1M_INPUT = 0.27
USD_POR_1M_OUTPUT = 1.10

# Mapa para clasificar una llamada LLM según una palabra clave del system prompt.
_CLAVES_AGENTE = ["Explorador", "Juez", "Reportador", "Selector", "Comandante", "Summarizer"]


def _clasificar_agente(messages) -> str:
    """Infiere qué agente hizo la llamada a partir del system prompt."""
    try:
        for m in messages or []:
            if m.get("role") == "system":
                texto = m.get("content", "") or ""
                for clave in _CLAVES_AGENTE:
                    if clave in texto:
                        return clave
                break
    except Exception:
        pass
    return "Otro"


@dataclass
class MetricsCollector:
    """Acumula los eventos de una campaña. Los agrega el reporte al final."""

    target: str = ""
    mision: str = ""
    inicio: float = field(default_factory=time.time)
    fin: float | None = None

    # Eventos crudos (se agregan en el reporte).
    llm_calls: list = field(default_factory=list)      # {agente, prompt_tokens, completion_tokens, latencia, iteracion}
    tareas_runner: list = field(default_factory=list)  # {herramienta, estado, codigo_salida, latencia, iteracion}
    ingestas: list = field(default_factory=list)       # {comando, crudo_acumulado, memoria_len}
    errores: list = field(default_factory=list)        # {origen, detalle}

    # Por iteración: {n: {tareas_generadas, decision_ia, razon_ia, decision_juez, razon_juez}}
    iteraciones: dict = field(default_factory=dict)

    # Estado de la campaña.
    fase_actual: str = "setup"
    iter_actual: int = 0
    motivo_termino: str = ""
    exito: bool | None = None
    memoria_final: dict = field(default_factory=dict)
    ultima_razon_juez: str = ""

    # --- contexto de fase/iteración ---

    def set_fase(self, nombre: str) -> None:
        self.fase_actual = nombre

    def iniciar_iteracion(self, n: int) -> None:
        self.iter_actual = n
        self.iteraciones.setdefault(n, {
            "tareas_generadas": 0,
            "decision_ia": None, "razon_ia": "",
            "decision_juez": None, "razon_juez": "",
        })

    # --- registro de eventos ---

    def registrar_llm(self, agente: str, prompt_tokens: int, completion_tokens: int, latencia: float) -> None:
        self.llm_calls.append({
            "agente": agente,
            "prompt_tokens": prompt_tokens or 0,
            "completion_tokens": completion_tokens or 0,
            "latencia": latencia,
            "iteracion": self.iter_actual,
        })

    def registrar_tarea(self, herramienta: str, estado, codigo_salida, latencia: float) -> None:
        self.tareas_runner.append({
            "herramienta": herramienta,
            "estado": estado,
            "codigo_salida": codigo_salida,
            "latencia": latencia,
            "iteracion": self.iter_actual,
        })

    def registrar_tareas_generadas(self, n: int) -> None:
        it = self.iteraciones.setdefault(self.iter_actual, {})
        it["tareas_generadas"] = it.get("tareas_generadas", 0) + n

    def registrar_decision_ia(self, continuar: bool, razon: str = "") -> None:
        it = self.iteraciones.setdefault(self.iter_actual, {})
        it["decision_ia"] = "continuar" if continuar else "terminar"
        it["razon_ia"] = razon or ""

    def registrar_decision_juez(self, aprueba: bool, razon: str = "") -> None:
        it = self.iteraciones.setdefault(self.iter_actual, {})
        it["decision_juez"] = "aprueba" if aprueba else "rechaza"
        it["razon_juez"] = razon or ""
        self.ultima_razon_juez = razon or ""

    def registrar_ingesta(self, crudo_acumulado: int, memoria_len: int) -> None:
        self.ingestas.append({
            "comando": len(self.ingestas) + 1,
            "crudo_acumulado": crudo_acumulado,
            "memoria_len": memoria_len,
        })

    def registrar_error(self, origen: str, detalle: str) -> None:
        self.errores.append({"origen": origen, "detalle": detalle})

    # --- resultado final ---

    def set_memoria_final(self, memoria: dict) -> None:
        self.memoria_final = memoria or {}

    def set_resultado(self, motivo: str, exito: bool) -> None:
        self.motivo_termino = motivo
        self.exito = exito

    def finalizar(self) -> None:
        if self.fin is None:
            self.fin = time.time()

    @property
    def duracion(self) -> float:
        return (self.fin or time.time()) - self.inicio


# --- gestión de la colección activa (sesión única) -------------------------

_activo: MetricsCollector | None = None
_instrumentado = False


def coleccion_activa() -> MetricsCollector | None:
    return _activo


def iniciar_coleccion(target: str, mision: str) -> MetricsCollector:
    """Arranca una colección nueva e instrumenta el cliente LLM (una vez)."""
    global _activo
    _activo = MetricsCollector(target=target, mision=mision)
    instrumentar_cliente()
    return _activo


def finalizar_coleccion() -> MetricsCollector | None:
    """Cierra la colección activa y la devuelve para generar el reporte."""
    global _activo
    col = _activo
    if col is not None:
        col.finalizar()
    _activo = None
    return col


def instrumentar_cliente() -> None:
    """Envuelve `_client.chat.completions.create` para medir tokens y latencia.

    Idempotente: solo parchea una vez. Cuando no hay colección activa, el wrapper
    se comporta exactamente como el original (no añade overhead observable).
    """
    global _instrumentado
    if _instrumentado:
        return

    from agents.base_agent import _client

    completions = _client.chat.completions
    original = completions.create

    def create_con_metricas(*args, **kwargs):
        col = coleccion_activa()
        if col is None:
            return original(*args, **kwargs)

        t0 = time.perf_counter()
        try:
            respuesta = original(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - la medición no debe ocultar el error
            col.registrar_error("llm", str(e))
            raise
        latencia = time.perf_counter() - t0

        messages = kwargs.get("messages") or (args[0] if args else None)
        agente = _clasificar_agente(messages)
        usage = getattr(respuesta, "usage", None)
        pt = getattr(usage, "prompt_tokens", 0) if usage else 0
        ct = getattr(usage, "completion_tokens", 0) if usage else 0
        col.registrar_llm(agente, pt, ct, latencia)
        return respuesta

    completions.create = create_con_metricas
    _instrumentado = True
