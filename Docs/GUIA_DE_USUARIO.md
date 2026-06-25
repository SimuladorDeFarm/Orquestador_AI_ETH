# Guía de Usuario — Dani-ETH

> Documento pensado para cualquier persona que quiera usar o entender Dani-ETH sin necesidad de conocer el código fuente.

---

## 1. ¿Qué es Dani-ETH?

Dani-ETH es un **orquestador autónomo de ethical hacking**. En términos simples: le das una dirección IP o un dominio y él mismo decide qué pruebas de seguridad hacer, las ejecuta, analiza los resultados y genera un reporte en lenguaje humano.

### ¿Qué lo hace diferente de ejecutar nmap manualmente?

Un pentest manual requiere que tú elijas las herramientas, las configures, interpretes los resultados y decidas qué hacer después. Dani-ETH automatiza ese ciclo completo:

```
Tú → das un objetivo
  ↓
Sistema → planifica, ejecuta herramientas, analiza, decide si seguir
  ↓
Tú → recibes un reporte con hallazgos
```

### ¿Qué herramientas usa?

Dani-ETH no ejecuta herramientas localmente. Las pide a un servicio externo llamado **runner** que corre en su propia infraestructura Docker. Las herramientas disponibles son:

| Herramienta | Para qué sirve |
|---|---|
| `nmap` | Escanear puertos y detectar servicios |
| `nuclei` | Detectar vulnerabilidades conocidas |
| `sqlmap` | Probar inyecciones SQL |
| `xsstrike` | Probar inyecciones XSS |
| `curl` | Hacer peticiones HTTP personalizadas |
| `ls` / `cat` | Explorar sistema de archivos (si hay acceso) |

### ¿Quién puede usarlo?

Dani-ETH está diseñado para entornos **autorizados**. Solo debe ejecutarse contra sistemas sobre los que tienes permiso explícito del dueño. El sistema opera en modo "caja negra": no recibe información previa del objetivo, lo construye todo desde cero.

---

## 2. Usando la API (paso a paso)

### Requisitos previos

Antes de iniciar, confirma que tienes:
- [ ] El runner corriendo (Tool Registry en puerto `8003`, Tool Executor en `8004`).
- [ ] La API Key de DeepSeek configurada en el entorno (`DEEPSEEK_API_KEY` o variable `Deepseek`).

### Paso 1: Levantar la API

```bash
cd orchestrator
uvicorn main:app --reload
```

La documentación interactiva queda disponible en: `http://127.0.0.1:8000/docs`

### Paso 2: Iniciar una campaña

Haz un `POST` a `/campaign/start` indicando el objetivo y, opcionalmente, el
modo y la profundidad. El sistema construye la misión automáticamente a partir
de esos parámetros.

**Ejemplo mínimo (solo reconocimiento, profundidad estándar):**

```bash
curl -X POST http://127.0.0.1:8000/campaign/start \
  -H "Content-Type: application/json" \
  -d '{"target": "scanme.nmap.org"}'
```

**Ejemplo completo (con todos los parámetros):**

```bash
curl -X POST http://127.0.0.1:8000/campaign/start \
  -H "Content-Type: application/json" \
  -d '{
    "target": "10.10.10.5",
    "sesion_id": 3,
    "modo": "reconocimiento_explotacion",
    "profundidad": "estandar",
    "restricciones": {
      "no_pivoting": true,
      "modo_ctf": true,
      "flag_format": "FLAG{...}",
      "solo_reportar_criticos": false,
      "stealth": false
    }
  }'
```

**Parámetros principales:**

| Campo | Opciones | Default |
|---|---|---|
| `modo` | `solo_reconocimiento` · `reconocimiento_vulnerabilidades` · `reconocimiento_explotacion` | `solo_reconocimiento` |
| `profundidad` | `superficial` (2 iters) · `estandar` (5 iters) · `exhaustivo` (sin límite) | `estandar` |
| `restricciones.no_pivoting` | `true` / `false` | `true` |
| `restricciones.modo_ctf` | `true` / `false` | `false` |
| `restricciones.stealth` | `true` / `false` (minimiza ruido IDS) | `false` |

