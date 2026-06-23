# Contexto para modificar el frontend — Integración con el Orquestador

> Este documento es un briefing completo para que una IA pueda implementar la
> integración del frontend con el orquestador Dani-ETH **sin necesidad de explorar
> el código desde cero**. Incluye el estado actual de cada archivo relevante, qué
> debe cambiar, qué no debe tocarse, y las convenciones del proyecto.

---

## 1. Visión general del sistema

Hay **dos backends distintos** que el frontend consume:

| Backend | Puerto | Qué expone |
|---|---|---|
| **Runner** (equipo externo) | `8003` / `8004` | Herramientas de pentest individuales (nmap, nuclei, etc.). El frontend las accede vía rutas `/proxy/*`. |
| **Orquestador** (nuestro) | `8000` | Control de campañas autónomas de pentesting y acceso a reportes ejecutivos generados por IA. |

El cliente HTTP ya existe y apunta al orquestador:

```ts
// frontend/src/lib/api.ts
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export const apiClient = axios.create({ baseURL: API_URL });
```

`apiClient` ya maneja el JWT de Firebase automáticamente en cada request. Se puede
usar directamente para llamar a los endpoints del orquestador.

---

## 2. Stack y convenciones del frontend

| | |
|---|---|
| **Lenguaje** | TypeScript estricto |
| **Framework** | React 18 con hooks funcionales — cero clases |
| **Bundler** | Vite |
| **Routing** | React Router v6 (`createBrowserRouter`) |
| **Estilos** | Tailwind CSS + variables CSS globales (ver sección 2.1) |
| **HTTP** | Axios vía `apiClient` (`src/lib/api.ts`) |
| **i18n** | `react-i18next` — todas las strings visibles deben ir por `t()` |
| **Auth** | Firebase — las rutas privadas están envueltas en `ProtectedRoute` |
| **No hay** | Redux, Context API para estado de campaña, react-query, SWR |

### 2.1 Variables CSS de color (no usar colores hardcoded)

```css
var(--bg-primary)        /* fondo principal */
var(--bg-secondary)      /* fondo de cards */
var(--bg-tertiary)       /* fondo de inputs y elementos activos */
var(--border-primary)    /* bordes */
var(--text-primary)      /* texto principal */
var(--text-secondary)    /* texto secundario */
var(--text-muted)        /* texto atenuado / labels */
var(--accent-cyan)       /* color de acento principal (cian) */
var(--accent-blue)       /* color de acento secundario (azul) */
var(--severity-critical) /* rojo — crítico */
var(--severity-high)     /* naranja — alto */
var(--severity-medium)   /* amarillo — medio */
var(--severity-low)      /* verde — bajo / éxito */
```

### 2.2 Patrón para funciones de API

Las funciones que llaman a la API viven en archivos dentro de `src/lib/` o
`src/services/`. Nunca se llama a `apiClient` directamente desde un componente.

```ts
// Ejemplo: src/lib/herramientas.ts
import { apiClient } from './api';

export async function listarHerramientas() {
  const { data } = await apiClient.get('/proxy/herramientas');
  return data;
}
```

### 2.3 Patrón de polling

El orquestador es asíncrono: lanzas una operación y luego consultas el estado
con `GET /campaign/status` hasta que el campo `estado` sea `finalizado` o `error`.
El patrón existente en `AIPentesting.tsx` para esperar tareas del runner es la
referencia a seguir:

```ts
const poll = setInterval(async () => {
  const estado = await obtenerEstadoCampaña();
  setEstado(estado);
  if (estado.estado === 'finalizado' || estado.estado === 'error') {
    clearInterval(poll);
  }
}, 3000); // cada 3 segundos
```

---

## 3. Archivos a modificar

### 3.1 `src/pages/AIPentesting.tsx` — EXTENDER (no reemplazar)

**Estado actual:** página funcional que permite ejecutar herramientas del runner
manualmente (nmap, nuclei, sqlmap, etc.). Tiene su propio sistema de polling para
tareas del runner. Esta funcionalidad **debe permanecer intacta**.

**Qué añadir:** una nueva sección de "Orquestador Autónomo" encima o debajo de la
sección de herramientas manuales, que permita:

1. **Formulario de inicio de campaña** — campo de texto para el `target` (IP o
   dominio) y botón "Iniciar campaña". Llama a `POST /campaign/start`.

2. **Panel de estado en tiempo real** — muestra el estado actual de la campaña
   con polling a `GET /campaign/status` cada 3 segundos mientras `estado` sea
   `ejecutando` o `pausado`. Debe mostrar:
   - El campo `estado` (con colores: `ejecutando` → cian, `pausado` → amarillo,
     `finalizado` → verde, `error` → rojo).
   - El campo `target`.
   - El campo `iteracion_actual`.
   - El campo `error` si existe.

