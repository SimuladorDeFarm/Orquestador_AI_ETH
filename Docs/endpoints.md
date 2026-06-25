# Documentación de Endpoints — Dani-ETH Orchestrator API

Referencia completa de la API REST del **orquestador** Dani-ETH (FastAPI). Cubre
el control del ciclo de vida de una campaña de pentesting autónomo y el acceso a
los reportes generados.

> **Alcance.** Este documento describe los endpoints que **expone el orquestador**
> (carpeta `orchestrator/`), es decir, lo que consume el frontend. La API del
> **runner** (servicio externo que ejecuta las herramientas) está documentada
> aparte en [`runner_api.md`](runner_api.md) e [`integracion_runner.md`](integracion_runner.md).
> El diseño interno de los endpoints de reportes (metadata JSON, fallback, seguridad)
> está en [`endpoints_reportes.md`](endpoints_reportes.md).

---

## Información general

| | |
|---|---|
| **Base URL** | `http://127.0.0.1:8000` (local / desarrollo) |
| **Framework** | FastAPI + Uvicorn |
| **Docs interactivos (Swagger)** | `http://127.0.0.1:8000/docs` |
| **Esquema OpenAPI** | `http://127.0.0.1:8000/openapi.json` |
| **Media type** | `application/json` en todas las peticiones y respuestas |
| **Cómo levantar** | `cd orchestrator && uvicorn main:app --reload` |

> ⚠️ **Importante:** la API se levanta **desde `orchestrator/`**. Si se levanta
> desde la raíz del repo, las rutas `/campaign/*` darán `404`.

### Índice de endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET`  | `/` | Health check del servicio. |
| `POST` | `/campaign/start` | Inicia una campaña contra un objetivo. |
| `GET`  | `/campaign/status` | Estado actual de la campaña. |
| `POST` | `/campaign/pause` | Pausa la campaña en curso. |
| `POST` | `/campaign/resume` | Reanuda una campaña pausada. |
| `POST` | `/campaign/stop` | Detiene la campaña en curso. |
| `GET`  | `/campaign/reports` | Lista todos los reportes generados. |
| `GET`  | `/campaign/reports/{id}` | Devuelve un reporte completo por su id. |

> **Sesión única.** Solo puede haber **una** campaña activa a la vez. El soporte
> multi-campaña con identificadores está pendiente.

---

## Health check

### `GET /`

Comprobación simple de que el servicio está vivo. No recibe parámetros.

#### Respuesta — `200 OK`

```json
{
  "status": "ok",
  "service": "dani-eth-orchestrator"
}
```

---

## Campaña (control del ciclo de vida)

Todos los endpoints de control devuelven el **mismo objeto de estado**
(`CampaignStatus`), producido por `campaign_manager.estado_actual()`. Es decir,
`status`, `pause`, `resume` y `stop` retornan siempre los campos de estado. El
endpoint `start` devuelve ese mismo objeto más el campo `advertencias`.

> **Nota:** los campos `modo`, `profundidad` y `restricciones` son `null` mientras
> no se haya iniciado ninguna campaña en la sesión actual.

---

### `POST /campaign/start`

Inicia una nueva campaña de exploración contra el objetivo indicado. La campaña
corre en un **hilo de fondo**; este endpoint retorna de inmediato con el estado
inicial (no espera a que termine).

Flujo interno:
1. Valida el body (target, modo, profundidad, restricciones).
2. Ensambla el prompt de misión con `construir_mision()`.
3. Verifica que no haya otra campaña activa (si la hay → `409`).
4. Lanza el `CampaignManager` en un hilo daemon.
5. El Commander dirige las fases (exploración → ...) hasta que el Juez aprueba
   o se alcanza el máximo de iteraciones.

#### Request body

```json
{
  "target": "10.10.10.5",
  "sesion_id": 3,
  "modo": "reconocimiento_explotacion",
  "profundidad": "estandar",
  "restricciones": {
    "no_pivoting": true,
    "modo_ctf": false,
    "flag_format": "FLAG{...}",
    "solo_reportar_criticos": false,
    "stealth": false
  }
}
```

