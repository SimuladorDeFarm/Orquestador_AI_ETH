# Handoff Frontend — Timeline de eventos de la campaña en vivo

> **Para quién es este documento.** Para la IA/dev que implementará el frontend y
> **no tiene acceso al repositorio del orquestador**. Aquí está todo lo necesario
> para construir la vista de "ataque en vivo" sin leer el código del backend:
> el contrato HTTP, los tipos de datos, ejemplos reales y las tareas pendientes
> con código listo para pegar.

---

## 1. Contexto en una frase

El **orquestador** (backend, FastAPI en `http://localhost:8000`) ejecuta campañas
de pentesting autónomo con varios agentes de IA. Hasta ahora, lo que hacían los
agentes solo se veía por la **terminal** (con `print()`). Acabamos de añadir en el
backend un **bus de eventos estructurado** y un endpoint que lo expone, para que el
frontend muestre esa actividad como una **timeline visual en vivo** en lugar de un
volcado de texto.

**Tu trabajo (frontend):** consumir ese endpoint por *polling* y renderizar cada
evento como un componente visual según su `tipo`.

---

## 2. Qué se hizo en el backend (ya está listo, no lo tocas)

1. **Bus de eventos** thread-safe: los agentes, además de seguir imprimiendo por
   consola, emiten eventos tipados (no se eliminó nada de la consola).
2. **Limpieza por campaña:** al iniciar una campaña nueva (`POST /campaign/start`),
   el bus se vacía. El cursor de eventos reinicia en `0`.
3. **Instrumentación de todos los agentes:** Commander, Explorer, Judge, Selector
   y Summarizer emiten eventos en cada punto relevante de su flujo.
4. **Endpoint nuevo:** `GET /campaign/logs` (descrito abajo).

**No hay WebSocket ni Server-Sent Events.** El backend no empuja datos. El frontend
**consulta** (polling) con un cursor incremental. Es el mismo patrón que ya usas
para `GET /campaign/status`.

---

## 3. El endpoint nuevo: `GET /campaign/logs`

```
GET http://localhost:8000/campaign/logs?desde=0
```

| Query param | Tipo | Default | Descripción |
|---|---|---|---|
| `desde` | integer | `0` | Cursor: devuelve solo los eventos cuyo `id` es `>= desde`. |

### Respuesta `200 OK`

```json
{
  "eventos": [
    {
      "id": 0,
      "timestamp": "2026-06-27T15:30:01.123456+00:00",
      "tipo": "campaign_start",
      "agente": "commander",
      "fase": null,
      "iteracion": null,
      "datos": { "target": "scanme.nmap.org", "mision": "Encuentra 1 flag..." }
    },
    {
      "id": 1,
      "timestamp": "2026-06-27T15:30:08.654321+00:00",
      "tipo": "tool_call",
      "agente": "explorer",
      "fase": "exploracion",
      "iteracion": 1,
      "datos": { "herramienta": "nmap", "params": { "target": "scanme.nmap.org" } }
    }
  ],
  "total": 2
}
```

- `eventos`: los eventos nuevos desde el cursor `desde`.
- `total`: total de eventos acumulados en esta campaña. **Guárdalo y úsalo como el
  próximo `desde`.**

Si no hay eventos (campaña nunca iniciada o `desde >= total`): `{ "eventos": [], "total": <n> }`.

### Forma de cada evento

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | number | Índice incremental. Sirve de **cursor** y de `key` de React. |
| `timestamp` | string | ISO 8601 en UTC. |
| `tipo` | string | Define **cómo renderizarlo** (ver catálogo §4). |
| `agente` | string | Quién lo emitió: `commander`, `explorer`, `judge`, `selector`, `summarizer`. |
| `fase` | string \| null | Fase de la campaña (ej. `"exploracion"`), si aplica. |
| `iteracion` | number \| null | Iteración Explorador↔Juez en curso, si aplica. |
| `datos` | object | Payload específico del `tipo` (varía, ver §4). |

---

## 4. Catálogo de tipos de evento (lo más importante)

Cada `tipo` se mapea a un componente visual distinto. El campo `datos` cambia según
el tipo. **Renderiza distinto cada uno; no los muestres como texto plano.**

