# Reporte de problemas — Runner (Tool Executor + Tool Registry)

> **Para:** equipo del runner (`danieth-backend_runner-frontend/backend_runner`).
> **De:** equipo del Orquestador (consume el runner vía HTTP).
> **Propósito:** documentar de forma precisa y reproducible los problemas que
> impiden ejecutar herramientas a través del runner. Pensado para ser leído por
> una IA o por una persona sin contexto previo.

---

## 0. TL;DR (resumen ejecutivo)

Al ejecutar cualquier herramienta vía `POST /ejecutar/`, **todas fallan** con
`codigo_salida: 125` y errores Docker de tipo *"Unable to find image ... pull
access denied"* o *"invalid reference format"*. Las causas son del lado del runner:

| # | Problema | Severidad | Estado |
|---|----------|-----------|--------|
| 1 | Las imágenes Docker de las herramientas **no están construidas** (o con tag que no coincide) | 🔴 Bloqueante | Abierto |
| 2 | `curl`, `ls`, `cat` están en el registry **pero no tienen Dockerfile** | 🔴 Bloqueante | Abierto |
| 3 | El **seed** del registry no es consistente con las imágenes reales; un re-seed rompe la ejecución | 🟠 Alto | Recurrente |
| 4 | Una imagen inexistente se reporta como `estado: "completado"` (no `"fallido"`) | 🟡 Medio | Abierto |

---

## 1. Entorno observado

- **Tool Registry**: `http://127.0.0.1:8003` — cataloga herramientas y versiones.
- **Tool Executor**: `http://127.0.0.1:8004` — ejecuta herramientas de forma asíncrona.
- El executor ejecuta cada herramienta así (ver `tool_executor/app/services/executor_service.py`):
  ```python
  # ExecutorService.lanzar_container
  await asyncio.create_subprocess_exec(
      "docker", "run", "--rm", docker_imagen, params_json, ...)
  ```
  Es decir: **`docker run --rm <docker_imagen> <params_json>`**, donde `<docker_imagen>`
  es el campo `docker_imagen` de la versión activa, leído del registry.

---

## 2. Problema 1 — Imágenes de herramientas no construidas / tag que no coincide 🔴

### Síntoma
Toda ejecución falla. Ejemplos reales:

```jsonc
// POST /ejecutar/  {"herramienta":"nmap","sesion_id":3,"params":{"objetivo":"localhost",...}}
// GET  /ejecutar/tareas/128 :
{
  "estado": "completado",
  "codigo_salida": 125,
  "resultado": { "json_output": {
    "raw": "",
    "error": "Unable to find image 'backend_runner-nmap:latest' locally\ndocker: Error response from daemon: pull access denied for backend_runner-nmap, repository does not exist or may require 'docker login'.\n"
  }}
}
```
```jsonc
// herramienta "curl" -> error: "Unable to find image 'backend_runner-curl:latest' locally ... pull access denied for backend_runner-curl"
```

### Evidencia

**Valores actuales en el registry** (`GET /herramientas/{nombre}/versiones`, versión activa):

| herramienta | `docker_imagen` registrado |
|---|---|
| nmap | `backend_runner-nmap` |
| curl | `backend_runner-curl` |
| nuclei | `backend_runner-nuclei` |
| sqlmap | `backend_runner-sqlmap` |
| xsstrike | `backend_runner-xsstrike` |
| ls | `backend_runner-ls` |
| cat | `backend_runner-cat` |

**Imágenes Docker realmente presentes** (`docker images | grep backend_runner-`):

```
backend_runner-nmap   7.94   30fd5d5904ee   224MB
```
→ Es la **única** imagen de herramienta construida, y con tag `7.94`.

### Causa raíz
1. El `docker_imagen` se guarda **sin tag** (`backend_runner-nmap`). En Docker, una
   referencia sin tag equivale **siempre** a `:latest`. Por lo tanto el executor corre
   `docker run backend_runner-nmap:latest …`.