| Campo | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `target` | string | ✅ | — | IP o hostname del objetivo autorizado. |
| `sesion_id` | integer | ❌ | valor de `config.py` | ID de sesión del runner. |
| `modo` | string (enum) | ❌ | `"solo_reconocimiento"` | Modo de ataque (ver valores válidos). |
| `profundidad` | string (enum) | ❌ | `"estandar"` | Nivel de profundidad (ver valores válidos). |
| `restricciones` | object | ❌ | objeto con defaults | Restricciones activas para la campaña. |
| `restricciones.no_pivoting` | boolean | ❌ | `true` | Prohíbe pivotar a otros hosts. |
| `restricciones.modo_ctf` | boolean | ❌ | `false` | Activa búsqueda de flag CTF. |
| `restricciones.flag_format` | string | ❌ | `"FLAG{...}"` | Formato de la flag (solo si `modo_ctf: true`). |
| `restricciones.solo_reportar_criticos` | boolean | ❌ | `false` | Reportar pero no explotar servicios críticos. |
| `restricciones.stealth` | boolean | ❌ | `false` | Minimizar ruido (IDS/IPS). |

**Valores válidos para `modo`:**

| Valor | Descripción |
|---|---|
| `"solo_reconocimiento"` | Solo mapear la superficie de ataque (default). |
| `"reconocimiento_vulnerabilidades"` | Reconocimiento + análisis de CVEs y configuraciones inseguras. |
| `"reconocimiento_explotacion"` | Ciclo completo: reconocimiento → vulnerabilidades → explotación. |

**Valores válidos para `profundidad`:**

| Valor | Descripción |
|---|---|
| `"superficial"` | Máx. 2 iteraciones, herramientas rápidas. |
| `"estandar"` | Máx. 5 iteraciones, rango completo de herramientas (default). |
| `"exhaustivo"` | Sin límite práctico, escaneo completo 1-65535, fuerza bruta. |

#### Respuesta — `200 OK`

```json
{
  "estado": "ejecutando",
  "target": "10.10.10.5",
  "sesion_id": 3,
  "modo": "reconocimiento_explotacion",
  "profundidad": "estandar",
  "restricciones": {
    "no_pivoting": true,
    "modo_ctf": false,
    "flag_format": "FLAG{...}",
    "solo_reportar_criticos": false,
    "stealth": false
  },
  "iteracion_actual": 0,
  "ruta_reporte": null,
  "error": null,
  "advertencias": []
}
```

> Si `modo_ctf: true` y `flag_format` viene vacío, el sistema aplica el default
> `"FLAG{...}"` sin bloquear la campaña, y devuelve la advertencia en el array:
> ```json
> "advertencias": [
>   {
>     "campo": "flag_format",
>     "mensaje": "No se proporcionó formato de flag. Se usará el valor por defecto: FLAG{...}"
>   }
> ]
> ```

#### Respuesta — `422` — `target` ausente o vacío

```json
{
  "error": "campo_requerido",
  "campo": "target",
  "mensaje": "El campo 'target' es obligatorio. Debes indicar la IP o el hostname del objetivo."
}
```

#### Respuesta — `422` — `target` con formato inválido

```json
{
  "error": "formato_invalido",
  "campo": "target",
  "mensaje": "El valor 'no-valido!!' no es una IP ni un hostname válido.",
  "ejemplos_validos": ["10.10.10.5", "scanme.nmap.org", "192.168.1.100"]
}
```

#### Respuesta — `422` — `modo` o `profundidad` con valor no reconocido

```json
{
  "error": "valor_invalido",
  "campo": "modo",
  "valor_recibido": "full_attack",
  "valores_validos": ["solo_reconocimiento", "reconocimiento_vulnerabilidades", "reconocimiento_explotacion"],
  "mensaje": "Modo de ataque no reconocido. Se usará 'solo_reconocimiento' si omites este campo."
}
```

#### Respuesta — `409 Conflict`

Ya hay una campaña en estado `ejecutando` o `pausado`.