**Respuesta esperada:**

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
  "iteracion_actual": 0,
  "ruta_reporte": null,
  "error": null,
  "advertencias": []
}
```

### Paso 3: Monitorear el estado

```bash
curl http://127.0.0.1:8000/campaign/status
```

Los estados posibles son:

| Estado | Significado |
|---|---|
| `inactivo` | No hay campaña en curso |
| `ejecutando` | La campaña está corriendo en segundo plano |
| `pausado` | Pausado entre tareas, espera reanudación |
| `detenido` | Detenido manualmente por el usuario |
| `finalizado` | Terminó normalmente, hay reporte disponible |
| `error` | Ocurrió un error; revisar el campo `error` |

### Paso 4: Controlar la campaña

```bash
# Pausar (toma efecto al terminar la tarea actual)
curl -X POST http://127.0.0.1:8000/campaign/pause

# Reanudar
curl -X POST http://127.0.0.1:8000/campaign/resume

# Detener completamente
curl -X POST http://127.0.0.1:8000/campaign/stop
```

### Paso 5: Leer los resultados

Cuando el estado llega a `finalizado`, el campo `ruta_reporte` tiene la ruta del archivo markdown con el reporte ejecutivo. También se genera un reporte de métricas en `orchestrator/metrics/<timestamp>/`.

---

## 3. Entendiendo los resultados

### El reporte ejecutivo (`reports/`)

Al terminar una campaña, el ReporterAgent genera un archivo `.md` en `orchestrator/reports/`. Su estructura típica es:

```
# Reporte de exploración — <objetivo>

## Servicios detectados
Lista de puertos y servicios encontrados (ej. 22/ssh, 80/http).

## Hallazgos relevantes
Observaciones de seguridad importantes: versiones desactualizadas,
configuraciones débiles, rutas sensibles expuestas, etc.

## Flags encontradas
Si la misión era CTF/laboratorio, aquí aparecen las flags capturadas.

## Recomendaciones
Acciones sugeridas basadas en los hallazgos.
```

### La memoria estructurada (Knowledge Base)

Durante la campaña, el Summarizer mantiene una KB con estos campos:

| Campo | Contenido |
|---|---|
| `objetivo` | IP/host evaluado |
| `servicios` | Puertos y servicios detectados |
| `rutas` | Paths HTTP o de sistema encontrados |
| `archivos` | Archivos identificados de interés |
| `flags` | Flags CTF capturadas (copia verbatim) |
| `hallazgos` | Observaciones de seguridad |
| `pendientes` | Tareas que el Explorador quiere hacer después |
| `descartado` | Vectores descartados para no repetirlos |

### Las iteraciones

El Explorador trabaja en ciclos:
1. Planifica un conjunto de tareas.
2. Ejecuta cada tarea y actualiza la KB.
3. Genera un mini-reporte de la iteración.
4. El Juez decide si aprueba (termina) o rechaza (pide más exploración).

Cada iteración aparece en el reporte de métricas con su decisión.

---

## 4. Ejemplo real: desde inicio a fin

Este ejemplo muestra una campaña completa contra `scanme.nmap.org` (host público de prueba de Nmap, autorizado para esto).

### 1. Levantar el sistema

```bash
# Terminal 1: levantar el runner (del equipo de backend)
docker-compose up  # dentro del repo del runner

# Terminal 2: levantar el orquestador
cd orchestrator
uvicorn main:app --reload
```

### 2. Iniciar la campaña

La misión ya no se escribe en un archivo: se construye automáticamente a partir
de los parámetros del request.

```bash
curl -X POST http://127.0.0.1:8000/campaign/start \
  -H "Content-Type: application/json" \
  -d '{
    "target": "scanme.nmap.org",
    "modo": "solo_reconocimiento",
    "profundidad": "estandar"
  }'
```

### 4. Esperar y monitorear

```bash
# Consultar cada 30 segundos (aprox. 3-10 min en total)
watch -n 30 'curl -s http://127.0.0.1:8000/campaign/status | python3 -m json.tool'
```

### 5. Leer los resultados

Cuando el estado sea `finalizado`:

```bash
# Ver el reporte ejecutivo (ruta en campo ruta_reporte del status)
cat orchestrator/reports/<nombre_del_archivo>.md

# Ver las métricas
ls orchestrator/metrics/
cat orchestrator/metrics/<timestamp>/reporte_metricas.md
```

### Qué verías en el reporte

```
## Servicios detectados
- 22/tcp   open  ssh      OpenSSH 6.6.1p1
- 80/tcp   open  http     Apache httpd 2.4.7
- 31337/tcp open  Elite?

## Hallazgos relevantes
- Apache 2.4.7 es una versión antigua (2014), sin soporte activo.
- Puerto 31337 abierto: verificar si corresponde a un servicio legítimo.