| `tipo` | `agente` | Qué representa | Campos de `datos` |
|---|---|---|---|
| `campaign_start` | commander | Arranque de la campaña. | `target`, `mision` |
| `phase_start` | commander | Entra en una fase (ej. exploración). | `fase`, `descripcion` |
| `phase_end` | commander | Termina una fase. | `fase`, `reportes_recibidos` |
| `campaign_end` | commander | Reporte ejecutivo final generado (✅ éxito). | `ruta_reporte`, `fases_completadas`, `total_reportes` |
| `campaign_aborted` | commander | La campaña se detuvo o falló. | `motivo`, `detalle` |
| `tool_selection` | selector | El Selector eligió el set de herramientas. | `rol`, `elegidas` (array), `fallback` (bool), `razon` |
| `stage` | explorer | Sub-etapa dentro de una iteración. | `etapa`: `escaneo_inicial` \| `generando_tareas` \| `ejecucion_tareas` \| `reporte` |
| `tasks_planned` | explorer | Se planificó la lista de tareas. | `cantidad`, `tareas` (array de `{herramienta, params}`) |
| `task_start` | explorer | Empieza a ejecutar una tarea. | `numero`, `herramienta`, `params` |
| `task_skipped` | explorer | Tarea sin herramienta, omitida. | `numero`, `tarea` |
| `tool_call` | explorer | El LLM invocó una herramienta. | `herramienta`, `params` |
| `tool_result` | explorer | **Output crudo** de una herramienta del runner. | `herramienta`, `params`, `output` (string largo), `chars` |
| `memory_update` | summarizer | La memoria de trabajo (KB) se actualizó. | `comandos_acumulados`, `chars_crudo`, `chars_memoria`, `memoria` (string) |
| `report_generated` | explorer | Reporte markdown de **una iteración**. | `reporte` (markdown) |
| `iteration_decision` | explorer | La IA decide seguir o terminar de iterar. | `continuar` (bool), `razon` |
| `judge_verdict` | judge | El Juez aprueba o rechaza la iteración. | `aprobado` (bool); `razon` si aprueba, `feedback` si rechaza |
| `error` | (cualquiera) | Falló una llamada al LLM o a un agente. | `origen`, `mensaje` |

> ⚠️ **Forward-compat:** el catálogo crecerá (falta el agente "Explotador").
> **Ignora de forma segura los `tipo` que no reconozcas** (renderiza un fallback
> genérico o nada), nunca rompas la UI por un tipo nuevo.

### Sugerencia de mapeo visual (colores ya existentes en el proyecto)

| `tipo` | Componente sugerido | Color (variable CSS) |
|---|---|---|
| `campaign_start` | Banner con target | `var(--accent-cyan)` |
| `phase_start` / `phase_end` | Separador de sección | `var(--accent-blue)` |
| `stage` | Chip de etapa | `var(--text-muted)` |
| `tasks_planned` | Lista colapsable de tareas | `var(--text-secondary)` |
| `task_start` / `tool_call` | Badge con nombre de herramienta | `var(--accent-blue)` |
| `tool_result` | Panel **colapsable** con el output crudo (`<pre>`) | `var(--bg-tertiary)` |
| `memory_update` | Stat compacta `X cmds → Y chars` | `var(--text-muted)` |
| `report_generated` | Markdown colapsable | `var(--bg-secondary)` |
| `iteration_decision` | Chip continuar/terminar | cyan / amarillo |
| `judge_verdict` | Card aprobado/rechazado | `var(--severity-low)` / `var(--severity-high)` |
| `campaign_end` | Banner éxito + botón "Ver reporte" | `var(--severity-low)` |
| `campaign_aborted` / `error` | Alert | `var(--severity-critical)` |

> El campo `output` de `tool_result` y el `reporte` de `report_generated` pueden ser
> **muy largos**. Móstralos colapsados por defecto (acordeón / "ver más").

---

## 5. Patrón de polling (cómo consumir los logs)

1. El usuario lanza la campaña con `POST /campaign/start`. El bus se vacía → el
   cursor empieza en `0`.
2. Pide `GET /campaign/logs?desde=0`. Guarda `total`.
3. Acumula los `eventos` recibidos en tu estado local (lista).
4. Siguiente llamada: `GET /campaign/logs?desde=<total_anterior>`. Solo recibes lo
   nuevo. Vuelve a guardar el nuevo `total`.
5. Repite cada **2–3 s** mientras la campaña esté activa.
6. **Cuándo parar:** consulta en paralelo `GET /campaign/status`; detén el polling
   cuando `estado` sea `finalizado`, `detenido` o `error`. (Recomendado: una última
   llamada a `/logs` tras parar, para no perder los eventos finales.)

