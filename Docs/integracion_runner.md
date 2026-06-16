# Integración del Orquestador con el Runner (Tool Executor API)

> Documento de contexto. Explica cómo el orquestador (carpeta `orchestrator/`)
> ejecuta herramientas a través del **runner de los compañeros** en vez de
> `docker exec`. Pensado para que cualquier sesión futura entienda el estado
> actual sin re-investigar.

---

## 1. Qué es el runner

El runner es un backend aparte (repo `danieth-backend_runner-frontend/backend_runner`,
corre con `docker-compose`). Son **dos servicios** relevantes:

| Servicio | Puerto | Rol |
|---|---|---|
| **Tool Registry** | `8003` | Cataloga las herramientas disponibles y sus esquemas de parámetros. |
| **Tool Executor** | `8004` | Ejecuta una herramienta (cada tool corre en su propio contenedor Docker) de forma **asíncrona**. |

> La base de datos es una **Supabase compartida** del equipo (no local). El
> registry y el executor leen/escriben ahí. La lista de herramientas y sus
> imágenes Docker viven en esa BD.

### Herramientas disponibles hoy
`nmap`, `nuclei`, `sqlmap`, `xsstrike`, `curl`, `ls`, `cat`.
Cada una tiene un **`esquema_input`** propio (parámetros estructurados, NO
comandos de shell). Ejemplos:

- `nmap`: `objetivo` (req), `puertos`, `tipo_escaneo` (`-sS/-sT/-sV/-A`), `velocidad` (0-5)
- `curl`: `url` (req), `metodo`, `headers`, `data`, `flags_extra`
- `nuclei`: `objetivo` (req), `templates`, `severidad`, `rate_limit`
- `cat`: `archivo` (req), `flags` · `ls`: `ruta`, `flags`

---

## 2. Contrato de la API del runner

### Registry (8003)
- `GET /herramientas/para-orquestador` → **catálogo** que consume el orquestador
  (nombre, descripcion, casos_usos, categoria, `esquema_input`, `esquema_output`, version_activa).
- `GET /herramientas/{nombre}/versiones` → versiones, con el campo `docker_imagen`.

### Executor (8004) — modelo asíncrono (lanzar + consultar)
1. **Lanzar**: `POST /ejecutar/`
   ```json
   {
     "herramienta": "nmap",
     "sesion_id": 3,
     "params": { "objetivo": "scanme.nmap.org", "tipo_escaneo": "-sV", "puertos": "80" },
     "orden_ejecucion": 1
   }
   ```
   Respuesta: `{"message":"tarea iniciada","tarea_id":111,"estado":"pendiente"}`

2. **Consultar**: `GET /ejecutar/tareas/{tarea_id}`
   ```json
   {
     "tarea_id": 111,
     "estado": "completado",
     "codigo_salida": 0,
     "mensaje_error": null,
     "nombre_herramienta": "nmap",
     "resultado": { "raw_output": "...", "json_output": { ... } }
   }
   ```

**Estados de la tarea**: `pendiente` → `corriendo` → `completado` | `fallido`.
(`completado` con `codigo_salida != 0` = la herramienta falló dentro del contenedor.)

> **Importante**: hacer `GET` antes de que la tarea termine NO es un error: devuelve
> 200 con estado `pendiente`/`corriendo`. Por eso el cliente hace **polling**
> (ver abajo), no un único GET.

---

## 3. Cómo lo consume el orquestador

### Archivos tocados
| Archivo | Cambio |
|---|---|
| `orchestrator/config.py` | URLs del runner, `SESION_ID`, parámetros de polling. |
| `orchestrator/core/runner_client.py` | **Reescrito**: cliente HTTP (reemplaza `docker exec`). |
| `orchestrator/agents/explorer_agent.py` | Tool calling con params estructurados + `enum` de herramientas. |
| `orchestrator/agents/explorer.py` | Inyecta el catálogo en el prompt; quitó la lista de herramientas hardcodeada. |
| `orchestrator/core/campaign_manager.py` | Propaga `sesion_id` por la campaña. |
| `orchestrator/routes/campaign.py` | `POST /campaign/start` acepta `sesion_id` opcional. |