```json
{
  "error": "campaña_en_curso",
  "mensaje": "Ya hay una campaña activa. Detenla antes de iniciar una nueva.",
  "estado_actual": {
    "estado": "ejecutando",
    "target": "10.10.10.5",
    "iteracion_actual": 2
  }
}
```

#### Respuesta — `503 Service Unavailable`

El runner no responde al iniciar (timeout o connection refused).

```json
{
  "error": "runner_no_disponible",
  "mensaje": "No se pudo conectar con el runner de herramientas. Verifica que los servicios del runner estén activos en los puertos 8003 y 8004.",
  "puertos_esperados": {
    "registry": 8003,
    "executor": 8004
  }
}
```

---

### `GET /campaign/status`

Devuelve el estado en tiempo real de la campaña. Si nunca se inició una, el
estado es `inactivo`.

#### Parámetros

Ninguno.

#### Respuesta — `200 OK` (en ejecución)

```json
{
  "estado": "ejecutando",
  "target": "scanme.nmap.org",
  "sesion_id": 3,
  "modo": "solo_reconocimiento",
  "profundidad": "estandar",
  "restricciones": {
    "no_pivoting": true,
    "modo_ctf": false,
    "flag_format": "FLAG{...}",
    "solo_reportar_criticos": false,
    "stealth": false
  },
  "iteracion_actual": 2,
  "ruta_reporte": null,
  "error": null
}
```

#### Respuesta — `200 OK` (finalizada)

Cuando termina, `ruta_reporte` apunta al `.md` generado:

```json
{
  "estado": "finalizado",
  "target": "scanme.nmap.org",
  "sesion_id": 3,
  "modo": "solo_reconocimiento",
  "profundidad": "estandar",
  "restricciones": {
    "no_pivoting": true,
    "modo_ctf": false,
    "flag_format": "FLAG{...}",
    "solo_reportar_criticos": false,
    "stealth": false
  },
  "iteracion_actual": 3,
  "ruta_reporte": "orchestrator/reports/reporte_2026-06-22_22-26-51.md",
  "error": null
}
```

#### Respuesta — `200 OK` (con error)

Si la campaña falló, `estado` es `error` y `error` trae el detalle:

```json
{
  "estado": "error",
  "target": "scanme.nmap.org",
  "sesion_id": 3,
  "modo": "solo_reconocimiento",
  "profundidad": "estandar",
  "restricciones": {
    "no_pivoting": true,
    "modo_ctf": false,
    "flag_format": "FLAG{...}",
    "solo_reportar_criticos": false,
    "stealth": false
  },
  "iteracion_actual": 1,
  "ruta_reporte": null,
  "error": "ConnectionError: runner no disponible en http://127.0.0.1:8004"
}
```

#### Valores posibles de `estado`

| Estado | Significado |
|---|---|
| `inactivo` | No se ha iniciado ninguna campaña. |
| `ejecutando` | Campaña corriendo en segundo plano. |
| `pausado` | Pausada entre tareas; espera `resume`. |
| `detenido` | Detenida manualmente con `stop`. |
| `finalizado` | Terminó normalmente; hay reporte disponible. |
| `error` | Falló; ver el campo `error`. |

---

### `POST /campaign/pause`

Solicita pausar la campaña. La pausa es **cooperativa**: toma efecto en el
próximo checkpoint (entre tareas), no instantáneamente. No se pierde estado.

#### Respuesta — `200 OK`

```json
{
  "estado": "pausado",
  "target": "scanme.nmap.org",
  "sesion_id": 3,
  "modo": "solo_reconocimiento",
  "profundidad": "estandar",
  "restricciones": { "no_pivoting": true, "modo_ctf": false, "flag_format": "FLAG{...}", "solo_reportar_criticos": false, "stealth": false },
  "iteracion_actual": 2,
  "ruta_reporte": null,
  "error": null
}
```

#### Respuesta — `409 Conflict`

```json
{
  "detail": "No hay una campaña en ejecución para pausar."
}
```

---

### `POST /campaign/resume`

Reanuda una campaña previamente pausada.

#### Respuesta — `200 OK`

