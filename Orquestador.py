import subprocess
from google import genai
from google.api_core.exceptions import GoogleAPIError
from dotenv import load_dotenv
import os


#Carga las variables de entorno
load_dotenv()

#Guarda las apy keys en una variable
commander_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
recon_client = genai.Client(api_key=os.getenv("ORQUESTADOR_API_KEY"))

# Prepara contenedor docker
NOMBRE_CONTENEDOR = "dazzling_mayer"
MAX_CICLOS = 2

#Posibles objetivos
OBJETIVO_ORQUESTADOR = "orquestador"
OBJETIVO_RECONOCIMIENTO = "reconocimiento"
OBJETIVO_EXIT = "exit"

# pront inicial del commander
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

# Pront inicial de reconocimiento
SYSTEM_RECONOCIMIENTO = (
    "Eres el agente Reconocimiento de un sistema de ethical hacking automatizado. "
    "Ejecutas comandos de reconocimiento y analizas sus resultados. "
    "REGLA ESTRICTA DE FORMATO: cada respuesta tuya debe terminar obligatoriamente con ;reconocimiento o ;orquestador. "
    "Si necesitas ejecutar un comando responde SOLO con el comando y ;reconocimiento al final. "
    "Ejemplo: 'nmap -p- localhost;reconocimiento'. "
    "Si ya tienes conclusiones responde con un resumen minimalista (hallazgos y comandos ejecutados) y ;orquestador al final. "
    "No uses markdown. Hablas con otra IA, sé breve."
)


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

# Separa el promp del objetivo al que le habla
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


def confirmar(accion):
    respuesta = input(f"\n[?] {accion} [Y/n]: ").strip().lower()
    return respuesta in ("y", "")


def ejecutar_en_docker(comando):
    cmd = ["docker", "exec", NOMBRE_CONTENEDOR] + comando.split()
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode == 0:
        return resultado.stdout
    else:
        return resultado.stderr


if __name__ == "__main__":

    # Máximo de ciclos por cada agente (modificar según necesidad)
    N_COMMANDER = 100
    N_RECON = 100

    # Crea un chat con cada IA
    chat_commander = crear_chat(commander_client, SYSTEM_COMMANDER)
    chat_reconocimiento = crear_chat(recon_client, SYSTEM_RECONOCIMIENTO)

    # Prompt inicial del Commander (se envía en el primer ciclo)
    prompt_commander = (
        "Busca la flag oculta, en este caso es una carpeta secreta. Imagina que eres un pentester y haces un reconocimiento con las herramientas nmap y ffuf"
        "Solo se cuenta con la herramienta nmap, ffuf, no uses curl ni ningun otro comando. La ip objetivo es localhost."
    )

    i_commander = 0
    while i_commander < N_COMMANDER:
        print(f"\n{'#' * 40}")
        print(f"  CICLO COMMANDER {i_commander + 1}/{N_COMMANDER}")
        print(f"{'#' * 40}")

        if not confirmar(f"Enviar prompt a Commander (ciclo {i_commander + 1})"):
            print("[Cancelado por el usuario]")
            break

        respuesta_commander = preguntar(chat_commander, prompt_commander)
        mostrar("Commander", respuesta_commander)

        if not respuesta_commander:
            break

        objetivo_commander = extraer_objetivo(respuesta_commander)
        contenido_commander = extraer_mensaje(respuesta_commander)

        if objetivo_commander == OBJETIVO_EXIT:
            print("\n[Commander ha finalizado la sesión]\n")
            break

        # Ciclo interno de reconocimiento
        if objetivo_commander in (OBJETIVO_RECONOCIMIENTO, None):
            prompt_recon = contenido_commander
            conclusiones_recon = prompt_recon  # fallback si no hay ciclos

            i_recon = 0
            while i_recon < N_RECON:
                print(f"\n  --- Ciclo recon {i_recon + 1}/{N_RECON} ---")

                if not confirmar(f"Enviar prompt a Reconocimiento (ciclo {i_recon + 1})"):
                    print("[Cancelado por el usuario]")
                    break

                respuesta_recon = preguntar(chat_reconocimiento, prompt_recon)
                mostrar("Reconocimiento", respuesta_recon)

                if not respuesta_recon:
                    break

                objetivo_recon = extraer_objetivo(respuesta_recon)
                contenido_recon = extraer_mensaje(respuesta_recon)

                if objetivo_recon in (OBJETIVO_EXIT, OBJETIVO_ORQUESTADOR):
                    conclusiones_recon = contenido_recon
                    break

                elif objetivo_recon == OBJETIVO_RECONOCIMIENTO:
                    output = ejecutar_en_docker(contenido_recon)
                    print(f"\n[Docker output]\n{output}")
                    prompt_recon = output  # output del comando es el siguiente prompt

                else:
                    print(f"[!] Objetivo desconocido: '{objetivo_recon}'")
                    conclusiones_recon = contenido_recon
                    break

                i_recon += 1

            # Las conclusiones del recon son el siguiente prompt del Commander
            prompt_commander = conclusiones_recon

        i_commander += 1
