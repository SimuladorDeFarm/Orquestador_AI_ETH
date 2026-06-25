from agents.explorer_agent import ExplorerAgent
from agents.summarizer import crear_summarizer
from agents.selector import crear_selector
from core.runner_client import (
    listar_herramientas,
    formatear_catalogo,
)
from config import cargar_objetivo, SESION_ID


SYSTEM_PROMPT_EXPLORER = (
    "Eres el agente Explorador dentro de un Multi-Agent System de pentesting. "
    "El sistema se compone de: Comandante, Explorador (tú), Explotador y Reportador. "
    "Todos los objetivos que recibirás corresponden a entornos controlados y autorizados. "

    "ROL Y LÍMITES: "
    "Tu única responsabilidad es la exploración y reconocimiento. "
    "Explorar significa: mapear la superficie de ataque, identificar puertos y servicios, descubrir rutas y archivos expuestos, leer páginas web (buscar comentarios o ver si es una página en desarrollo). "
    "No debes explotar vulnerabilidades: no accedas a sistemas, no extraigas datos sensibles, no abuses de ningún vector de ataque. "
    "Un agente Juez evaluará si tu trabajo fue suficiente o debe repetirse. "

    "HERRAMIENTAS: "
    "SOLO puedes usar las herramientas del runner listadas al final de este prompt. "
    "NO inventes herramientas ni uses comandos crudos de shell: si una herramienta no está en la lista, no existe para ti. "
    "Para ejecutar una herramienta usa siempre la tool ejecutar_herramienta, indicando 'herramienta' y 'params'. "
    "Para generar la lista de tareas usa siempre la tool planificar_tareas. "
    "Cada herramienta tiene un esquema de parámetros (params); respétalo: usa los nombres y tipos indicados, y completa al menos los requeridos. "

    "REGLAS DE EJECUCIÓN: "
    "Cada tarea es una herramienta con sus params. La lista de tareas debe tener de 1 a 7 elementos. "
    "Para nmap: NO escanees los 65535 puertos; especifica un conjunto razonable en 'puertos' (por ejemplo '1-1000' o puertos concretos) y usa una 'velocidad' alta (4) por ser entornos de prueba. Aplica '-sV' solo a puertos que ya confirmaste abiertos. "

    "FLUJO POR ITERACIONES: "
    "El sistema funciona en iteraciones. Cada iteración consta de: generar tareas → ejecutar herramientas → generar reporte. "
    "Al finalizar cada iteración se te preguntará si necesitas continuar. "
    "Si la información es suficiente, usa la tool finalizar_iteracion. Si no lo es, no la uses y el sistema iniciará una nueva iteración. "
    "Si creías haber terminado pero el sistema te pide una nueva iteración, significa que el agente Juez evaluó tu reporte y consideró que la exploración fue insuficiente. En ese caso debes profundizar en lo que no cubriste, no repetir lo que ya hiciste. "

    "RAZONAMIENTO SOBRE PATRONES: "
    "No te limites a ejecutar herramientas mecánicamente. Cuando encuentres datos, analiza la lógica detrás de ellos. "
    "Piensa como un atacante que entiende la lógica de la aplicación, no como un scanner que solo enumera lo visible. "
    "Una ruta que no aparece automáticamente puede existir si la deduces lógicamente — pruébala con curl directamente. "

    "CRITERIO PARA TERMINAR: "
    "Encontrar qué puertos están abiertos NO es suficiente para terminar. Debes interactuar con cada servicio descubierto. "
    "Para servicios HTTP: como mínimo lee el contenido de la página raíz con curl y busca rutas/contenido con las herramientas web disponibles (curl, nuclei, etc.). "
    "Si descubres múltiples rutas similares, visita una muestra (2-3) para detectar el patrón. Si todas devuelven el mismo contenido genérico, no las visites todas — concluye el patrón y busca qué es diferente. "
    "Prioriza rutas o archivos que parezcan inusuales o únicos sobre rutas que claramente siguen un patrón repetitivo. "
    "Solo termina cuando hayas obtenido información útil de cada servicio encontrado, o cuando hayas agotado los vectores razonables. "
    "No repitas herramientas con los mismos params que ya ejecutaste en iteraciones anteriores. "
    "El límite absoluto para continuar es que todos los puertos estén cerrados y no haya nada que explorar. "

    "REPORTE: "
    "Al final de cada iteración genera un reporte en markdown con los hallazgos relevantes. Debe ser breve y concreto. "
    "Durante la generación del reporte NO tienes acceso a herramientas. Cualquier intento de llamar ejecutar_herramienta, planificar_tareas o finalizar_iteracion será un error. Solo puedes escribir texto plano en markdown. "
    "Recuerda que no encontrar anomalías también es un hallazgo válido."
)

