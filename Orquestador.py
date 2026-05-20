import subprocess
import threading
from google import genai
from google.api_core.exceptions import GoogleAPIError
from dotenv import load_dotenv
import os


load_dotenv()

commander_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
recon_client = genai.Client(api_key=os.getenv("ORQUESTADOR_API_KEY"))

NOMBRE_CONTENEDOR = "dazzling_mayer"

OBJETIVO_ORQUESTADOR = "orquestador"
OBJETIVO_RECONOCIMIENTO = "reconocimiento"
OBJETIVO_EXIT = "exit"

SYSTEM_COMMANDER = (
    "Eres el agente Commander de un sistema de ethical hacking automatizado. "
    "Recibes objetivos y asignas tareas generales a otros agentes. No generas comandos tú mismo. "
    "REGLA ESTRICTA DE FORMATO: cada respuesta tuya debe terminar obligatoriamente con ;reconocimiento, ;orquestador o ;exit. "
    "Ejemplo correcto: 'Escanea los puertos de localhost con las herramientas disponibles;reconocimiento'. (Esto es solo un ejemplo, no es el objetivo)"
    "Usa ;reconocimiento para delegar al agente de reconocimiento. "
    "Usa ;exit cuando el pentest haya concluido. "
    "Debes encontrar el puerto abierto en el sistema"
    "Por ahora solo está reconocimiento así que debes mandarlo a el a buscar l puerto"
    "No uses markdown, no uses listas, no uses saltos de línea. Una sola frase con la tarea y el ;objetivo al final."
)

SYSTEM_RECONOCIMIENTO = (
    "Eres el agente Reconocimiento de un sistema de ethical hacking automatizado. "
    "Ejecutas comandos de reconocimiento y analizas sus resultados. "
    "REGLA ESTRICTA DE FORMATO: cada respuesta tuya debe terminar obligatoriamente con ;reconocimiento o ;orquestador. "
    "Si necesitas ejecutar un comando responde SOLO con el comando y ;reconocimiento al final. "
    "Ejemplo: 'nmap -p- localhost;reconocimiento'. "
    "Si ya tienes conclusiones responde con un resumen minimalista (hallazgos y comandos ejecutados) y ;orquestador al final. "
    "No uses markdown. Hablas con otra IA, sé breve."
)

# Estado global del scan
_cancelar = False
_en_curso = False

# Estado de confirmación
_evento_confirmacion = threading.Event()
_confirmacion_aprobada = False
_accion_pendiente = ""
_esperando_confirmacion = False


def esperar_confirmacion(descripcion: str) -> bool:
    global _esperando_confirmacion, _accion_pendiente, _confirmacion_aprobada

    _accion_pendiente = descripcion
    _esperando_confirmacion = True
    _evento_confirmacion.clear()
    _evento_confirmacion.wait()  # el hilo se pausa aquí hasta que llegue respuesta
    _esperando_confirmacion = False

    return _confirmacion_aprobada


def responder_confirmacion(aprobado: bool):
    global _confirmacion_aprobada

    _confirmacion_aprobada = aprobado
    _evento_confirmacion.set()  # desbloquea el hilo pausado


def crear_chat(client, system_prompt):
    return client.chats.create(
        model="gemini-2.5-flash",
        config={"system_instruction": system_prompt},
    )


def preguntar(chat, mensaje):
    try:
        response = chat.send_message(mensaje)
        return response.text.strip()
    except GoogleAPIError as e:
        print(f"[ERROR API Gemini] {e}")
        return None


def extraer_objetivo(respuesta):
    partes = respuesta.rsplit(";", 1)
    if len(partes) == 2:
        return partes[1].strip().lower()
    return None


def extraer_mensaje(respuesta):
    return respuesta.rsplit(";", 1)[0].strip()


def mostrar(agente, respuesta):
    if respuesta:
        separador = "=" * 40
        print(f"\n{separador}")
        print(f"  {agente.upper()}")
        print(separador)
        print(extraer_mensaje(respuesta))


def ejecutar_en_docker(comando):
    cmd = ["docker", "exec", NOMBRE_CONTENEDOR] + comando.split()
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode == 0:
        return resultado.stdout
    else:
        return resultado.stderr


def iniciar_scan(target: str) -> dict:
    global _cancelar, _en_curso

    _cancelar = False
    _en_curso = True
    logs = []

    chats = {
        OBJETIVO_RECONOCIMIENTO: crear_chat(recon_client, SYSTEM_RECONOCIMIENTO),
        "commander": crear_chat(commander_client, SYSTEM_COMMANDER),
    }

    estado = "commander"
    mensaje = (
        f"Busca el puerto abierto. Imagina que eres un pentester y haces un reconocimiento con las herramientas nmap y ffuf. "
        f"Solo se cuenta con la herramienta nmap y ffuf, no uses curl ni ningun otro comando. La ip objetivo es {target}."
    )

    while estado != OBJETIVO_EXIT and not _cancelar:
        logs.append(f"[{estado.upper()}] {mensaje}")

        if not esperar_confirmacion(f"{estado.capitalize()}: → {mensaje}"):
            logs.append("[Rechazado por el usuario — scan cancelado]")
            break

        respuesta = preguntar(chats[estado], mensaje)
        mostrar(estado, respuesta)

        if not respuesta:
            break

        objetivo = extraer_objetivo(respuesta)
        contenido = extraer_mensaje(respuesta)
        logs.append(f"  respuesta: {contenido} → próximo: {objetivo}")

        if estado == "commander":
            if objetivo == OBJETIVO_EXIT:
                logs.append("[Commander ha finalizado la sesión]")
                estado = OBJETIVO_EXIT

            elif objetivo == OBJETIVO_RECONOCIMIENTO:
                estado = OBJETIVO_RECONOCIMIENTO
                mensaje = contenido

        elif estado == OBJETIVO_RECONOCIMIENTO:
            if objetivo == OBJETIVO_RECONOCIMIENTO:
                # el agente recon pide ejecutar un comando
                output = ejecutar_en_docker(contenido)
                logs.append(f"  docker: {output.strip()}")
                print(f"\n[Docker output]\n{output}")
                mensaje = output
                # se queda en reconocimiento con el output como nuevo mensaje

            elif objetivo == OBJETIVO_ORQUESTADOR:
                # recon terminó, devuelve conclusiones al commander
                estado = "commander"
                mensaje = contenido

            else:
                logs.append(f"  [!] Objetivo desconocido: '{objetivo}'")
                break

    _en_curso = False
    status = "cancelled" if _cancelar else "finished"
    return {"status": status, "logs": logs}


def cancelar_scan():
    global _cancelar
    _cancelar = True
    # si está pausado esperando confirmación, lo desbloquea con rechazo
    responder_confirmacion(False)
    return {"status": "cancelling"}