3. **Botones de control** — Pausar (`POST /campaign/pause`), Reanudar
   (`POST /campaign/resume`), Detener (`POST /campaign/stop`). Solo mostrar el
   botón pertinente según el estado actual:
   - Si `ejecutando` → mostrar "Pausar" y "Detener".
   - Si `pausado` → mostrar "Reanudar" y "Detener".
   - Si `finalizado` o `error` → mostrar "Nueva campaña" (limpia el estado local).

4. **Enlace al reporte** — cuando `estado === 'finalizado'` y `ruta_reporte` no
   es `null`, mostrar un botón/link que lleve a `/reports` (la página de reportes).

### 3.2 `src/pages/Reports.tsx` — REEMPLAZAR CONTENIDO

**Estado actual:** completamente estático. Muestra 5 tarjetas hardcodeadas
(`vulnerabilityReport`, `patchesByTech`, etc.) y un selector de fecha/formato
sin funcionalidad real. **Todo ese contenido mock debe reemplazarse** por datos
reales del orquestador.

**Qué construir:**

1. **Lista de reportes** — al cargar la página, hacer `GET /campaign/reports` y
   mostrar la lista. Cada reporte muestra: fecha, target, iteraciones (o "—" si
   es null), y un botón "Ver reporte".

2. **Vista de reporte individual** — al hacer clic en "Ver reporte", obtener el
   reporte con `GET /campaign/reports/{id}` y mostrar el campo `contenido`
   (que es un string en markdown). Para renderizarlo se debe instalar e importar
   `react-markdown` (no está en el proyecto aún).

3. **Estado de carga y error** — mostrar un spinner mientras carga, y un mensaje
   claro si `GET /campaign/reports` falla (ej: orquestador no disponible).

4. **Estado vacío** — si la lista viene vacía, mostrar un mensaje que explique
   que aún no hay campañas completadas.

---

## 4. Archivo nuevo a crear

### `src/lib/orquestador.ts`

Siguiendo el patrón de `src/lib/herramientas.ts`, crear un archivo con todas las
funciones que llaman al orquestador:

```ts
import { apiClient } from './api';

// Tipos
export interface CampaignStatus {
  estado: 'inactivo' | 'ejecutando' | 'pausado' | 'detenido' | 'finalizado' | 'error';
  target: string | null;
  sesion_id: number;
  iteracion_actual: number;
  ruta_reporte: string | null;
  error: string | null;
}

export interface ReporteResumen {
  id: string;
  fecha: string;
  target: string;
  mision: string;
  iteraciones: number | null;
}

export interface ReporteCompleto extends ReporteResumen {
  archivo_md: string;
  contenido: string;
}

// Funciones
export async function iniciarCampaña(target: string, sesion_id?: number): Promise<CampaignStatus> {
  const { data } = await apiClient.post('/campaign/start', { target, sesion_id });
  return data;
}

export async function obtenerEstadoCampaña(): Promise<CampaignStatus> {
  const { data } = await apiClient.get('/campaign/status');
  return data;
}

export async function pausarCampaña(): Promise<CampaignStatus> {
  const { data } = await apiClient.post('/campaign/pause');
  return data;
}

export async function reanudarCampaña(): Promise<CampaignStatus> {
  const { data } = await apiClient.post('/campaign/resume');
  return data;
}

export async function detenerCampaña(): Promise<CampaignStatus> {
  const { data } = await apiClient.post('/campaign/stop');
  return data;
}

export async function listarReportes(): Promise<ReporteResumen[]> {
  const { data } = await apiClient.get('/campaign/reports');
  return data.reportes;
}

export async function obtenerReporte(id: string): Promise<ReporteCompleto> {
  const { data } = await apiClient.get(`/campaign/reports/${id}`);
  return data;
}
```

---

## 5. Dependencia a instalar

La página de reportes necesita renderizar el campo `contenido` que viene como
string en markdown. Instalar:

```bash
cd frontend
npm install react-markdown
```

Uso en el componente:

```tsx
import ReactMarkdown from 'react-markdown';

<ReactMarkdown className="prose prose-invert max-w-none text-sm">
  {reporte.contenido}
</ReactMarkdown>
```

> **Nota:** el proyecto no tiene Tailwind Typography (`@tailwindcss/typography`).
> Si `prose` no funciona, aplicar estilos manuales al wrapper del markdown
> (ej: `<div style={{ color: 'var(--text-secondary)', lineHeight: '1.7' }}>`)
> o instalar el plugin de Typography.

---

## 6. Contrato de la API del orquestador

Base URL: `http://localhost:8000` (mismo que `VITE_API_URL`).
Documentación completa: `Docs/endpoints.md` en el repo del orquestador.

### Endpoints de campaña

**Iniciar:**
```
POST /campaign/start
Body: { "target": "scanme.nmap.org", "sesion_id": 3 }
200: CampaignStatus con estado "ejecutando"
409: { "detail": "Ya hay una campaña en curso. Deténla antes de iniciar otra." }
```

**Estado:**
```
GET /campaign/status
200: CampaignStatus (siempre 200, aunque no haya campaña → estado "inactivo")
```