## Recomendaciones
- Actualizar Apache a versión estable actual.
- Revisar el servicio en puerto 31337.
```

---

## 5. Glosario (términos simples)

| Término | Explicación |
|---|---|
| **Orquestador** | El sistema principal (Dani-ETH) que coordina todos los agentes y decide el flujo. |
| **Agente** | Un componente con IA especializado en una tarea (explorar, juzgar, resumir, reportar). |
| **Runner** | Servicio externo que ejecuta las herramientas de pentest en contenedores Docker aislados. |
| **Campaña** | Una ejecución completa desde que das el objetivo hasta que se genera el reporte. |
| **Iteración** | Un ciclo de trabajo del Explorador: planifica → ejecuta → reporta. |
| **KB (Knowledge Base)** | La "memoria de trabajo" estructurada del Explorador. Solo guarda lo relevante, no el output crudo. |
| **Summarizer** | El agente que comprime los resultados brutos en la KB. Evita que el contexto del LLM crezca sin control. |
| **Juez** | El agente que decide si la exploración fue suficiente o debe continuar. |
| **Commander** | Agente que coordina las fases (reconocimiento → explotación). Actualmente gestiona el flujo general. |
| **Reporter** | El agente que escribe el reporte ejecutivo final en markdown. |
| **Selector** | El agente que elige qué herramientas son pertinentes según la fase actual. |
| **Tool calling** | Mecanismo por el que el LLM pide ejecutar una herramienta específica con parámetros estructurados. |
| **Ethical hacking** | Pruebas de seguridad autorizadas para encontrar vulnerabilidades antes que actores maliciosos. |
| **Black box** | El sistema no recibe información previa del objetivo; lo descubre todo por sí mismo. |
| **Sesión ID** | Identificador numérico de sesión que usa el runner para separar ejecuciones. |
| **Token** | Unidad de texto que el LLM procesa. El costo del API de DeepSeek se mide en tokens. |
| **Polling** | Consultar repetidamente el estado de una tarea hasta que termine (el executor es asíncrono). |

---

## 6. Solución de problemas

### El status devuelve `error`

Revisa el campo `error` en la respuesta de `/campaign/status`. Los casos más comunes:

**Runner no disponible:**
```
Connection refused to http://127.0.0.1:8003
```
Solución: Verificar que el runner está corriendo con `docker-compose ps`. Consultar `Docs/problemas_runner.md`.

**API Key inválida o no configurada:**
```
AuthenticationError: Incorrect API key provided
```
Solución: Revisar que la variable de entorno `Deepseek` (o `DEEPSEEK_API_KEY`) está configurada y es válida.

**`modo` o `profundidad` con valor no reconocido:**
```
422 {"error": "valor_invalido", "campo": "modo", ...}
```
Solución: Usar uno de los valores del enum (`solo_reconocimiento`, `reconocimiento_vulnerabilidades`, `reconocimiento_explotacion`). Si se omite el campo, el sistema aplica el default automáticamente.

---

### La campaña queda en `ejecutando` para siempre

El proceso corre en un hilo de fondo. Si el runner no responde en el tiempo de polling (`~5 min`), la tarea quedará bloqueada esperando. Opciones:

1. Revisar los logs en la terminal donde corre uvicorn.
2. Detener la campaña con `POST /campaign/stop`.
3. Reiniciar el orquestador si el hilo colgó.

---

### `POST /campaign/start` devuelve 409

Significa que ya hay una campaña en curso. Solo puede correr una a la vez:

```bash
# Detener la campaña actual primero
curl -X POST http://127.0.0.1:8000/campaign/stop

# Esperar a que el estado sea "detenido" o "finalizado"
curl http://127.0.0.1:8000/campaign/status

# Luego iniciar la nueva
curl -X POST http://127.0.0.1:8000/campaign/start ...
```

---

### No se generó el reporte ejecutivo

Puede ocurrir si la campaña fue detenida manualmente antes de que el Reporter terminara. El reporte de métricas sí se genera aunque no haya reporte ejecutivo.

---

### El Juez nunca aprueba (demasiadas iteraciones)

El sistema tiene un límite máximo de iteraciones para evitar loops infinitos (configurable en `agents/explorer.py`). Si el Juez rechaza siempre, puede ser porque:

- El `modo` elegido es muy exigente para lo que el target permite (ej. `reconocimiento_explotacion` en un host muy restrictivo).
- El runner no está ejecutando herramientas exitosamente (verificar tasa de éxito en métricas).
- Las restricciones y el target no coinciden (ej. `modo_ctf: true` en un host sin CTF activo).

---

### El endpoint `/campaign` devuelve 404

Asegúrate de lanzar uvicorn **desde la carpeta `orchestrator/`**, no desde la raíz del proyecto:

```bash
# CORRECTO
cd orchestrator && uvicorn main:app --reload