### `config.py`
```python
RUNNER_REGISTRY_URL = "http://127.0.0.1:8003"   # env: RUNNER_REGISTRY_URL
RUNNER_EXECUTOR_URL = "http://127.0.0.1:8004"   # env: RUNNER_EXECUTOR_URL
SESION_ID           = 3                          # env: SESION_ID (sesión única por ahora)
RUNNER_POLL_INTERVALO = 2    # segundos entre consultas
RUNNER_POLL_MAX       = 150  # ~5 min máximo de espera por tarea
```

### `core/runner_client.py` (solo `urllib`, sin dependencias nuevas)
- `listar_herramientas()` → GET del catálogo. Si el runner no responde, `[]`.
- `ejecutar(herramienta, params, sesion_id)` → **POST + polling**. Hace `POST /ejecutar/`,
  obtiene `tarea_id`, y consulta `GET /ejecutar/tareas/{id}` cada `RUNNER_POLL_INTERVALO`
  segundos hasta estado terminal o `RUNNER_POLL_MAX`. **Nunca lanza**: los errores
  (HTTP, timeout) se devuelven en un dict con `estado` `error`/`timeout` para que el
  agente los lea.
- `formatear_resultado(tarea)` → texto legible para el LLM (encabezado + `json_output`).
- `formatear_catalogo(herramientas)` → texto del catálogo para inyectar al prompt.

### Flujo de una ejecución
```
Explorador (LLM) elige tool ejecutar_herramienta(herramienta, params)
   └─ runner_client.ejecutar()
        ├─ POST /ejecutar/            → tarea_id
        └─ loop: GET /ejecutar/tareas/{id}  (cada 2s, hasta completado/fallido)
   └─ formatear_resultado() → vuelve al agente como resultado
```

### Tool calling estructurado (clave)
El Explorador ya **no** arma comandos de shell. Usa:
- `ejecutar_herramienta(herramienta, params)` — `herramienta` está restringida por un
  **`enum`** con las herramientas reales del catálogo → el modelo no puede inventar tools.
- `planificar_tareas(tareas)` — `tareas` es una lista de objetos `{herramienta, params}`.

El catálogo (con cada `esquema_input`) se **inyecta dinámicamente** en el system prompt
del Explorador en `crear_explorador()`, junto al objetivo de la misión (`objetivo.txt`).
Se lee en cada campaña: si el runner cambia sus herramientas, el Explorador se entera solo.

### `sesion_id`
Por ahora hay **una sola sesión fija** (`SESION_ID`, default `3`). Se puede sobreescribir
por env o en el body de `POST /campaign/start` (`{"target": "...", "sesion_id": N}`).
El soporte multi-sesión/id queda pendiente.

---

## 4. Arreglo aplicado al runner (nmap)

Al integrar, el `nmap` fallaba con `codigo_salida: 125` y
`"docker: invalid reference format"`. Causa: la versión activa de nmap en el registry
tenía la imagen mal escrita con **dos `:`**:

```
backend_runner-nmap:nmap:7.94   ❌  →   backend_runner-nmap:7.94   ✅
```

Se corrigió con un **UPDATE puntual** (1 fila) sobre la Supabase compartida
(`versiones_herramientas`), ejecutado dentro del contenedor `backend_runner-tool_registry-1`.
También hubo que **construir las imágenes** por herramienta (`docker build -t backend_runner-nmap:7.94 .`
desde `tools/nmap/`), porque no estaban buildeadas.

> Si el equipo **re-seedea** la BD con el seed original, el typo podría volver. Conviene
> que corrijan el seed en origen.

---

## 5. Cómo levantar y probar

```bash
# 1. El runner debe estar corriendo (docker-compose en su repo): puertos 8003 y 8004.
# 2. Levantar el orquestador:
cd orchestrator
uvicorn main:app --reload     # docs: http://127.0.0.1:8000/docs

# 3. Iniciar una campaña:
#    POST /campaign/start  {"target": "scanme.nmap.org"}
#    GET  /campaign/status
#    POST /campaign/pause | /campaign/resume | /campaign/stop
```

Prueba directa del cliente (sin LLM):
```python
from core.runner_client import listar_herramientas, ejecutar, formatear_resultado
print([t["nombre"] for t in listar_herramientas()])
print(formatear_resultado(ejecutar("nmap", {"objetivo":"scanme.nmap.org","puertos":"80"}, 3)))
```