2. Pero **no existe** ninguna imagen `backend_runner-<tool>:latest`. La única que existe
   es `backend_runner-nmap:7.94`, cuyo tag **no coincide** con el `:latest` solicitado.
3. Como la imagen no existe localmente, Docker intenta hacer `pull` de un repositorio
   inexistente → `pull access denied` → `codigo_salida: 125`.

### Impacto
Ninguna herramienta se puede ejecutar. El runner queda inutilizable de punta a punta.

### Fix recomendado
Construir **todas** las imágenes de herramientas con el nombre/tag que el registry
referencia (sin tag ⇒ `:latest`):

```bash
cd backend_runner
docker build -t backend_runner-nmap:latest     tools/nmap
docker build -t backend_runner-nuclei:latest   tools/nuclei
docker build -t backend_runner-sqlmap:latest   tools/sqlmap
docker build -t backend_runner-xsstrike:latest tools/xsstrike
```
(O bien automatizar el build en `docker-compose` / un script, ver Problema 3.)

> Importante: definir **una sola convención** de tags y que el seed y el build la
> respeten. Hoy el seed usa imágenes sin tag (⇒ `:latest`) pero no hay build que las
> genere con ese tag.

---

## 3. Problema 2 — `curl`, `ls`, `cat` registrados sin Dockerfile 🔴

### Síntoma
Las herramientas `curl`, `ls` y `cat` aparecen en el catálogo
(`GET /herramientas/para-orquestador`) y tienen `docker_imagen` asignada, pero su
imagen **no se puede construir** porque **no existe el Dockerfile**.

### Evidencia
Contenido de `tools/` en el repo del runner:
```
tools/
├── nmap/      (Dockerfile + run.py)
├── nuclei/    (Dockerfile + run.py)
├── sqlmap/    (Dockerfile + run.py)
└── xsstrike/  (Dockerfile + run.py)
```
→ Hay build para **4** herramientas, pero el registry publica **7**
(`nmap, nuclei, sqlmap, xsstrike, curl, ls, cat`). No hay `tools/curl`, `tools/ls`
ni `tools/cat`.

### Impacto
Cualquier tarea con `curl`, `ls` o `cat` falla siempre (imagen imposible de construir).
Además es engañoso para los agentes consumidores: el catálogo ofrece herramientas que
no existen como ejecutable.

### Fix recomendado
Elegir una de dos:
- **Agregar** `tools/curl/`, `tools/ls/`, `tools/cat/` con su `Dockerfile` + `run.py`
  (siguiendo el patrón de `tools/nmap`: el `run.py` parsea `sys.argv[1]` como JSON de
  params y emite JSON por stdout), **o**
- **Quitar** `curl`, `ls`, `cat` del registry hasta que tengan implementación real.

---

## 4. Problema 3 — Seed inconsistente con las imágenes; el re-seed rompe la ejecución 🟠

### Contexto / historial
- En una primera revisión, la versión activa de nmap tenía
  `docker_imagen = "backend_runner-nmap:nmap:7.94"` — **dos `:`**, que produce
  `docker: invalid reference format`. Se corrigió manualmente a `backend_runner-nmap:7.94`
  y se construyó esa imagen → nmap funcionó (`codigo_salida: 0`).
- Posteriormente, un **re-seed** de la base de datos revirtió/cambió los valores: ahora
  las imágenes quedaron **sin tag** (`backend_runner-nmap`, etc.) y sin construir,
  reintroduciendo la falla (Problema 1).

### Causa raíz
El proceso de seed y el proceso de build **no están acoplados ni versionados juntos**:
- El seed escribe en el registry `docker_imagen` que no corresponden a imágenes que el
  build realmente genere.
- No hay un paso que garantice que, tras seedear, las imágenes referenciadas existen.

> Nota: la base de datos es una **Supabase compartida** por el equipo, por lo que un
> re-seed afecta a todos los entornos a la vez.

### Impacto
Arreglos manuales en el registry no son durables: el siguiente re-seed los borra.
La ejecución se rompe de forma recurrente ("whack-a-mole").