```json
{
  "estado": "ejecutando",
  "target": "scanme.nmap.org",
  "sesion_id": 3,
  "modo": "solo_reconocimiento",
  "profundidad": "estandar",
  "restricciones": { "no_pivoting": true, "modo_ctf": false, "flag_format": "FLAG{...}", "solo_reportar_criticos": false, "stealth": false },
  "iteracion_actual": 2,
  "ruta_reporte": null,
  "error": null
}
```

#### Respuesta — `409 Conflict`

```json
{
  "detail": "No hay una campaña pausada para reanudar."
}
```

---

### `POST /campaign/stop`

Solicita detener la campaña. También es **cooperativo**: toma efecto en el
próximo checkpoint. El estado pasa a `detenido`.

#### Respuesta — `200 OK`

```json
{
  "estado": "detenido",
  "target": "scanme.nmap.org",
  "sesion_id": 3,
  "modo": "solo_reconocimiento",
  "profundidad": "estandar",
  "restricciones": { "no_pivoting": true, "modo_ctf": false, "flag_format": "FLAG{...}", "solo_reportar_criticos": false, "stealth": false },
  "iteracion_actual": 2,
  "ruta_reporte": null,
  "error": null
}
```

#### Respuesta — `409 Conflict`

```json
{
  "detail": "No hay una campaña activa para detener."
}
```

---

## Reportes

Acceso a los reportes ejecutivos que el orquestador guarda en
`orchestrator/reports/`. Cada reporte es un par de archivos hermanos:
`reporte_<id>.md` (el documento) y `reporte_<id>.json` (metadatos para listar sin
abrir el markdown completo).

> **El `id`** es el timestamp de generación, formato `YYYY-MM-DD_HH-MM-SS`
> (ej: `2026-06-22_22-26-51`). Se asigna al terminar la campaña y es la clave para
> pedir un reporte concreto.
>
> **Reportes antiguos (legacy).** Los reportes generados antes de esta feature no
> tienen `.json`; aparecen igual en la lista, pero con `target: "desconocido"`,
> `mision: ""` e `iteraciones: null` (fallback). Detalle en
> [`endpoints_reportes.md`](endpoints_reportes.md).

---

### `GET /campaign/reports`

Lista todos los reportes disponibles, **ordenados del más nuevo al más viejo**.
Devuelve solo metadatos (sin el contenido del markdown), para que el listado sea
rápido aunque haya muchos reportes.

#### Parámetros

Ninguno.

#### Respuesta — `200 OK`

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

> El segundo item es un reporte legacy (sin `.json`): de ahí `target: "desconocido"`
> e `iteraciones: null`.

**Campos de cada reporte** (`ReporteResumen`):

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | string | Identificador (timestamp `YYYY-MM-DD_HH-MM-SS`). |
| `fecha` | string | Fecha legible `YYYY-MM-DD HH:MM:SS`. |
| `target` | string | Host/IP objetivo (`"desconocido"` en reportes legacy). |
| `mision` | string | Misión de la campaña (`""` en reportes legacy). |
| `iteraciones` | integer ∣ null | Nº de iteraciones (`null` en reportes legacy). |

---

### `GET /campaign/reports/{id}`

Devuelve el **contenido completo** de un reporte concreto, junto con sus
metadatos.

#### Parámetros de ruta

| Nombre | Tipo | En | Requerido | Descripción |
|---|---|---|---|---|
| `id` | string | path | ✅ | Identificador del reporte (`YYYY-MM-DD_HH-MM-SS`). Ej: `2026-06-22_22-26-51`. |

> **Seguridad.** El `id` se valida contra una regex estricta antes de abrir
> archivo alguno. Un `id` malicioso (ej: `../config`) no cumple el patrón y
> devuelve `404`, evitando path traversal.

#### Respuesta — `200 OK`

```json
{
  "id": "2026-06-22_22-26-51",
  "fecha": "2026-06-22 22:26:51",
  "target": "localhost",
  "mision": "Ejecuta un nmap a los mil puertos más comunes...",
  "iteraciones": 2,
  "archivo_md": "reporte_2026-06-22_22-26-51.md",
  "contenido": "# Reporte Ejecutivo Final - Fase de Exploración\n\n## 1. Servicios descubiertos\n..."
}
```

