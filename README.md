# Dani-ETH

Orquestador autónomo de ethical hacking con IA (Multi-Agent System) que ejecuta pentests en modalidad black box sobre infraestructuras digitales autorizadas.

---

## Estado actual

El proyecto se encuentra en refactorización activa. Conviven dos versiones:

- `V1/` — versión inicial funcional con Gemini API y endpoints de control via FastAPI
- `orchestrator/` — nueva arquitectura modular con DeepSeek API y tool calling

El desarrollo activo ocurre en `orchestrator/`.

---

## Arquitectura (orchestrator/)

```
orchestrator/
├── main.py
├── config.py                  # API keys y parámetros globales
├── agents/
│   ├── base_agent.py          # Conexión DeepSeek, tool calling, historial
│   ├── explorer.py            # Agente de reconocimiento (en desarrollo)
│   ├── commander.py
│   ├── exploiter.py
│   ├── reporter.py
│   └── judge.py
├── core/
│   ├── runner_client.py       # Ejecuta comandos en Docker
│   ├── campaign_manager.py
│   └── scope_guard.py
└── models/
```

---

## Requisitos

- Python 3.11+
- Docker con un contenedor objetivo corriendo
- API key de DeepSeek

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/SimuladorDeFarm/dani-eth.git
cd dani-eth

# 2. Crear y activar entorno virtual
python3 -m venv evn
source evn/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env y agregar la API key de DeepSeek
```

---

## Variables de entorno

```env
Deepseek=sk-...
DOCKER_CONTAINER=nombre_del_contenedor
```

---

## Ejecución

El punto de entrada actual es el agente Explorer para pruebas:

```bash
cd orchestrator
python3 -m agents.explorer
```

Esto ejecuta el flujo completo:
1. Escaneo inicial con nmap
2. Generación de lista de tareas por la IA
3. Ejecución de cada tarea en el contenedor Docker
4. Reporte de hallazgos en markdown

Para correr la API (V1, estable):

```bash
# Activar entorno virtual primero
source evn/bin/activate
uvicorn main:app --reload
```

---

## Contenedor Docker objetivo

El agente ejecuta los comandos dentro de un contenedor Docker. Antes de correr el explorador, asegúrate de tener el contenedor activo y con algún servicio expuesto:

```bash
# Verificar que el contenedor está corriendo
docker ps

# Ejemplo: abrir un puerto en el contenedor
docker exec -it nombre_contenedor nc -lnvp 8000 -k
```

El nombre del contenedor se configura en `.env` con la variable `DOCKER_CONTAINER`.

---

> Este proyecto es de uso exclusivo para pruebas de penetración autorizadas. No operar sin el consentimiento explícito del titular del sistema objetivo.
