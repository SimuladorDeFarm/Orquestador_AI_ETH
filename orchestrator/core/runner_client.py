"""Cliente del runner de los compañeros (Tool Executor API + Tool Registry).

Reemplaza la ejecución vía `docker exec`. Toda interacción es HTTP:
- Registry (8003): cataloga las herramientas disponibles y sus esquemas.
- Executor (8004): ejecuta una herramienta de forma asíncrona (tarea) y se
  consulta por id hasta que termina.
"""

import json
import time
import urllib.request
import urllib.error

from config import (
    RUNNER_REGISTRY_URL,
    RUNNER_EXECUTOR_URL,
    RUNNER_POLL_INTERVALO,
    RUNNER_POLL_MAX,
)

ESTADOS_TERMINALES = {"completado", "fallido"}


def _get(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post(url: str, body: dict, timeout: int = 15):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def listar_herramientas() -> list[dict]:
    """Devuelve el catálogo de herramientas del registry (para el orquestador).

    Cada herramienta trae nombre, descripcion, casos_usos, categoria y
    esquema_input. Si el runner no responde, devuelve lista vacía.
    """
    try:
        return _get(f"{RUNNER_REGISTRY_URL}/herramientas/para-orquestador")
    except Exception as e:
        print(f"[RUNNER] No se pudo obtener el catálogo de herramientas: {e}")
        return []


def ejecutar(herramienta: str, params: dict, sesion_id: int) -> dict:
    """Ejecuta una herramienta en el runner y espera (polling) su resultado.

    Devuelve el dict de la tarea terminal (o un dict sintético con estado
    'error'/'timeout' si algo falla). Nunca lanza: los errores se reportan en
    el propio resultado para que el agente los pueda leer.
    """
    print(f"[RUNNER] Ejecutando '{herramienta}' params={params} (sesion {sesion_id})")
    try:
        inicio = _post(
            f"{RUNNER_EXECUTOR_URL}/ejecutar/",
            {"herramienta": herramienta, "params": params, "sesion_id": sesion_id},
        )
    except urllib.error.HTTPError as e:
        detalle = e.read().decode()
        print(f"[RUNNER] Error al lanzar '{herramienta}': {e.code} {detalle}")
        return _error(herramienta, f"HTTP {e.code}: {detalle}")
    except Exception as e:
        print(f"[RUNNER] Error al lanzar '{herramienta}': {e}")
        return _error(herramienta, str(e))

    tarea_id = inicio.get("tarea_id")
    print(f"[RUNNER] Tarea {tarea_id} iniciada, esperando resultado...")

    for _ in range(RUNNER_POLL_MAX):
        time.sleep(RUNNER_POLL_INTERVALO)
        try:
            tarea = _get(f"{RUNNER_EXECUTOR_URL}/ejecutar/tareas/{tarea_id}")
        except Exception as e:
            print(f"[RUNNER] Error consultando tarea {tarea_id}: {e}")
            return _error(herramienta, f"error consultando tarea: {e}")
        if tarea.get("estado") in ESTADOS_TERMINALES:
            print(f"[RUNNER] Tarea {tarea_id} -> {tarea.get('estado')} "
                  f"(codigo_salida={tarea.get('codigo_salida')})")
            return tarea

    print(f"[RUNNER] Tarea {tarea_id} no terminó tras el tiempo máximo de espera")
    return _error(herramienta, "timeout esperando la tarea", estado="timeout")


def _error(herramienta: str, mensaje: str, estado: str = "error") -> dict:
    return {
        "estado": estado,
        "nombre_herramienta": herramienta,
        "codigo_salida": None,
        "mensaje_error": mensaje,
        "resultado": {},
    }


def formatear_resultado(tarea: dict) -> str:
    """Convierte el resultado de una tarea en texto legible para el agente."""
    nombre = tarea.get("nombre_herramienta")
    estado = tarea.get("estado")
    codigo = tarea.get("codigo_salida")
    error = tarea.get("mensaje_error")

    encabezado = f"[{nombre}] estado={estado} codigo_salida={codigo}"
    if error:
        encabezado += f" error={error}"

    resultado = tarea.get("resultado") or {}
    json_output = resultado.get("json_output")
    if json_output is not None:
        cuerpo = json.dumps(json_output, ensure_ascii=False, indent=2)
    else:
        cuerpo = resultado.get("raw_output", "") or ""

    return f"{encabezado}\n{cuerpo}".strip()


def formatear_catalogo(herramientas: list[dict]) -> str:
    """Renderiza el catálogo del runner para inyectarlo en el prompt del agente."""
    if not herramientas:
        return "No hay herramientas disponibles en el runner."

    lineas = []
    for h in herramientas:
        nombre = h.get("nombre", "?")
        categoria = h.get("categoria", "")
        descripcion = h.get("descripcion", "")
        lineas.append(f"- {nombre} ({categoria}): {descripcion}")

        esquema = h.get("esquema_input", {}) or {}
        for param, meta in esquema.items():
            tipo = meta.get("tipo") or meta.get("type") or "?"
            requerido = meta.get("requerido", meta.get("required", False))
            req = "requerido" if requerido else "opcional"
            desc = meta.get("descripcion", meta.get("description", ""))
            lineas.append(f"    · {param} ({tipo}, {req}): {desc}")

    return "\n".join(lineas)