# INCORRECTO (dará 404 en /campaign/*)
uvicorn orchestrator.main:app --reload
```

---

## 7. Interpretando métricas

Al terminar una campaña, se genera un reporte de métricas en `orchestrator/metrics/<YYYY-MM-DD_HH-MM-SS>/`. Contiene un `reporte_metricas.md` y gráficos PNG embebidos.

### Resumen ejecutivo

| Campo | Qué indica |
|---|---|
| **Iteraciones** | Cuántos ciclos planificó el Explorador. Más iteraciones = objetivo más complejo o Juez más exigente. |
| **Llamadas al LLM** | Total de peticiones a DeepSeek. Incluye todos los agentes. |
| **Tokens totales** | Volumen de texto procesado. Afecta directamente el costo. |
| **Costo estimado** | Aproximación en USD según tarifas de DeepSeek. No incluye impuestos ni fees adicionales. |
| **Tareas ejecutadas** | Cuántas veces el runner corrió una herramienta. |
| **Tasa de éxito** | Porcentaje de tareas que terminaron con código de salida 0 (éxito). Baja tasa = problemas en el runner. |
| **Tiempo LLM / runner** | Dónde pasó el tiempo. Si el runner domina, la ejecución de herramientas fue el cuello de botella. |

### Gráfico: Distribución del tiempo

Muestra cómo se dividió el tiempo total entre:
- **LLM (pensar):** tiempo esperando respuesta de DeepSeek.
- **Runner (ejecutar):** tiempo esperando que las herramientas terminen.
- **Otro/overhead:** tiempo del orquestador en sí.

Si "Runner" domina ampliamente, el cuello de botella está en la ejecución de herramientas (normal para herramientas lentas como nmap).

### Gráfico: Tokens por agente

Muestra qué agente consumió más tokens. El Explorador suele ser el mayor consumidor porque es el que más ciclos ejecuta. Si el Summarizer consume muchos tokens, la KB está creciendo más de lo esperado.

### Gráfico: Ahorro de contexto del Summarizer

Compara:
- **Crudo acumulado:** cuántos caracteres tendría el historial si se arrastrara todo el output de las herramientas.
- **Memoria estructurada (KB):** cuántos caracteres ocupa realmente la KB.

Una compresión de 5× o más indica que el Summarizer funciona bien. Una compresión baja (< 2×) puede indicar que los outputs de las herramientas son cortos o que la KB está capturando demasiado texto.

### Gráfico: Tareas por iteración

Muestra cuántas tareas planificó el Explorador en cada iteración. Un número decreciente suele ser bueno: el Explorador está convergiendo. Un número constante alto puede indicar que repite trabajo o que el target tiene muchos vectores.

### Tabla: Acuerdo IA ↔ Juez

| Situación | Interpretación |
|---|---|
| Ambos coinciden en terminar | Ideal: ambos agentes convergen en que la misión está cumplida. |
| Ambos coinciden en seguir | El objetivo requiere más iteraciones; ambos lo reconocen. |
| IA quería terminar, Juez insistió | El Explorador se rindió antes de tiempo; el Juez forzó más trabajo. |
| IA quería seguir, Juez aprobó | El Juez consideró suficiente el trabajo aunque el Explorador quería continuar. |

Un alto número de "Juez insistió" puede indicar que el `modo` o la `profundidad` elegidos son más exigentes de lo que el Explorador logra cubrir con los vectores disponibles en el target.

### Gráfico: Éxito vs fallo por herramienta

Muestra la tasa de éxito de cada herramienta del runner. Fallos frecuentes en una herramienta específica suelen indicar:
- La imagen Docker de esa herramienta no está construida en el runner.
- Los parámetros enviados no coinciden con el esquema esperado.
- El target rechaza activamente ese tipo de prueba (ej. firewall bloqueando nmap).

Consultar `Docs/problemas_runner.md` para problemas conocidos del runner.

### Cobertura final (KB)

Muestra cuántos elementos hay en cada categoría de la KB al terminar la campaña. Útil para evaluar profundidad de la exploración:

- **Servicios ≥ 3** con una misión de reconocimiento = cobertura básica.
- **Flags = 0** con una misión CTF = la misión no se cumplió.
- **Pendientes > 0** al terminar = el Explorador identificó vectores que no alcanzó a explorar.

---

*Para dudas técnicas sobre la integración con el runner, consultar `Docs/integracion_runner.md`. Para problemas del runner, ver `Docs/problemas_runner.md`.*