**Control:**
```
POST /campaign/pause   → 200: CampaignStatus | 409: { detail: "..." }
POST /campaign/resume  → 200: CampaignStatus | 409: { detail: "..." }
POST /campaign/stop    → 200: CampaignStatus | 409: { detail: "..." }
```

**Objeto CampaignStatus completo:**
```json
{
  "estado": "ejecutando",
  "target": "scanme.nmap.org",
  "sesion_id": 3,
  "iteracion_actual": 2,
  "ruta_reporte": null,
  "error": null
}
```

Valores de `estado`: `inactivo` | `ejecutando` | `pausado` | `detenido` | `finalizado` | `error`

### Endpoints de reportes

**Listar:**
```
GET /campaign/reports
200: { "reportes": [ ReporteResumen, ... ] }   // más nuevos primero
```

**Detalle:**
```
GET /campaign/reports/{id}
200: ReporteCompleto
404: { "detail": "Reporte '{id}' no encontrado" }
```

**ReporteResumen:**
```json
{
  "id": "2026-06-22_22-26-51",
  "fecha": "2026-06-22 22:26:51",
  "target": "localhost",
  "mision": "Ejecuta un nmap a los mil puertos más comunes...",
  "iteraciones": 2
}
```

**ReporteCompleto** (extiende ReporteResumen):
```json
{
  "id": "2026-06-22_22-26-51",
  "fecha": "2026-06-22 22:26:51",
  "target": "localhost",
  "mision": "Ejecuta un nmap a los mil puertos más comunes...",
  "iteraciones": 2,
  "archivo_md": "reporte_2026-06-22_22-26-51.md",
  "contenido": "# Reporte Ejecutivo Final...\n\n## 1. Servicios..."
}
```

> `iteraciones` puede ser `null` en reportes generados antes de que se implementara
> el metadata. Mostrar `"—"` en la UI en ese caso.

---

## 7. Comportamiento del polling

El orquestador **no tiene WebSocket ni push**. La campaña corre en un hilo de
fondo; el frontend debe consultar `GET /campaign/status` periódicamente.

**Cuándo hacer polling:** mientras `estado` sea `ejecutando` o `pausado`.

**Cuándo parar:** cuando `estado` sea `finalizado`, `detenido` o `error`.

**Intervalo recomendado:** 3000ms (3 segundos). No usar un intervalo menor para
evitar spam de requests.

**Limpiar el intervalo** siempre en el `useEffect` de cleanup:

```ts
useEffect(() => {
  if (estado.estado !== 'ejecutando' && estado.estado !== 'pausado') return;
  const interval = setInterval(async () => {
    const nuevo = await obtenerEstadoCampaña();
    setEstado(nuevo);
    if (nuevo.estado !== 'ejecutando' && nuevo.estado !== 'pausado') {
      clearInterval(interval);
    }
  }, 3000);
  return () => clearInterval(interval);
}, [estado.estado]);
```

---

## 8. Qué NO tocar

- `src/lib/api.ts` — el cliente HTTP y los interceptores ya están correctos.
- `src/lib/herramientas.ts` — las funciones del runner no se modifican.
- La sección de ejecución manual de herramientas en `AIPentesting.tsx` — solo añadir,
  no modificar lo existente.
- `src/router.tsx` — las rutas no cambian (`/ai-pentesting` y `/reports` ya existen).
- `src/components/layout/` — layout, sidebar y header no se tocan.
- Archivos de autenticación (`AuthContext.tsx`, `ProtectedRoute.tsx`, `firebase.ts`).

---

## 9. Rutas del frontend (referencia)

```
/dashboard       → Dashboard.tsx       (no tocar)
/ai-pentesting   → AIPentesting.tsx    ← MODIFICAR (añadir sección orquestador)
/reports         → Reports.tsx         ← REEMPLAZAR contenido
/vulnerabilities → VulnerabilityHub.tsx (no tocar)
/patches         → PatchManager.tsx    (no tocar)
/team            → TeamAssets.tsx      (no tocar)
/settings        → Settings.tsx        (no tocar)
```

---

## 10. Resumen de cambios a implementar

```
Nuevo archivo:
  src/lib/orquestador.ts          ← funciones API + tipos TypeScript

Instalar:
  npm install react-markdown      ← para renderizar markdown en Reports

Modificar:
  src/pages/AIPentesting.tsx      ← añadir sección "Orquestador Autónomo"
                                     con formulario + estado + controles
  src/pages/Reports.tsx           ← reemplazar mock por lista real de reportes
                                     + vista de reporte individual con markdown
```

El trabajo puede hacerse en cualquier orden, pero el orden recomendado es:

1. Crear `orquestador.ts` (base de todo).
2. Modificar `AIPentesting.tsx` (usa solo funciones de campaña).
3. Instalar `react-markdown`.
4. Reemplazar `Reports.tsx` (usa funciones de reportes + react-markdown).
