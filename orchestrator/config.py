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

# --- CORS ---
# Orígenes del frontend autorizados a llamar a esta API desde el navegador.
# Sin esto, el navegador bloquea las respuestas (aunque el servidor responda 200)
# porque el frontend manda 'Authorization: Bearer <token>' desde otro origen.
# Lista separada por comas; default: los puertos típicos de Vite en desarrollo.
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]

# Polling de tareas del executor: intervalo y nº máximo de consultas.
RUNNER_POLL_INTERVALO = 2      # segundos entre consultas
RUNNER_POLL_MAX = 150          # ~5 min de espera máxima por tarea


# Objetivo de la misión, editable sin tocar código (orchestrator/objetivo.txt).
OBJETIVO_PATH = os.path.join(os.path.dirname(__file__), "objetivo.txt")


def cargar_objetivo() -> str:
    """[DEPRECADA] Lee el objetivo de la misión desde objetivo.txt.

    El flujo normal ya no depende de este archivo: la misión se ensambla en
    tiempo de ejecución con `construir_mision()` a partir de los parámetros que
    el frontend envía a POST /campaign/start. Se mantiene solo como override
    manual de emergencia.
    """
    try:
        with open(OBJETIVO_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


# --- Construcción dinámica de la misión -----------------------------------
# Los bloques se copian verbatim de Docs/prompts_mision.md. No parafrasear.

FLAG_FORMAT_DEFAULT = "FLAG{...}"

_BLOQUE_BASE = """\
Eres un agente de ethical hacking profesional operando sobre un entorno
EXPLÍCITAMENTE AUTORIZADO. Tu objetivo es evaluar la seguridad del siguiente host:

HOST OBJETIVO: {target}

Debes operar en modalidad black box: no tienes información previa sobre el objetivo.
Construye tu comprensión desde cero usando las herramientas disponibles.
Cada acción que realices debe justificarse por la misión definida a continuación."""

_BLOQUES_MODO = {
    "solo_reconocimiento": """\
=== MODO DE OPERACIÓN: SOLO RECONOCIMIENTO ===

Tu misión se limita ESTRICTAMENTE a recopilar información del objetivo.
Debes identificar puertos abiertos, servicios activos, versiones de software,
tecnologías en uso, subdominios, rutas web accesibles y banners de servicio.

PROHIBIDO ABSOLUTAMENTE en este modo:
- Intentar explotar ninguna vulnerabilidad, aunque sea obvia.
- Ejecutar payloads, shellcodes, exploits o cualquier código ofensivo.
- Modificar, crear o eliminar archivos en el objetivo.
- Realizar acciones que puedan interrumpir o degradar servicios del objetivo.
- Autenticarte usando credenciales encontradas (solo reportarlas).

El producto de tu trabajo es un mapa detallado de la superficie de ataque.
No tomes ninguna acción ofensiva bajo ninguna circunstancia.""",
    "reconocimiento_vulnerabilidades": """\
=== MODO DE OPERACIÓN: RECONOCIMIENTO Y ANÁLISIS DE VULNERABILIDADES ===

Tu misión tiene dos fases que debes ejecutar en orden:

FASE 1 — RECONOCIMIENTO:
Identifica puertos abiertos, servicios activos, versiones de software,
tecnologías en uso, subdominios, rutas web accesibles y banners de servicio.

FASE 2 — ANÁLISIS DE VULNERABILIDADES:
Sobre la superficie de ataque mapeada en la Fase 1, detecta y documenta
vulnerabilidades conocidas (CVEs), configuraciones inseguras, servicios
desactualizados y posibles vectores de ataque. Usa herramientas de análisis
como nuclei, nikto u otras disponibles en el runner.

PROHIBIDO ABSOLUTAMENTE en este modo:
- Intentar explotar ninguna vulnerabilidad detectada, aunque tengas el vector claro.
- Ejecutar payloads, shellcodes, exploits o cualquier código ofensivo activo.
- Modificar, crear o eliminar archivos en el objetivo.
- Autenticarte usando credenciales encontradas (solo reportarlas).
- Realizar acciones que puedan interrumpir o degradar servicios.

El producto de tu trabajo es un informe de superficie de ataque con
vulnerabilidades priorizadas. La explotación no forma parte de tu misión.""",
    "reconocimiento_explotacion": """\
=== MODO DE OPERACIÓN: RECONOCIMIENTO Y EXPLOTACIÓN ===

Tu misión es un ciclo completo de prueba de penetración. Debes ejecutar
las siguientes fases en orden:

FASE 1 — RECONOCIMIENTO:
Identifica puertos abiertos, servicios activos, versiones de software,
tecnologías en uso, subdominios, rutas web accesibles y banners de servicio.

FASE 2 — ANÁLISIS DE VULNERABILIDADES:
Detecta y documenta vulnerabilidades conocidas (CVEs), configuraciones inseguras
y vectores de ataque concretos sobre la superficie mapeada.

FASE 3 — EXPLOTACIÓN:
Explota activamente los vectores de ataque identificados para demostrar su
impacto real. Documenta cada explotación con evidencia concreta (output de
herramientas, capturas de respuesta, datos accedidos). Prioriza los vectores
de mayor impacto. Si una explotación falla, continúa con el siguiente vector
sin abandonar la misión.

IMPORTANTE: Cada acción ofensiva debe estar precedida por la justificación
de qué vulnerabilidad estás explotando y por qué es el siguiente paso lógico.
El objetivo es demostrar impacto real, no simplemente detectar problemas.""",
}

_BLOQUES_PROFUNDIDAD = {
    "superficial": """\
=== PROFUNDIDAD: SUPERFICIAL ===

Opera con los siguientes límites:
- Máximo de iteraciones del Explorer: 2.
- Usa únicamente herramientas rápidas y de bajo impacto (nmap con timing T3 o menor,
  escaneos de puertos comunes, sin fuerza bruta).
- Prioriza cobertura sobre profundidad: identifica lo más relevante rápidamente.
- No realices escaneos completos de los 65535 puertos.
- No ejecutes herramientas que tarden más de 2 minutos por tarea.
- El Judge debe aprobar con hallazgos básicos; no es necesaria cobertura exhaustiva.""",
    "estandar": """\
=== PROFUNDIDAD: ESTÁNDAR ===

Opera con los siguientes límites:
- Máximo de iteraciones del Explorer: 5.
- Puedes usar el rango completo de herramientas disponibles en el runner.
- Balancea cobertura y profundidad: escanea los puertos más comunes primero,
  luego profundiza en los servicios que muestren mayor superficie de ataque.
- El Judge debe aprobar cuando hayas cubierto los servicios principales con
  suficiente detalle para tomar decisiones informadas.""",
    "exhaustivo": """\
=== PROFUNDIDAD: EXHAUSTIVO ===

Opera sin límite práctico de iteraciones (máximo interno del sistema).
- Usa todas las herramientas disponibles en el runner que sean relevantes.
- Escanea el rango completo de puertos (1-65535).
- Profundiza en cada servicio encontrado hasta agotar los vectores identificables.
- Usa fuerza bruta de directorios, subdominios y credenciales donde sea pertinente.
- El Judge solo debe aprobar cuando la cobertura sea exhaustiva: no quedan
  servicios sin analizar, no quedan vectores identificados sin explorar.
- Prioriza completitud sobre velocidad.""",
}

_BLOQUE_RESTRICCION_NO_PIVOTING = """\
=== RESTRICCIÓN OBLIGATORIA: SIN PIVOTING ===

PROHIBIDO ABSOLUTAMENTE realizar pivoting hacia otras máquinas o redes.
Tu scope está restringido exclusivamente al host {target}.
Si durante la explotación obtienes acceso a credenciales, claves SSH, tokens
o cualquier material que permita acceder a otros sistemas, DEBES REPORTARLO
pero NO utilizarlo para acceder a dichos sistemas.
Cualquier intento de movimiento lateral o acceso a hosts distintos de {target}
constituye una violación del scope autorizado. Esta restricción no tiene excepciones."""

_BLOQUE_RESTRICCION_CTF = """\
=== OBJETIVO ESPECIAL: CAPTURA DE FLAG (CTF) ===

Además de tu misión principal, debes localizar y capturar una flag oculta
en el sistema objetivo. El formato de la flag es: {flag_format}

Busca la flag en ubicaciones típicas: archivos del sistema, variables de entorno,
bases de datos, respuestas HTTP, comentarios en código fuente, metadatos,
directorios ocultos y cualquier lugar donde pueda estar almacenada.

OBLIGATORIO: Cuando encuentres una cadena que coincida con el formato
{flag_format}, debes:
1. Reportar el valor exacto de la flag.
2. Reportar la ruta o ubicación exacta donde fue encontrada.
3. Reportar el método utilizado para obtenerla.

Encontrar la flag es un criterio de éxito de la misión. El Judge debe
considerar la campaña exitosa solo si la flag fue encontrada y reportada."""

_BLOQUE_RESTRICCION_CRITICOS = """\
=== RESTRICCIÓN OBLIGATORIA: SERVICIOS CRÍTICOS SOLO EN MODO REPORTE ===

Si identificas servicios críticos (bases de datos en producción, servicios
de autenticación central, sistemas de backup, servicios industriales/SCADA,
infraestructura de red como firewalls o switches), debes aplicar la siguiente
política sin excepción:

- PERMITIDO: Identificar, escanear y documentar el servicio y sus vulnerabilidades.
- PROHIBIDO: Explotar activamente dichas vulnerabilidades en servicios críticos.

Se consideran críticos: MySQL/PostgreSQL/MSSQL expuestos, LDAP/Active Directory,
servicios en puertos 443, 22 con credenciales válidas, cualquier servicio cuya
interrupción pueda afectar a usuarios reales.

Documenta el vector con suficiente detalle para que un equipo humano pueda
reproducir la explotación de forma controlada. No lo ejecutes tú."""

_BLOQUE_RESTRICCION_STEALTH = """\
=== RESTRICCIÓN OBLIGATORIA: MODO SIGILOSO (STEALTH) ===

Debes minimizar el ruido generado en el objetivo para evitar detección por
sistemas de seguridad (IDS/IPS, SIEM, alertas de firewall). Aplica:

- Usa timing lento en nmap (T1 o T2 máximo). Nunca T4 o T5.
- Evita escaneos masivos de puertos en ráfagas rápidas; fragmenta las consultas.
- Prefiere herramientas pasivas sobre activas cuando ambas sirvan.
- No uses herramientas de fuerza bruta con alta concurrencia.
- Introduce pausas entre tareas cuando el runner lo permita.
- Evita repetir la misma consulta más de una vez al mismo servicio.
- Si una herramienta genera mucho tráfico por diseño, evalúa si es imprescindible
  antes de usarla; si no lo es, descártala.

El objetivo es obtener la máxima información con el menor rastro posible."""

_BLOQUE_CIERRE = """\
=== INSTRUCCIONES FINALES PARA TODOS LOS AGENTES ===

1. PRIORIDAD DE RESTRICCIONES: Las restricciones marcadas con
   "PROHIBIDO ABSOLUTAMENTE" o "RESTRICCIÓN OBLIGATORIA" tienen prioridad
   sobre cualquier otra consideración. No las ignores aunque el contexto
   parezca justificarlo.

2. REPORTE DE HALLAZGOS: Todo hallazgo debe incluir: qué se encontró,
   cómo se encontró (herramienta + parámetros), y cuál es su impacto potencial.

3. CONTINUIDAD: Si una herramienta falla o no devuelve resultados, continúa
   con la siguiente tarea planificada. No detengas la campaña por errores
   individuales.

4. CRITERIO DE ÉXITO: La campaña es exitosa cuando el Judge confirma que
   se ha cubierto el scope definido por el modo y la profundidad seleccionados,
   y todas las restricciones activas han sido respetadas."""


def construir_mision(
    target: str,
    modo: str = "solo_reconocimiento",
    profundidad: str = "estandar",
    restricciones: dict | None = None,
) -> str:
    """Ensambla el prompt de misión a partir de los parámetros de la campaña.

    Orden de los bloques: BASE → MODO → PROFUNDIDAD → RESTRICCIONES activas →
    CIERRE. `restricciones` es un dict con las claves no_pivoting, modo_ctf,
    flag_format, solo_reportar_criticos y stealth (igual que el submodelo del
    endpoint). Los bloques desconocidos caen al default correspondiente.
    """
    restricciones = restricciones or {}
    flag_format = (restricciones.get("flag_format") or "").strip() or FLAG_FORMAT_DEFAULT

    bloques: list[str] = [_BLOQUE_BASE]
    bloques.append(_BLOQUES_MODO.get(modo, _BLOQUES_MODO["solo_reconocimiento"]))
    bloques.append(_BLOQUES_PROFUNDIDAD.get(profundidad, _BLOQUES_PROFUNDIDAD["estandar"]))

    if restricciones.get("no_pivoting"):
        bloques.append(_BLOQUE_RESTRICCION_NO_PIVOTING)
    if restricciones.get("modo_ctf"):
        bloques.append(_BLOQUE_RESTRICCION_CTF)
    if restricciones.get("solo_reportar_criticos"):
        bloques.append(_BLOQUE_RESTRICCION_CRITICOS)
    if restricciones.get("stealth"):
        bloques.append(_BLOQUE_RESTRICCION_STEALTH)

    bloques.append(_BLOQUE_CIERRE)

    mision = "\n\n".join(bloques)
    return mision.replace("{target}", target).replace("{flag_format}", flag_format)


