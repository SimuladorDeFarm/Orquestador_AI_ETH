# Dani-ETH

Orquestador autónomo de ethical hacking con IA (Multi-Agent System) que ejecuta pentests en modalidad black box sobre infraestructuras digitales autorizadas.

---

## Requisitos

- **Python 3.11+**
- **API key de DeepSeek** (variable `Deepseek` en `.env`)
- **El runner corriendo** — servicio externo que ejecuta las herramientas:
  - Tool Registry en `http://127.0.0.1:8003`
  - Tool Executor en `http://127.0.0.1:8004`

> El orquestador **no ejecuta herramientas localmente**: se las pide por HTTP al runner. Si el runner no está arriba, no hay ejecución.

---

## Cómo ejecutar

### 1. Instalación

```bash
git clone https://github.com/SimuladorDeFarm/dani-eth.git
cd dani-eth

python3 -m venv evn
source evn/bin/activate
pip install -r requirements.txt

cp .env.example .env     # y agregar la API key de DeepSeek
```

### 2. Definir la misión

Editá la misión (objetivo) en texto plano en [`orchestrator/objetivo.txt`](orchestrator/objetivo.txt):

```text
Encuentra 1 flag con formato flag{...} en el sistema objetivo.
```

### 3. Levantar la API

> ⚠️ Levantar **desde `orchestrator/`** (no desde la raíz, o los endpoints `/campaign` darán 404).

```bash
cd orchestrator
uvicorn main:app --reload        # docs interactivas: http://127.0.0.1:8000/docs
```

### 4. Controlar la campaña (endpoints)

| Método | Ruta | Acción |
|---|---|---|
| POST | `/campaign/start` | Inicia la exploración. Body: `{"target": "scanme.nmap.org", "sesion_id": 3}` |
| POST | `/campaign/pause` | Pausa (toma efecto en el próximo checkpoint) |
| POST | `/campaign/resume` | Reanuda |
| POST | `/campaign/stop` | Detiene la campaña |
| GET | `/campaign/status` | Estado actual (`estado`, `target`, `iteracion_actual`, `ruta_reporte`, …) |

El flujo genera automáticamente un reporte markdown en `orchestrator/reports/reporte_YYYY-MM-DD_HH-MM-SS.md`.

### Alternativa por CLI

Corre una campaña con el `TARGET` por defecto de `agents/explorer.py`:

```bash
cd orchestrator
python3 -m agents.explorer
```

---

## Variables de entorno

```env
Deepseek=sk-...                              # requerida
RUNNER_REGISTRY_URL=http://127.0.0.1:8003    # opcional (default)
RUNNER_EXECUTOR_URL=http://127.0.0.1:8004    # opcional (default)
SESION_ID=3                                  # opcional (sesión del runner)
```

---

## Arquitectura de agentes (MAS)

Cada agente es una instancia de la API de DeepSeek con un system prompt propio. La ejecución de herramientas se delega al runner HTTP.

```
BaseAgent                  → historial, preguntar() genérico
  ├── IterableAgent        → + decidir_iteracion()
  │     └── ExplorerAgent  → memoria (KB) + summarizer, ejecuta vía runner, planifica tareas
  │     └── ExploiterAgent → (pendiente)
  ├── JudgeAgent           → + aprueba, evaluar_reporte()
  ├── SummarizerAgent      → actualizar_memoria(): mantiene la KB del Explorador
  └── SelectorAgent        → seleccionar(): elige el pool de herramientas por rol

ReporterAgent(BaseAgent)   → generar_reporte(), guarda .md en reports/
```

- **ExplorerAgent** (reconocimiento): ejecuta herramientas con parámetros estructurados vía runner; mantiene una **memoria de trabajo estructurada (KB)** en vez de arrastrar todo el transcript (ahorra tokens). El output crudo se guarda aparte, fuera del contexto del LLM.
- **SummarizerAgent**: integra el resultado de cada comando en la KB `{servicios, rutas, archivos, flags, hallazgos, pendientes, descartado}`, copiando verbatim flags/paths/versiones.
- **SelectorAgent**: dado el catálogo del runner, elige el subconjunto de herramientas pertinente al rol (`reconocimiento`, `explotación`). Lo usa cualquier agente que lance comandos.
- **JudgeAgent**: evalúa el reporte de cada iteración contra la misión; aprueba o rechaza.
- **ReporterAgent**: sintetiza el reporte ejecutivo final.

### Flujo de ejecución

```
POST /campaign/start → CampaignManager (hilo de fondo) → run_campaign()
  └── crear_explorador(): Selector elige pool + Summarizer + memoria(target)
  └── loop (hasta que el Juez apruebe o máx. iteraciones):
        explorador():
          FASE 1 — planificar tareas (nmap inicial en la 1ª iteración)
          FASE 2 — ejecutar cada tarea en el runner → la memoria (KB) se actualiza
          FASE 3 — reporte markdown de la iteración (desde la memoria)
        decidir_iteracion()    ← Explorer decide si continuar
        juez.evaluar_reporte() ← Juez aprueba o rechaza
  └── reportador.generar_reporte()  ← reporte ejecutivo final en reports/
```

Control cooperativo de la campaña (en checkpoints entre tareas): `pause` / `resume` / `stop`.

---

## El runner (servicio externo)

| Servicio | Puerto | Rol |
|---|---|---|
| Tool Registry | `8003` | Cataloga herramientas y sus `esquema_input` (`GET /herramientas/para-orquestador`). |
| Tool Executor | `8004` | Ejecuta una herramienta (asíncrono: `POST /ejecutar/` → `tarea_id`, luego `GET /ejecutar/tareas/{id}`). |

Detalle de la integración en [`Docs/integracion_runner.md`](Docs/integracion_runner.md). Problemas conocidos del runner en [`Docs/problemas_runner.md`](Docs/problemas_runner.md).

---

## Estructura del proyecto

```
orchestrator/
├── main.py                         # App FastAPI (incluye el router de campaign)
├── config.py                       # DEEPSEEK_*, RUNNER_*_URL, SESION_ID, cargar_objetivo()
├── objetivo.txt                    # Misión editable
├── reports/                        # Reportes ejecutivos generados (markdown)
├── agents/
│   ├── base_agent.py / iterable_agent.py
│   ├── explorer_agent.py / explorer.py        # Explorador: memoria + runner + flujo
│   ├── judge_agent.py / judge.py
│   ├── reporter_agent.py / reporter.py
│   ├── summarizer_agent.py / summarizer.py    # Memoria de trabajo (KB)
│   └── selector_agent.py / selector.py        # Pool de herramientas por rol
├── core/
│   ├── runner_client.py            # Cliente HTTP del runner (listar_herramientas, ejecutar)
│   └── campaign_manager.py         # CampaignManager (hilo + pause/stop) + run_campaign()
└── routes/
    └── campaign.py                 # /campaign/{start,pause,resume,stop,status}

Docs/
├── integracion_runner.md
└── problemas_runner.md
```

---

> Este proyecto es de uso exclusivo para pruebas de penetración autorizadas. No operar sin el consentimiento explícito del titular del sistema objetivo.
