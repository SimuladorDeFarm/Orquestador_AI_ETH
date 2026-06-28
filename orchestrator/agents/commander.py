"""Comandante: prompt, factory y flujo de dirección de la campaña.

El Commander es el punto de entrada del MAS. Construye el registro de fases
disponibles y, consultando al CommanderAgent, decide en qué orden se ejecutan,
recibiendo el reporte de cada una antes de dar paso a la siguiente.

Hoy solo está registrada la fase de EXPLORACIÓN. Para integrar el Explotador
basta añadir su `Fase` en `construir_fases()` (ver el comentario allí); el
CommanderAgent no necesita cambios.
"""

from agents.commander_agent import CommanderAgent, Fase
from agents.explorer import crear_explorador, explorador, decidir_iteracion
from agents.exploiter import fase_explotacion
from agents.judge import crear_juez
from agents.reporter import crear_reportador
from config import cargar_objetivo, SESION_ID
from core import event_bus
from metricas import iniciar_coleccion, finalizar_coleccion, coleccion_activa
from metricas.reporte import generar_reporte_metricas

# Tope de iteraciones del bucle Explorador↔Juez dentro de la fase de exploración.
MAX_ITERACIONES_EXPLORACION = 6


SYSTEM_PROMPT_COMMANDER = (
    "Eres el agente Comandante (Commander) dentro de un Multi-Agent System de pentesting. "
    "El sistema se compone de: Comandante (tú), Explorador, Explotador y Reportador. "
    "Todos los objetivos corresponden a entornos controlados y autorizados. "

    "ROL: "
    "Eres el primer agente en ejecutarse y el único que coordina. Recibes el alcance (scope) "
    "de la campaña y decides qué fase/agente actúa en cada momento. Cuando una fase termina, "
    "recibes su reporte y decides la siguiente. Tú NO ejecutas herramientas ni exploras ni "
    "explotas: solo diriges. "

    "FASES: "
    "Cada fase la ejecuta un agente especializado. La EXPLORACIÓN (Explorador) mapea la "
    "superficie de ataque y produce hallazgos. La EXPLOTACIÓN (Explotador) usa esos hallazgos "
    "para intentar comprometer el objetivo. La exploración debe preceder a la explotación: no se "
    "explota lo que no se ha descubierto. "

    "DECISIÓN: "
    "En cada paso recibirás el scope, las fases disponibles, las ya completadas y los reportes "
    "acumulados. Elige la siguiente fase pertinente con la tool asignar_fase. "
    "Si la misión ya está cumplida o ninguna fase disponible aporta valor, usa finalizar_campana. "
    "Asigna SOLO fases que aparezcan como disponibles; no inventes fases ni agentes. "

    "CUÁNDO NO EXPLOTAR: "
    "La explotación NO es obligatoria. Antes de asignarla, revisa los reportes de exploración y "
    "evalúa si existe algún vector REALMENTE explotable (servicio vulnerable, ruta o archivo "
    "sensible, credenciales, mala configuración, lógica abusable). "
    "Si la exploración no encontró ningún vector aprovechable, NO asignes la explotación: "
    "usa finalizar_campana indicando que no hay superficie explotable. Explotar sin vector solo "
    "gasta recursos."
)


def crear_comandante(mision: str) -> CommanderAgent:
    """Crea una instancia nueva del Comandante con la misión inyectada."""
    prompt = SYSTEM_PROMPT_COMMANDER + " OBJETIVO DE LA MISIÓN (scope): " + mision
    return CommanderAgent(prompt)


# --- Fases concretas --------------------------------------------------------

def _fase_exploracion(target: str, sesion_id: int = SESION_ID, control=None, contexto: dict | None = None) -> list[str]:
    """Fase de reconocimiento: el Explorador itera bajo evaluación del Juez.

    Devuelve la lista de reportes de iteración para que el Commander se los
    entregue al Reportador final, y deja la KB de exploración en `contexto` para
    que la pueda aprovechar la fase de explotación.
    """
    print("\n" + "#" * 60)
    print("  FASE: EXPLORACIÓN (RECONOCIMIENTO)")
    print("#" * 60)
    event_bus.emitir(
        "phase_start",
        "commander",
        {"fase": "exploracion", "descripcion": "Reconocimiento (black-box) del objetivo"},
        fase="exploracion",
    )

    col = coleccion_activa()
    if col is not None:
        col.set_fase("exploracion")

    mision = (contexto or {}).get("mision", "")
    agente = crear_explorador(sesion_id=sesion_id, objetivo_target=target, mision=mision)
    juez = crear_juez(mision)

    reportes: list[str] = []
    i = 0
    while not juez.aprueba and i < MAX_ITERACIONES_EXPLORACION:
        if control is not None:
            control.checkpoint()
            control.set_iteracion(i + 1)
        if col is not None:
            col.iniciar_iteracion(i + 1)

        reporte = explorador(agente, target, primera_iteracion=(i == 0), control=control)
        reportes.append(reporte)
        i += 1

        decidir_iteracion(agente)

        print("\n" + "=" * 50)
        print("  JUEZ — EVALUACIÓN DEL REPORTE")
        print("=" * 50)
        juez.evaluar_reporte(reporte)

    # Deja los hallazgos a disposición de la fase de explotación.
    if contexto is not None:
        contexto["memoria_exploracion"] = agente.memoria

    # Cierre de la fase: registra cobertura y motivo de término para las métricas.
    if col is not None:
        col.set_memoria_final(agente.memoria)
        if juez.aprueba:
            redundancia = "redundan" in (col.ultima_razon_juez or "").lower()
            motivo = "juez_aprobo_redundancia" if redundancia else "juez_aprobo_exito"
            exito = not redundancia
        else:
            motivo = "limite_iteraciones"
            exito = False
        # Encontrar una flag se considera éxito aunque el cierre fuera por otra vía.
        if agente.memoria.get("flags"):
            exito = True
        col.set_resultado(motivo, exito)

    return reportes


