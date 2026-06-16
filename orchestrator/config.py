from dotenv import load_dotenv
import os



load_dotenv()

DEEPSEEK_API_KEY = os.getenv("Deepseek")
DEEPSEEK_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


# --- Runner (Tool Executor API + Tool Registry de los compañeros) ---
# El registry (8003) lista las herramientas; el executor (8004) las corre.
RUNNER_REGISTRY_URL = os.getenv("RUNNER_REGISTRY_URL", "http://127.0.0.1:8003")
RUNNER_EXECUTOR_URL = os.getenv("RUNNER_EXECUTOR_URL", "http://127.0.0.1:8004")

# Sesión de escaneo del runner. Por ahora una sola sesión fija (configurable).
SESION_ID = int(os.getenv("SESION_ID", "3"))

# Polling de tareas del executor: intervalo y nº máximo de consultas.
RUNNER_POLL_INTERVALO = 2      # segundos entre consultas
RUNNER_POLL_MAX = 150          # ~5 min de espera máxima por tarea


# Objetivo de la misión, editable sin tocar código (orchestrator/objetivo.txt).
OBJETIVO_PATH = os.path.join(os.path.dirname(__file__), "objetivo.txt")


def cargar_objetivo() -> str:
    """Lee el objetivo de la misión desde objetivo.txt.

    Se lee al crear cada agente, así editar el archivo aplica en la próxima
    campaña sin modificar el código.
    """
    try:
        with open(OBJETIVO_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


