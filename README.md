# Dani-ETH

Orquestador autónomo de ethical hacking con IA (Multi-Agent System) que ejecuta pentests en modalidad black box sobre infraestructuras digitales autorizadas.

---

## Estado actual

El desarrollo activo ocurre en `orchestrator/`. La carpeta `V1/` es la versión inicial con Gemini API y FastAPI, conservada como referencia.

---

## Arquitectura de agentes

```
BaseAgent              → historial, preguntar() genérico
  ├── IterableAgent    → + continuar_iteracion, decidir_iteracion()
  │     └── ExplorerAgent  → + lista_tareas, preguntar() con Docker, generar_tareas()
  └── JudgeAgent       → + aprueba, evaluar_reporte()

ReporterAgent(BaseAgent) → generar_reporte(), guarda .md en reports/
```

### Flujo de ejecución

```
iterador()
  └── explorador()
        ├── FASE 1 — escaneo inicial con nmap (solo primera iteración)
        │           o generar nuevas tareas (iteraciones siguientes)
        ├── FASE 2 — ejecución de tareas en Docker
        └── FASE 3 — reporte markdown de la iteración
  └── decidir_iteracion()   ← Explorer decide si continuar
  └── juez.evaluar_reporte() ← Juez aprueba o rechaza
        └── si aprueba → sale del loop
        └── si rechaza → nueva iteración (máx. 3)
  └── reportador.generar_reporte()  ← reporte ejecutivo final guardado en reports/
```

---

## Estructura del proyecto

```
orchestrator/
├── config.py                      # API keys y parámetros globales
├── reports/                       # Reportes ejecutivos generados (markdown)
├── agents/
│   ├── base_agent.py              # Clase base: historial + preguntar()
│   ├── iterable_agent.py          # + continuar_iteracion, decidir_iteracion()
│   ├── explorer_agent.py          # + lista_tareas, Docker, generar_tareas()
│   ├── judge_agent.py             # + aprueba, evaluar_reporte()
│   ├── reporter_agent.py          # + generar_reporte() con guardado a archivo
│   ├── explorer.py                # Instancia ExplorerAgent + funciones de flujo
│   ├── judge.py                   # Instancia JudgeAgent + system prompt
│   ├── reporter.py                # Instancia ReporterAgent + system prompt
│   ├── commander.py               # (pendiente)
│   └── exploiter.py               # (pendiente)
└── core/
    └── runner_client.py           # Ejecuta comandos en Docker vía subprocess
```

---

## Requisitos

- Python 3.11+
- Docker con un contenedor objetivo corriendo
- API key de DeepSeek

---

## Instalación

```bash
git clone https://github.com/SimuladorDeFarm/dani-eth.git
cd dani-eth

python3 -m venv evn
source evn/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Agregar la API key de DeepSeek en .env
```

---

## Variables de entorno

```env
Deepseek=sk-...
DOCKER_CONTAINER=nombre_del_contenedor
```

---

## Ejecución

```bash
cd orchestrator
python3 -m agents.explorer
```

Antes de correr, ajusta el objetivo en [agents/explorer.py](orchestrator/agents/explorer.py):

```python
TARGET = "192.168.1.1"  # IP o dominio objetivo
```

El flujo genera automáticamente un reporte markdown en `orchestrator/reports/reporte_YYYY-MM-DD_HH-MM-SS.md`.

---

## Contenedor Docker objetivo

Los comandos se ejecutan dentro del contenedor. Debe estar corriendo antes de lanzar el explorador:

```bash
docker ps

# Ejemplo: servir archivos en el contenedor
docker exec -it nombre_contenedor python3 -m http.server 8000
```

El nombre del contenedor se configura en `core/runner_client.py` con la variable `NOMBRE_CONTENEDOR`.

---

> Este proyecto es de uso exclusivo para pruebas de penetración autorizadas. No operar sin el consentimiento explícito del titular del sistema objetivo.