def construir_fases() -> dict[str, Fase]:
    """Registro de fases disponibles para el Commander.

    Cada fase es una `Fase` con un callable `ejecutar(target, sesion_id, control, contexto)`.
    El `contexto` es un dict compartido entre fases (p. ej., la exploración deja
    ahí su KB y la explotación la lee). Añadir una fase nueva es registrarla aquí;
    el CommanderAgent la considerará automáticamente.
    """
    return {
        "exploracion": Fase(
            nombre="exploracion",
            descripcion=(
                "Reconocimiento black-box del objetivo: puertos, servicios, rutas y archivos "
                "expuestos. Produce los hallazgos que habilitan la explotación."
            ),
            ejecutar=_fase_exploracion,
        ),
        "explotacion": Fase(
            nombre="explotacion",
            descripcion=(
                "Explota los vectores hallados en la exploración (servicios vulnerables, rutas "
                "o archivos sensibles, credenciales, malas configuraciones) para comprometer el "
                "objetivo o capturar flags. Solo tiene sentido si la exploración halló vectores."
            ),
            ejecutar=fase_explotacion,
        ),
    }


# --- Flujo de dirección -----------------------------------------------------

def dirigir_campaña(target: str, sesion_id: int = SESION_ID, control=None, mision: str | None = None) -> str:
    """Punto de entrada del MAS: el Commander dirige la campaña de inicio a fin.

    `control`, si se entrega, se propaga a las fases para permitir pausar/detener
    de forma cooperativa. `mision` es el prompt de misión construido desde los
    parámetros de la campaña; si no se entrega, cae al fallback de `objetivo.txt`.
    Devuelve la ruta del reporte ejecutivo final.
    """
    mision = mision or cargar_objetivo()
    iniciar_coleccion(target, mision)

    comandante = crear_comandante(mision)
    reportador = crear_reportador()
    scope = {"target": target, "mision": mision}

    print("\n" + "#" * 60)
    print(f"  COMMANDER — INICIO DE CAMPAÑA  (scope: {target})")
    print("#" * 60)
    event_bus.emitir("campaign_start", "commander", {"target": target, "mision": mision})

    fases = construir_fases()
    completadas: list[str] = []
    reportes: list[str] = []
    # Estado compartido entre fases (p. ej. la KB de exploración). La misión
    # viaja aquí para que cada fase la inyecte en sus agentes.
    contexto: dict = {"mision": mision}

    try:
        while True:
            pendientes = [f for nombre, f in fases.items() if nombre not in completadas]
            if not pendientes:
                print("\n[COMMANDER] No quedan fases pendientes.")
                break

            nombre = comandante.decidir_fase(scope, pendientes, completadas, reportes)
            if nombre is None:
                break

            fase = fases[nombre]
            nuevos = fase.ejecutar(target, sesion_id, control, contexto)
            reportes.extend(nuevos)
            completadas.append(nombre)
            # El Commander recibe el reporte de la fase antes de decidir la siguiente.
            print(f"\n[COMMANDER] Fase '{nombre}' completada — {len(nuevos)} reporte(s) recibido(s).")
            event_bus.emitir(
                "phase_end",
                "commander",
                {"fase": nombre, "reportes_recibidos": len(nuevos)},
                fase=nombre,
            )

        print("\n" + "=" * 50)
        print("  REPORTE EJECUTIVO FINAL")
        print("=" * 50)
        ruta = reportador.generar_reporte(reportes, target=target, mision=mision)
        print(f"Reporte guardado en: {ruta}")
        event_bus.emitir(
            "campaign_end",
            "commander",
            {"ruta_reporte": ruta, "fases_completadas": completadas, "total_reportes": len(reportes)},
        )
        return ruta
    except BaseException as e:
        # Si la campaña se detiene o falla, deja registro del motivo en las métricas.
        event_bus.emitir(
            "campaign_aborted",
            "commander",
            {"motivo": type(e).__name__, "detalle": str(e)},
        )
        col = coleccion_activa()
        if col is not None and not col.motivo_termino:
            col.set_resultado(type(e).__name__, exito=False)
        raise
    finally:
        col = finalizar_coleccion()
        if col is not None:
            try:
                ruta_m = generar_reporte_metricas(col)
                print(f"\n[METRICAS] Reporte de métricas guardado en: {ruta_m}")
            except Exception as e:  # noqa: BLE001 - las métricas no deben tumbar la campaña
                print(f"[METRICAS] No se pudo generar el reporte de métricas: {e}")