### Fix recomendado
1. Definir el `docker_imagen` del seed con la **misma convención** que produce el build
   (nombre y tag exactos).
2. Idealmente, un único comando reproducible que **construya y seedee de forma
   consistente** (ej. `docker compose build` de servicios de tools + seed que apunte a
   esos tags). Así `git pull + build + seed` deja el runner siempre operativo.
3. Validación post-seed opcional: para cada herramienta activa, verificar que
   `docker image inspect <docker_imagen>` exista; si no, marcar la versión como no
   disponible (`disponible=false`) en vez de dejar que falle en ejecución.

---

## 5. Problema 4 — Semántica de estado: imagen inexistente se reporta como "completado" 🟡

### Síntoma
Cuando la imagen no existe (error de Docker), la tarea queda con
`estado: "completado"` y `codigo_salida: 125`, en lugar de `estado: "fallido"`.

### Por qué importa
Un consumidor que se fíe del campo `estado` interpretará la tarea como exitosa.
Hay que mirar `codigo_salida` y/o `resultado.json_output.error` para detectar el fallo,
lo cual no es obvio. Un error de infraestructura (imagen ausente, fallo de Docker) no
debería reportarse igual que una herramienta que corrió bien.

### Fix recomendado
- Si `codigo_salida != 0`, marcar `estado: "fallido"` (o un estado intermedio claro), o
- al menos distinguir el error de Docker (125, "invalid reference format", "pull access
  denied") de una herramienta que ejecutó pero terminó con código != 0.

---

## 6. Cómo reproducir

```bash
# 1. Lanzar una herramienta cualquiera:
curl -X POST http://127.0.0.1:8004/ejecutar/ \
  -H 'Content-Type: application/json' \
  -d '{"herramienta":"nmap","sesion_id":3,"params":{"objetivo":"scanme.nmap.org","puertos":"80"}}'
# -> {"message":"tarea iniciada","tarea_id":N,"estado":"pendiente"}

# 2. Consultar el resultado:
curl http://127.0.0.1:8004/ejecutar/tareas/N
# -> estado "completado", codigo_salida 125, error "Unable to find image 'backend_runner-nmap:latest' ..."

# 3. Confirmar que no hay imagen :latest:
docker images | grep backend_runner-
# -> solo (o ninguna) backend_runner-nmap:7.94
```

---

## 7. Checklist de arreglo (priorizado)

- [ ] **(P1)** Construir las 4 imágenes con build (`nmap, nuclei, sqlmap, xsstrike`) con
      el tag que el registry espera (hoy: sin tag ⇒ `:latest`).
- [ ] **(P1)** Resolver `curl`, `ls`, `cat`: agregar su `tools/<tool>/` (Dockerfile + run.py)
      o quitarlas del registry.
- [ ] **(P2)** Hacer el seed consistente con el build (misma convención de nombre/tag) y
      reproducible con un solo flujo (build + seed).
- [ ] **(P3)** Reportar fallos de Docker como `estado: "fallido"` (o distinguir
      `codigo_salida != 0`).
- [ ] **(P3)** Validación post-seed: marcar `disponible=false` si la imagen no existe.

---

## 8. Anexo — Contrato observado (para referencia)

**Registry (8003)**
- `GET /herramientas/para-orquestador` → catálogo (nombre, descripcion, casos_usos,
  categoria, esquema_input, esquema_output, version_activa).
- `GET /herramientas/{nombre}/versiones` → versiones con `docker_imagen`, `activo`, `disponible`.

**Executor (8004)** — modelo asíncrono
- `POST /ejecutar/` con `{ "herramienta": str, "sesion_id": int, "params": {...}, "orden_ejecucion": int? }`
  → `{ "message", "tarea_id", "estado":"pendiente" }`
- `GET /ejecutar/tareas/{tarea_id}` → `{ "estado", "codigo_salida", "mensaje_error",
  "nombre_herramienta", "resultado": { "raw_output", "json_output" }, ... }`
- Estados observados: `pendiente` → `corriendo` → `completado` | `fallido`.