---

## 6. Caveats / cosas a recordar

- El runner debe estar **arriba** en 8003 y 8004; si no, `listar_herramientas()` devuelve `[]`.
- Las **imágenes Docker de cada herramienta deben estar construidas** (nmap ya lo está;
  nuclei/sqlmap/xsstrike puede que no).
- La BD es **Supabase compartida**: cualquier cambio afecta a todo el equipo.
- `sesion_id` es **fijo** (3) por ahora.
- El runner tiene su propio timeout por contenedor (~900s); además nuestro polling
  corta a ~5 min (`RUNNER_POLL_MAX`).

---

## 7. Memoria estructurada del Explorador (IMPLEMENTADO)

Para no arrastrar todo el transcript con outputs crudos (mucho texto, tokens y confusión),
el Explorador usa una **memoria de trabajo estructurada** (una KB) en lugar del historial.

### Agente Summarizer
- `orchestrator/agents/summarizer_agent.py`: clase `SummarizerAgent` + helpers de la KB.
  - `actualizar_memoria(memoria, herramienta, params, resultado) -> dict`: función
    **stateless** que integra el resultado de UN comando en la KB (tool calling de schema
    fuerte). Si falla, devuelve la memoria sin cambios.
  - Helpers: `memoria_vacia(objetivo)`, `formatear_memoria(kb)`, `normalizar_memoria()`.
- `orchestrator/agents/summarizer.py`: `SYSTEM_PROMPT_SUMMARIZER` + `crear_summarizer()`.
- Regla clave del prompt: copia **verbatim** flags, paths, versiones y credenciales;
  deduplica; mantiene `pendientes` y `descartado` para no repetir comandos.

### Estructura de la KB
```json
{ "objetivo": "...", "servicios": [], "rutas": [], "archivos": [],
  "flags": [], "hallazgos": [], "pendientes": [], "descartado": [] }
```

### Cómo lo usa el Explorador (`explorer_agent.py`)
- El `ExplorerAgent` recibe un `summarizer` y mantiene `self.memoria` (KB) + `self.registro`
  (outputs crudos, fuera del contexto del LLM, para auditoría/Reporter).
- `ingerir(herramienta, params, resultado)`: guarda el crudo y actualiza la memoria.
- **Todas** las llamadas al LLM (`preguntar`, `generar_tareas`, `decidir_iteracion`) usan
  `_contexto()` = `[system_prompt, memoria_formateada]` — contexto **acotado y constante**,
  no el transcript que crecía.
- En el bucle de tareas (`explorer.py`), tras cada `ejecutar()` se llama a `ingerir()`.
  El reporte de iteración se genera a partir de la memoria, no del texto crudo.

> Costo: una llamada chica al Summarizer por comando, a cambio de contexto acotado del
> Explorador (menos tokens netos en corridas largas y menos confusión del modelo).

---

## 8. Selector de herramientas (IMPLEMENTADO)

A medida que el catálogo crezca, pasarle TODAS las herramientas a cada agente gasta tokens
y lo confunde. El **agente Selector** elige el subconjunto (pool) pertinente para una tarea.

- `orchestrator/agents/selector_agent.py`: clase `SelectorAgent`.
  - `seleccionar(catalogo, objetivo, rol="reconocimiento") -> list[dict]`: stateless, vía
    tool calling (`seleccionar_herramientas` con `enum` de nombres). Devuelve el subconjunto
    del catálogo. **Fallback**: si falla o no elige nada, devuelve el catálogo completo.
- `orchestrator/agents/selector.py`: `SYSTEM_PROMPT_SELECTOR` + `crear_selector()`.
- Es **genérico por rol**: lo usa cualquier agente que lance comandos.
  - Explorador → `rol="reconocimiento"` (descubrimiento/enumeración/lectura).
  - Explotador (pendiente) → `rol="explotación"` (sqlmap, xsstrike, etc.).

### Integración
`crear_explorador()` (en `explorer.py`) ahora hace:
`catalogo = listar_herramientas()` → `crear_selector().seleccionar(catalogo, objetivo, "reconocimiento")`
→ el Explorador recibe SOLO ese pool (tanto en el prompt como en el `enum` de la tool
`ejecutar_herramienta`). La selección ocurre una vez por campaña.