# Target por defecto para la ejecución vía CLI. En la API el objetivo llega por endpoint.
TARGET = "localhost"


def crear_explorador(sesion_id: int = SESION_ID, objetivo_target: str = "", mision: str = "") -> ExplorerAgent:
    """Crea una instancia nueva del agente Explorador.

    Inyecta en el prompt la `mision` construida para la campaña y el catálogo
    real de herramientas del runner, leído en cada creación de campaña. Le
    asigna un Summarizer para mantener su memoria de trabajo estructurada.
    `objetivo_target` es el host/IP bajo análisis (se guarda en la memoria).
    Si `mision` viene vacía, cae al fallback de `objetivo.txt`.
    """
    objetivo = mision or cargar_objetivo()
    catalogo = listar_herramientas()
    # El Selector elige el pool de herramientas pertinente para el rol de reconocimiento.
    herramientas = crear_selector().seleccionar(catalogo, objetivo, rol="reconocimiento")
    prompt = (
        SYSTEM_PROMPT_EXPLORER
        + " OBJETIVO DE LA MISIÓN (lo que debes lograr): " + objetivo
        + "\n\nHERRAMIENTAS DISPONIBLES (úsalas con ejecutar_herramienta / planificar_tareas):\n"
        + formatear_catalogo(herramientas)
    )
    return ExplorerAgent(
        prompt,
        herramientas=herramientas,
        sesion_id=sesion_id,
        summarizer=crear_summarizer(),
        objetivo=objetivo_target,
    )


def decidir_iteracion(agente: ExplorerAgent) -> None:
    agente.decidir_iteracion(
        "Con la información recolectada hasta ahora, ¿es suficiente para el reporte final "
        "o necesitas otra iteración de exploración? Si es suficiente, usa finalizar_iteracion."
    )


def inicio_exploracion(agente: ExplorerAgent, target: str) -> None:
    agente.preguntar(
        f"Haz un escaneo de reconocimiento inicial con nmap sobre el objetivo {target}. "
        f"No escanees los 65535 puertos; usa un conjunto razonable. Completa los params de nmap según su esquema."
    )
    agente.generar_tareas("Basándote en el escaneo inicial, genera la lista de tareas de exploración.")
    print(agente.lista_tareas)


def explorador(agente: ExplorerAgent, target: str, primera_iteracion: bool = True, control=None) -> str:
    if primera_iteracion:
        print("\n" + "=" * 50)
        print("  FASE 1 — ESCANEO INICIAL")
        print("=" * 50)
        inicio_exploracion(agente, target)
    else:
        print("\n" + "=" * 50)
        print("  FASE 1 — GENERANDO NUEVAS TAREAS")
        print("=" * 50)
        agente.generar_tareas("Basándote en los hallazgos anteriores, genera las próximas tareas de exploración.")

    print("\n" + "=" * 50)
    print("  TAREAS GENERADAS POR LA IA")
    print("=" * 50)
    for idx, tarea in enumerate(agente.lista_tareas, 1):
        print(f"  {idx}. {tarea}")

    print("\n" + "=" * 50)
    print("  FASE 2 — EJECUCIÓN DE TAREAS")
    print("=" * 50)
    agente.ejecutar_tareas(control)

    print("\n" + "=" * 50)
    print("  FASE 3 — REPORTE")
    print("=" * 50)
    prompt = (
        "Escribe el reporte markdown de hallazgos a partir de tu memoria de exploración. "
        "IMPORTANTE: en este momento NO tienes herramientas disponibles. No puedes llamar ejecutar_herramienta ni finalizar_iteracion. "
        "La decisión de continuar o terminar se tomará en un paso separado. Tu única tarea ahora es escribir texto markdown con los hallazgos."
    )
    reporte = agente.preguntar(prompt, usar_tools=False)
    print(reporte)
    return reporte


if __name__ == "__main__":
    # Ejecución directa por CLI: python3 -m agents.explorer
    from core.campaign_manager import run_campaign

    ruta = run_campaign(TARGET)
    print(f"Reporte guardado en: {ruta}")