**Campos** (`ReporteCompleto`):

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | string | Identificador del reporte. |
| `fecha` | string | Fecha legible. |
| `target` | string | Objetivo de la campaña. |
| `mision` | string | Misión de la campaña. |
| `iteraciones` | integer ∣ null | Nº de iteraciones. |
| `archivo_md` | string | Nombre del archivo `.md` asociado. |
| `contenido` | string | Markdown completo del reporte. |

#### Respuesta — `404 Not Found`

El `id` no corresponde a ningún reporte (o tiene formato inválido).

```json
{
  "detail": "Reporte '2099-01-01_00-00-00' no encontrado"
}
```

---

## Esquemas (modelos Pydantic)

### `CampaignStatus`

Estado de una campaña. Lo devuelven todos los endpoints de control.

| Campo | Tipo | Descripción |
|---|---|---|
| `estado` | string (enum) | `inactivo` ∣ `ejecutando` ∣ `pausado` ∣ `detenido` ∣ `finalizado` ∣ `error`. |
| `target` | string ∣ null | Host/IP objetivo. |
| `sesion_id` | integer | ID de sesión del runner. |
| `modo` | string ∣ null | Modo de ataque de la campaña activa. |
| `profundidad` | string ∣ null | Nivel de profundidad de la campaña activa. |
| `restricciones` | object ∣ null | Restricciones activas (los 5 subcampos). |
| `iteracion_actual` | integer | Iteración actual en ejecución. |
| `ruta_reporte` | string ∣ null | Ruta del `.md` final (al finalizar). |
| `error` | string ∣ null | Mensaje de error (si `estado == "error"`). |

> El endpoint `POST /campaign/start` añade además `advertencias: array` a esta
> respuesta. Los demás endpoints de control no incluyen ese campo.

### `ReporteResumen`

Metadatos de un reporte para el listado.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | string | Identificador (timestamp). |
| `fecha` | string | Fecha legible. |
| `target` | string | Host/IP objetivo. |
| `mision` | string | Misión de la campaña. |
| `iteraciones` | integer ∣ null | Nº de iteraciones (null en legacy). |

### `ListaReportes`

Envoltorio del listado.

| Campo | Tipo | Descripción |
|---|---|---|
| `reportes` | array[`ReporteResumen`] | Reportes, más nuevos primero. |

### `ReporteCompleto`

Extiende `ReporteResumen` con el contenido.

| Campo | Tipo | Descripción |
|---|---|---|
| *(todos los de `ReporteResumen`)* | | |
| `archivo_md` | string | Nombre del archivo `.md`. |
| `contenido` | string | Markdown completo del reporte. |

---

## Tabla de códigos de estado

| Código | Cuándo aparece |
|---|---|
| `200 OK` | Operación exitosa. |
| `404 Not Found` | `GET /campaign/reports/{id}` con un id inexistente o inválido. |
| `409 Conflict` | Control de campaña en un estado incompatible (iniciar con otra en curso, pausar sin campaña activa, etc.). |
| `422 Unprocessable Entity` | `target` ausente/vacío/inválido, o `modo`/`profundidad` con valor fuera del enum. El cuerpo de error detalla el campo concreto. |
| `503 Service Unavailable` | El runner no responde al iniciar la campaña. |

---

## Notas operativas

- **El runner debe estar disponible** (Tool Registry `:8003` y Tool Executor `:8004`)
  para que las campañas ejecuten herramientas. Si no, la campaña terminará en `error`.
- **Reportes en disco:** `orchestrator/reports/` como `reporte_<id>.md` +
  `reporte_<id>.json`.
- **Estado en memoria:** no hay base de datos; el estado de la campaña vive en el
  proceso del orquestador. Reiniciar el servidor lo pierde (los reportes en disco
  persisten).
- **Misión dinámica:** el prompt de misión se construye en tiempo de ejecución a
  partir de `target`, `modo`, `profundidad` y `restricciones` recibidos en
  `POST /campaign/start`. Ya no se usa `orchestrator/objetivo.txt` en el flujo
  normal (se mantiene solo como override de emergencia).
