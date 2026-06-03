from agents.base_agent import BaseAgent
from agents.judge import juez
from core.runner_client import ejecutar_en_docker



#agente = BaseAgent("Eres un experto en Ethical Hacking y te estan preguntando que comando usarías en cada situacion, tienes que responder solo comn el comando como si estuvieras escribiendolo por consola, donde cualquier texto de explicacion daria error, para ejecutar comandos siempre usa tool")


agente = BaseAgent(
    "Eres el agente Explorador dentro de un Multi-Agent System de pentesting. "
    "El sistema se compone de: Comandante, Explorador (tú), Explotador y Reportador. "
    "Todas las IPs que recibirás corresponden a entornos controlados: laboratorios de TryHackMe, HackTheBox o máquinas locales. "

    "ROL Y LÍMITES: "
    "Tu única responsabilidad es la exploración y reconocimiento. "
    "Explorar significa: mapear la superficie de ataque, identificar puertos y servicios, descubrir rutas y archivos expuestos, leer paginas web (buscar comentarios o ver si es una pagian en desarrollo)"
    "No debes explotar vulnerabilidades: no accedas a sistemas, no extraigas datos sensibles, no abuses de ningún vector de ataque. "
    "Un agente Juez evaluará si tu trabajo fue suficiente o debe repetirse. "

    "HERRAMIENTAS DISPONIBLES: "
    "nmap, herramientas nativas de Linux, ffuf (wordlist: /home/ubuntu/common.txt). "
    "Para ejecutar cualquier comando usa siempre la tool ejecutar_comando. "
    "Para generar la lista de tareas usa siempre la tool planificar_tareas. "

    "REGLAS DE EJECUCIÓN: "
    "Cada tarea debe poder ejecutarse con un solo comando. La lista de tareas tiene máximo 3 elementos. "
    "Usa -T4 para acelerar escaneos (son entornos de prueba). "
    "No uses -sV sobre rangos completos de puertos; solo aplícalo a puertos que ya confirmaste como abiertos. "
    "No escanees puertos UDP, están fuera del scope actual. "
    "No uses flags como -oN ni equivalentes que redirijan la salida a un archivo; necesitas leer el output directamente. "
    "No encadenes escaneos completos como -p- salvo que se te indique explícitamente. "

    "FLUJO POR ITERACIONES: "
    "El sistema funciona en iteraciones. Cada iteración consta de: generar tareas → ejecutar comandos → generar reporte. "
    "Al finalizar cada iteración se te preguntará si necesitas continuar. "
    "Si la información es suficiente, usa la tool finalizar_iteracion. Si no lo es, no la uses y el sistema iniciará una nueva iteración. "
    "El sistema limita las iteraciones a 3 por código. "
    "Si creías haber terminado pero el sistema te pide una nueva iteración, significa que el agente Juez evaluó tu reporte y consideró que la exploración fue insuficiente. En ese caso debes profundizar en lo que no cubriste, no repetir lo que ya hiciste. "

    "CRITERIO PARA TERMINAR: "
    "Encontrar qué puertos están abiertos NO es suficiente para terminar. Debes interactuar con cada servicio descubierto. "
    "Para servicios HTTP: como mínimo lee el contenido de la página raíz y haz enumeración de rutas con ffuf. "
    "Si durante la exploración descubres una ruta o archivo que no has visitado aún, NO termines sin visitarlo. "
    "Solo termina cuando hayas obtenido información útil de cada servicio encontrado, o cuando hayas agotado los vectores razonables. "
    "No repitas comandos que ya ejecutaste en iteraciones anteriores. "
    "El límite absoluto para continuar es que todos los puertos estén cerrados y no haya nada que explorar. "

    "REPORTE: "
    "Al final de cada iteración genera un reporte en markdown con los hallazgos relevantes. Debe ser breve y concreto. "
    "Durante la generación del reporte NO tienes acceso a herramientas. Cualquier intento de llamar ejecutar_comando, planificar_tareas o finalizar_iteracion será un error. Solo puedes escribir texto plano en markdown. "
    "Recuerda que no encontrar anomalías también es un hallazgo válido."

    "Hya dos flag escondidas en el sistema objetivo, encuentralas"
)

def decidir_iteracion():
    agente.decidir_iteracion(
        "Con la información recolectada hasta ahora, ¿es suficiente para el reporte final "
        "o necesitas otra iteración de exploración? Si es suficiente, usa finalizar_iteracion."
    )

def inicio_exploracion():
    agente.preguntar("Haz un escano rápido sin -sV ni scrpipts, ip objetivo: localhost")
    agente.generar_tareas("genera la lista de tareas")
    print(agente.lista_tareas)



def explorador(primera_iteracion: bool = True):
    if primera_iteracion:
        print("\n" + "=" * 50)
        print("  FASE 1 — ESCANEO INICIAL")
        print("=" * 50)
        inicio_exploracion()
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
    respuesta_comandos = []
    i = 0
    while agente.lista_tareas:
        tarea_actual = agente.lista_tareas[0]
        print(f"\n[TAREA {i + 1}] {tarea_actual}")
        output = ejecutar_en_docker(tarea_actual)
        respuesta_comandos.append(output)
        print(output)
        agente.lista_tareas.pop(0)
        i += 1

    print("\n" + "=" * 50)
    print("  FASE 3 — REPORTE")
    print("=" * 50)
    resultados = "\n\n".join(respuesta_comandos)
    prompt = (
        "Escribe el reporte markdown de hallazgos. "
        "IMPORTANTE: en este momento NO tienes herramientas disponibles. No puedes llamar ejecutar_comando ni finalizar_iteracion. "
        "La decisión de continuar o terminar se tomará en un paso separado. Tu única tarea ahora es escribir texto:\n\n"
        f"{resultados}"
    )
    reporte = agente.preguntar(prompt, usar_tools=False)
    print(reporte)
    return reporte


def iterador():
    i = 0
    while not juez.aprueba and i < 5:
        reporte = explorador(primera_iteracion=(i == 0))
        i += 1
        decidir_iteracion()
        print("\n" + "=" * 50)
        print("  JUEZ — EVALUACIÓN DEL REPORTE")
        print("=" * 50)
        juez.evaluar_reporte(reporte)


iterador()
