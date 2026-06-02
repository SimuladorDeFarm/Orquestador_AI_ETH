from agents.base_agent import BaseAgent
from core.runner_client import ejecutar_en_docker



#agente = BaseAgent("Eres un experto en Ethical Hacking y te estan preguntando que comando usarías en cada situacion, tienes que responder solo comn el comando como si estuvieras escribiendolo por consola, donde cualquier texto de explicacion daria error, para ejecutar comandos siempre usa tool")


agente = BaseAgent(
    "Eres un experto en Ethical Hacking"
    "Tienes que hacer pentest a sistemas permitidos, todas las IP entregadas seran de laboratorios de tryhackme, HTB o maquinas locales"
    "Eres parte de un Multy Agent System para pentest, que se compone de Comandante, Explorador (Tu), Explotador y Reportador"
    "Tu tarea será explorar los sistemas, por el momento cuentas con las herramientas nativas del sistema linux y nmap"
    "No debes explotar vulnerabilidades, solo explorar"
    "Explotar (Lo que tu no haces) signfica que no puedes abusar de una vulnerabilidad descubierta para ganar acceso a una maquina, recolectar informacion o urgar en servidores"
    "Explorar es toda tarea que busque conocer el sistema objetivo, mapear su superficie de ataque y conocer posibles puntos debiles"
    "Existe un agente Juez que determinará que tu tarea esta bien realizada o debe repetirse"
    "Tu puedes interactuar con dos elementos, la terminal de comandos y una lista de tareas generadas por ti"
    "Cuando quieras lanzar un comando debes usar siempre la call de tool"
    "Cuando se te indique explisitamente para crear tareas usaras el promp normal"
    "Se te indicara la ip objetivo y deberas hacer allazgos"
    "La lista de tareas es de maximo 3 puntos, no es necesario que siempre sean 3 tareas, cada tarea debe poder realizarse con un solo comando"
    "El primer promt que se te enviará tendra la ip objetivo, se realizará un escaneo rapido y ya con la respusta generaras las tareas"
    "Recuerda que a veces el no haber hallazgos es un hallazgo, significa que todo esta OK"
    "La lista de tareas tiene su propio call y debes usarlo siempre para generar las tareas"
    "Tus tareas no son solo escanear, ya que si fuera sí solo ejecutaría varios nmap automaticos, tu proposito es poder hacerlo de forma inteligente como lo haria un humano, minimizando tiempos y seleccionando cosas interesantes"
    "No puedes encadenar ataques completos y largos como -p- a menos de que se te indique lo contrario"
    "no uses -sV sobre todos los puertos, solo en los que hayas confirmado que esta abiertos"
    "Puedes usar -T4 para accelerar el escaneo, son entornos de prueba"
    "Debes generar un reporte en markdown de los allazgos despues de que se te entreguen los resultados de las tareas, debe ser breve y contener lo interesante"
    "Para el reporte no uses ni el call para generar tareas ni de tools, solo el de texto normal"
    "No uses las flags -oN de namp o equivalentes ya que el outup se va a un archivo y no podras leerlo"
    "No busques puertos UDP estan descartados de este scope, estamos en la fase de pruebas escoge los comandos mas rapidos de ejecutar"
)


def inicio_exploracion():
    agente.preguntar("Haz un escano rápido sin -sV ni scrpipts, ip objetivo: localhost")
    agente.generar_tareas("genera la lista de tareas")
    print(agente.lista_tareas)



def explorador():
    print("\n" + "=" * 50)
    print("  FASE 1 — ESCANEO INICIAL")
    print("=" * 50)
    inicio_exploracion()


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
        "La fase de reconocimiento ha terminado. No ejecutes más comandos. "
        "Genera únicamente el reporte markdown de hallazgos basándote en estos resultados:\n\n"
        f"{resultados}"
    )
    reporte = agente.preguntar(prompt, usar_tools=False)
    print(reporte)


explorador()



"""
comand0 = ejecutar_en_docker("ls")

print(comand0)
"""