# Endpoints de Reportes — Acceso a reportes ejecutivos vía API

> Documento de contexto y referencia. Explica las rutas FastAPI que permiten al
> frontend (o a cualquier cliente HTTP) **listar** y **leer** los reportes
> ejecutivos que genera el orquestador, sin entrar a la carpeta `reports/` a mano.
> Pensado para que cualquier sesión futura entienda la feature sin re-investigar.

---

## 1. Problema que resuelve

El orquestador genera reportes en markdown (`orchestrator/reports/reporte_<timestamp>.md`)
al terminar cada campaña. Antes, la **única** forma de acceder a ellos era entrar
manualmente a la carpeta del servidor. El frontend no tenía manera de:

1. Listar qué reportes existen y sus datos clave (objetivo, fecha, iteraciones).
2. Obtener el contenido de un reporte concreto.

La solución añade **dos endpoints HTTP** al router de campaña, más un sistema de
**metadatos en JSON** para que el listado sea rápido (no hay que abrir y parsear
cada `.md` completo solo para mostrar la lista).

---

## 2. Arquitectura

```
Frontend / cliente HTTP
        ↓
FastAPI (Orquestador)  ──  routes/campaign.py
        ├── GET /campaign/reports        → lista (JSON)
        └── GET /campaign/reports/{id}   → contenido completo (JSON)
                    ↓
        core/reports_handler.py   (lee/parsea/ordena)
                    ↓
        orchestrator/reports/
            ├── reporte_<id>.md     (el documento)
            └── reporte_<id>.json   (metadatos)
```

Componentes tocados:

| Archivo | Rol en la feature |
|---|---|
| `orchestrator/agents/reporter_agent.py` | Al generar el `.md`, escribe también el `.json` de metadatos. |
| `orchestrator/agents/commander.py` | Pasa `target` y `mision` al ReporterAgent para que queden en el metadata. |
| `orchestrator/core/reports_handler.py` | **Nuevo.** Funciones para listar y leer reportes (con fallback y seguridad). |
| `orchestrator/routes/campaign.py` | Modelos Pydantic + los dos endpoints. |

**Restricción de diseño:** solo se tocó el backend (orquestador). El frontend no
se modificó; estos endpoints son el contrato que consumirá cuando se conecte.

---

## 3. El identificador (`id`)

El `id` de un reporte es el **timestamp** del momento en que se generó, con formato
`YYYY-MM-DD_HH-MM-SS`. Ejemplo: `2026-06-22_22-26-51`.

- Se genera en `ReporterAgent.generar_reporte()` con `datetime.now()` **al terminar
  la campaña**, en el mismo instante en que se escribe el reporte.
- Es el mismo valor en tres lugares, lo que enlaza los archivos:

```
reporte_2026-06-22_22-26-51.md      ← el reporte
reporte_2026-06-22_22-26-51.json    ← su metadata (y el campo "id" dentro)
         └──────┬───────┘
              el id
```

- El cliente **no inventa** ids: los lee del listado (`GET /reports`) y los reusa
  para pedir el detalle (`GET /reports/{id}`).
- Como incluye segundos, dos campañas no colisionan salvo que terminaran en el
  mismo segundo exacto.

---

## 4. Estructura del metadata JSON

Cada reporte nuevo genera un `reporte_<id>.json` hermano del `.md`:

```json
{
  "id": "2026-06-22_22-26-51",
  "timestamp": "2026-06-22_22-26-51",
  "target": "localhost",
  "mision": "Ejecuta un nmap a los mil puertos más comunes...",
  "iteraciones": 2,
  "archivo_md": "reporte_2026-06-22_22-26-51.md"
}
```

| Campo | Significado | Origen |
|---|---|---|
| `id` | Identificador (= timestamp). Clave para `GET /reports/{id}`. | `datetime.now()` |
| `timestamp` | Igual al `id`, en formato ordenable lexicográficamente. | `datetime.now()` |
| `target` | IP/host evaluado en la campaña. | `commander.py` (scope) |
| `mision` | Texto de la misión (`objetivo.txt`) de esa campaña. | `commander.py` (scope) |
| `iteraciones` | Nº de reportes de iteración sintetizados. | `len(reportes)` |
| `archivo_md` | Nombre del `.md` asociado. Hace el JSON autocontenido. | derivado |

**Por qué un JSON aparte y no leer el `.md`:** para que `GET /reports` sea barato.
Listar 100 reportes requeriría abrir 100 archivos markdown completos; con el JSON
solo se leen unos pocos campos por reporte.

**Escritura best-effort:** el `.json` se escribe dentro de un `try/except`. Si
fallara, el `.md` ya está guardado y la campaña no se cae — el reporte se
degrada a "legacy" (ver siguiente sección).

---

## 5. Compatibilidad con reportes antiguos (fallback)

Existen reportes generados **antes** de esta feature que NO tienen `.json`. El
handler nunca asume que todo `.md` tiene su `.json`. La lógica de
`_metadata_de()` en `reports_handler.py`:

- **Si existe el `.json`** → se usan sus campos.
- **Si NO existe** (reporte legacy o JSON corrupto) → fallback:
  - `id` / `fecha` se derivan del nombre del archivo.
  - `target` = `"desconocido"`, `mision` = `""`, `iteraciones` = `null`.

Así la lista nunca se rompe por reportes históricos: aparecen todos, los nuevos
con datos completos y los viejos con los campos que se puedan inferir.

---

## 6. Endpoint: `GET /campaign/reports`

Lista todos los reportes, **más nuevos primero**.

### Petición

```bash
curl http://127.0.0.1:8000/campaign/reports
```

### Respuesta — `200 OK`

```json
{
  "reportes": [
    {
      "id": "2026-06-22_22-26-51",
      "fecha": "2026-06-22 22:26:51",
      "target": "localhost",
      "mision": "Ejecuta un nmap a los mil puertos más comunes...",
      "iteraciones": 2
    },
    {
      "id": "2026-06-16_13-21-52",
      "fecha": "2026-06-16 13:21:52",
      "target": "desconocido",
      "mision": "",
      "iteraciones": null
    }
  ]
}
```

> El segundo item es un reporte legacy (sin `.json`): por eso `target` es
> `desconocido` e `iteraciones` es `null`.

### Modelo de respuesta (Pydantic)

`ListaReportes` → `{ "reportes": [ ReporteResumen, ... ] }`, donde `ReporteResumen`
tiene: `id`, `fecha`, `target`, `mision`, `iteraciones`.

El orden viene de `listar_reportes()`, que ordena por `id` descendente (el formato
de timestamp es ordenable como texto).

---

## 7. Endpoint: `GET /campaign/reports/{id}`

Devuelve el **contenido completo** de un reporte concreto.

### Petición

```bash
curl http://127.0.0.1:8000/campaign/reports/2026-06-22_22-26-51
```

### Respuesta — `200 OK`

```json
{
  "id": "2026-06-22_22-26-51",
  "fecha": "2026-06-22 22:26:51",
  "target": "localhost",
  "mision": "Ejecuta un nmap a los mil puertos más comunes...",
  "iteraciones": 2,
  "archivo_md": "reporte_2026-06-22_22-26-51.md",
  "contenido": "# Reporte Ejecutivo Final - Fase de Exploración\n\n## 1. Servicios..."
}
```

El campo `contenido` trae el markdown completo del `.md` como string. El frontend
lo renderiza con cualquier librería de markdown.

### Respuesta — `404 Not Found`

Si el `id` no corresponde a ningún reporte (o tiene formato inválido):

```json
{ "detail": "Reporte '2099-01-01_00-00-00' no encontrado" }
```

### Modelo de respuesta (Pydantic)

`ReporteCompleto` extiende `ReporteResumen` y añade `archivo_md` y `contenido`.

---

## 8. Seguridad: protección contra path traversal

El `id` llega desde la URL, así que se trata como entrada no confiable. En
`obtener_reporte()` el nombre de archivo se valida contra una **regex estricta**
antes de abrir nada:

```python
_PATRON_NOMBRE = re.compile(r"^reporte_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.md$")
```

Un `id` como `../config` o `../../etc/passwd` no cumple el patrón → la función
devuelve `None` → el endpoint responde `404`. Nunca se construye una ruta a partir
de un `id` arbitrario sin antes validarlo.

---

## 9. Cómo probarlo

### Sin levantar servidor (TestClient)

```bash
cd orchestrator
python3 -c "
from fastapi.testclient import TestClient
from main import app
c = TestClient(app)
print(c.get('/campaign/reports').status_code)
print(c.get('/campaign/reports').json()['reportes'][0])
"
```

### Con el servidor levantado

```bash
cd orchestrator
uvicorn main:app --reload
# Swagger interactivo: http://127.0.0.1:8000/docs (tag «campaign»)

curl http://127.0.0.1:8000/campaign/reports
curl http://127.0.0.1:8000/campaign/reports/<id>
```

### Generar un reporte con metadata

Cualquier campaña que termine y produzca reporte genera el `.json` automáticamente:

```bash
curl -X POST http://127.0.0.1:8000/campaign/start \
  -H "Content-Type: application/json" \
  -d '{"target": "scanme.nmap.org"}'
# al finalizar (status «finalizado») aparecerá reporte_<id>.md + reporte_<id>.json
```

---

## 10. Resumen del flujo de punta a punta

```
Campaña termina
   ↓
ReporterAgent.generar_reporte(reportes, target, mision)
   ├── escribe reporte_<id>.md
   └── escribe reporte_<id>.json  (best-effort)
   ↓
GET /campaign/reports
   └── reports_handler.listar_reportes()  → lee todos los .json (o fallback) y ordena
   ↓
El frontend muestra la lista de ids
   ↓
GET /campaign/reports/{id}
   └── reports_handler.obtener_reporte(id) → valida id, lee el .md, adjunta contenido
   ↓
El frontend renderiza el markdown
```