> Mantén dos polls (status cada 3 s ya existe; logs cada 2–3 s) o únelos en un solo
> intervalo. No bajes de ~2 s para no saturar el backend.

---

## 6. Tareas pendientes (Sprint B — Frontend)

El backend (Sprint A) está **completo**. Estas son tus tareas:

### B1 — Tipos y función de API

Añadir en `src/lib/orquestador.ts` (junto a las funciones de campaña que ya existen):

```ts
import { apiClient } from './api';

export interface CampaignEvent {
  id: number;
  timestamp: string;            // ISO 8601 UTC
  tipo: string;                 // ver catálogo §4
  agente: 'commander' | 'explorer' | 'judge' | 'selector' | 'summarizer' | string;
  fase: string | null;
  iteracion: number | null;
  datos: Record<string, unknown>;
}

export interface LogsResponse {
  eventos: CampaignEvent[];
  total: number;
}

export async function obtenerLogs(desde = 0): Promise<LogsResponse> {
  const { data } = await apiClient.get('/campaign/logs', { params: { desde } });
  return data;
}
```

### B2 — Hook de polling incremental

Crear `src/hooks/useCampaignLogs.ts` (o donde vivan tus hooks):

```ts
import { useEffect, useRef, useState } from 'react';
import { obtenerLogs, CampaignEvent } from '../lib/orquestador';

// `activo` = true mientras la campaña esté en 'ejecutando' o 'pausado'.
export function useCampaignLogs(activo: boolean) {
  const [eventos, setEventos] = useState<CampaignEvent[]>([]);
  const cursor = useRef(0);

  // Al (re)iniciar una campaña, resetea el cursor y la lista.
  const reset = () => {
    cursor.current = 0;
    setEventos([]);
  };

  useEffect(() => {
    if (!activo) return;
    let cancelado = false;

    const tick = async () => {
      try {
        const { eventos: nuevos, total } = await obtenerLogs(cursor.current);
        if (cancelado) return;
        if (nuevos.length > 0) {
          setEventos(prev => [...prev, ...nuevos]);
          cursor.current = total;
        }
      } catch {
        /* reintenta en el próximo tick */
      }
    };

    tick(); // primera carga inmediata
    const interval = setInterval(tick, 2500);
    return () => { cancelado = true; clearInterval(interval); };
  }, [activo]);

  return { eventos, reset };
}
```

> Llama a `reset()` cuando dispares un `POST /campaign/start` nuevo, para no mezclar
> la timeline de la campaña anterior.

### B3 — Componente `CampaignLogFeed`

Crear `src/components/CampaignLogFeed.tsx`: recibe `eventos: CampaignEvent[]` y
renderiza cada uno según su `tipo` (un `switch (evento.tipo)` que devuelve el
componente visual de §4). Para `tipo` desconocido → fallback genérico (no romper).

- `tool_result` y `report_generated`: contenido **colapsable** (acordeón).
- Auto-scroll al último evento (opcional, estilo terminal).
- Agrupar visualmente por `fase` / `iteracion` si quieres más estructura.

### B4 — Integrar en `AIPentesting.tsx`

Montar `<CampaignLogFeed eventos={eventos} />` debajo del panel de estado/control
de la campaña. Pasar `activo = estado === 'ejecutando' || estado === 'pausado'`
al hook `useCampaignLogs`.

### B5 — Verificar el ciclo completo

Lanzar una campaña y comprobar que la timeline aparece en vivo, que el polling se
detiene al `finalizado`/`error`/`detenido`, y que al iniciar otra campaña la
timeline se limpia (gracias a `reset()`).

---

## 7. Resumen del contrato (cheat-sheet)

```
GET /campaign/logs?desde=N
  → { eventos: CampaignEvent[], total: number }

CampaignEvent = {
  id, timestamp, tipo, agente, fase|null, iteracion|null, datos
}

Polling: desde=0 → guarda total → desde=total → repite (2–3s)
Parar cuando GET /campaign/status.estado ∈ {finalizado, detenido, error}
Bus se vacía en cada POST /campaign/start (cursor reinicia en 0)
Ignora tipos de evento desconocidos sin romper
```

Cualquier duda sobre el resto de endpoints de campaña y reportes está en
`Docs/endpoints.md` del repo del orquestador (pídelo si lo necesitas).
