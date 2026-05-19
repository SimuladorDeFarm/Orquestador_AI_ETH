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
    "Debes encontrar la flag oculta en el sistema, tiene el formato de flag + llave + texto + cierre llave"
    "Por ahora solo está reconocimiento así que debes mandarlo a el a buscar la flag"
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

    N_COMMANDER = 100
    N_RECON = 100

    chat_commander = crear_chat(commander_client, SYSTEM_COMMANDER)
    chat_reconocimiento = crear_chat(recon_client, SYSTEM_RECONOCIMIENTO)

    prompt_commander = (
        f"Busca la flag oculta, en este caso es una carpeta secreta. Imagina que eres un pentester y haces un reconocimiento con las herramientas nmap y ffuf. "
        f"Solo se cuenta con la herramienta nmap y ffuf, no uses curl ni ningun otro comando. La ip objetivo es {target}."
    )

    i_commander = 0
    while i_commander < N_COMMANDER and not _cancelar:
        logs.append(f"[CICLO COMMANDER {i_commander + 1}]")

        if not esperar_confirmacion(f"Commander ciclo {i_commander + 1}: enviar prompt → {prompt_commander}"):
            logs.append("[Rechazado por el usuario — scan cancelado]")
            break

        respuesta_commander = preguntar(chat_commander, prompt_commander)
        mostrar("Commander", respuesta_commander)

        if not respuesta_commander:
            break

        logs.append(f"Commander: {extraer_mensaje(respuesta_commander)}")

        objetivo_commander = extraer_objetivo(respuesta_commander)
        contenido_commander = extraer_mensaje(respuesta_commander)

        if objetivo_commander == OBJETIVO_EXIT:
            logs.append("[Commander ha finalizado la sesión]")
            break

        if objetivo_commander in (OBJETIVO_RECONOCIMIENTO, None):
            prompt_recon = contenido_commander
            conclusiones_recon = prompt_recon

            i_recon = 0
            while i_recon < N_RECON and not _cancelar:
                logs.append(f"  [CICLO RECON {i_recon + 1}]")

                if not esperar_confirmacion(f"Recon ciclo {i_recon + 1}: ejecutar → {prompt_recon}"):
                    logs.append("  [Rechazado por el usuario — scan cancelado]")
                    _cancelar = True
                    break

                respuesta_recon = preguntar(chat_reconocimiento, prompt_recon)
                mostrar("Reconocimiento", respuesta_recon)

                if not respuesta_recon:
                    break

                objetivo_recon = extraer_objetivo(respuesta_recon)
                contenido_recon = extraer_mensaje(respuesta_recon)

                logs.append(f"  Recon: {contenido_recon}")

                if objetivo_recon in (OBJETIVO_EXIT, OBJETIVO_ORQUESTADOR):
                    conclusiones_recon = contenido_recon
                    break

                elif objetivo_recon == OBJETIVO_RECONOCIMIENTO:
                    output = ejecutar_en_docker(contenido_recon)
                    logs.append(f"  Docker output: {output.strip()}")
                    print(f"\n[Docker output]\n{output}")
                    prompt_recon = output

                else:
                    logs.append(f"  [!] Objetivo desconocido: '{objetivo_recon}'")
                    conclusiones_recon = contenido_recon
                    break

                i_recon += 1

            prompt_commander = conclusiones_recon

        i_commander += 1

    _en_curso = False
    status = "cancelled" if _cancelar else "finished"
    return {"status": status, "logs": logs}


def cancelar_scan():
    global _cancelar
    _cancelar = True
    # si está pausado esperando confirmación, lo desbloquea con rechazo
    responder_confirmacion(False)
    return {"status": "cancelling"}
