"""Comandante: prompt, factory y flujo de dirección de la campaña.

El Commander es el punto de entrada del MAS. Construye el registro de fases
disponibles y, consultando al CommanderAgent, decide en qué orden se ejecutan,
recibiendo el reporte de cada una antes de dar paso a la siguiente.

Hoy solo está registrada la fase de EXPLORACIÓN. Para integrar el Explotador
basta añadir su `Fase` en `construir_fases()` (ver el comentario allí); el
CommanderAgent no necesita cambios.
"""

from agents.commander_agent import CommanderAgent, Fase
from agents.explorer import crear_explorador, explorador, decidir_iteracion, reporte_parcial
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

    # Import diferido para evitar el ciclo commander <-> campaign_manager.
    from core.campaign_manager import CampañaDetenida

    mision = (contexto or {}).get("mision", "")
    agente = crear_explorador(sesion_id=sesion_id, objetivo_target=target, mision=mision)
    juez = crear_juez(mision)

    # Acumulador compartido: los reportes se registran aquí a medida que se
    # completan, para que el Reportador pueda incluir los hallazgos parciales
    # aunque la campaña se detenga a mitad de la fase.
    acumulador = contexto.setdefault("reportes", []) if contexto is not None else []
    reportes: list[str] = []
    i = 0
    detenida = False
    try:
        while not juez.aprueba and i < MAX_ITERACIONES_EXPLORACION:
            if control is not None:
                control.checkpoint()
                control.set_iteracion(i + 1)
            if col is not None:
                col.iniciar_iteracion(i + 1)

            reporte = explorador(agente, target, primera_iteracion=(i == 0), control=control)
            reportes.append(reporte)
            acumulador.append(reporte)
            i += 1

            decidir_iteracion(agente)

            print("\n" + "=" * 50)
            print("  JUEZ — EVALUACIÓN DEL REPORTE")
            print("=" * 50)
            juez.evaluar_reporte(reporte)
    except CampañaDetenida:
        # Detención cooperativa: rescata los hallazgos de la iteración en curso
        # antes de propagar, para que el reporte final no los pierda.
        detenida = True
        print("\n[EXPLORACIÓN] Campaña detenida; generando un reporte parcial desde la memoria...")
        try:
            parcial = reporte_parcial(agente)
            if parcial:
                reportes.append(parcial)
                acumulador.append(parcial)
        except Exception as e:  # noqa: BLE001 - el reporte parcial es best-effort
            print(f"[EXPLORACIÓN] No se pudo generar el reporte parcial: {e}")
        raise
    finally:
        # Deja los hallazgos a disposición de la fase de explotación.
        if contexto is not None:
            contexto["memoria_exploracion"] = agente.memoria

        # Cierre de la fase: registra cobertura y motivo de término para las métricas.
        if col is not None:
            col.set_memoria_final(agente.memoria)
            if detenida:
                col.set_resultado("detenido_usuario", exito=bool(agente.memoria.get("flags")))
            elif juez.aprueba:
                redundancia = "redundan" in (col.ultima_razon_juez or "").lower()
                motivo = "juez_aprobo_redundancia" if redundancia else "juez_aprobo_exito"
                # Encontrar una flag se considera éxito aunque el cierre fuera por otra vía.
                exito = (not redundancia) or bool(agente.memoria.get("flags"))
                col.set_resultado(motivo, exito)
            else:
                col.set_resultado("limite_iteraciones", exito=bool(agente.memoria.get("flags")))

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

    # Import diferido para evitar el ciclo commander <-> campaign_manager.
    from core.campaign_manager import CampañaDetenida

    fases = construir_fases()
    completadas: list[str] = []
    reportes: list[str] = []
    # Estado compartido entre fases (p. ej. la KB de exploración). La misión
    # viaja aquí para que cada fase la inyecte en sus agentes. `reportes` es el
    # mismo objeto que el acumulador de las fases: así, si la campaña se detiene
    # a mitad de una fase, los reportes ya completados (y el parcial de rescate)
    # siguen disponibles para el reporte ejecutivo.
    contexto: dict = {"mision": mision, "reportes": reportes}
    detenida = False

    try:
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
                # Las fases acumulan sus reportes en contexto["reportes"] (== reportes).
                nuevos = fase.ejecutar(target, sesion_id, control, contexto)
                completadas.append(nombre)
                # El Commander recibe el reporte de la fase antes de decidir la siguiente.
                print(f"\n[COMMANDER] Fase '{nombre}' completada — {len(nuevos)} reporte(s) recibido(s).")
                event_bus.emitir(
                    "phase_end",
                    "commander",
                    {"fase": nombre, "reportes_recibidos": len(nuevos)},
                    fase=nombre,
                )
        except CampañaDetenida:
            # Detención solicitada por el usuario: NO se aborta la campaña. Se cae
            # al reporte ejecutivo con los hallazgos acumulados hasta ahora.
            detenida = True
            print("\n[COMMANDER] Campaña detenida por el usuario; se generará un reporte con los hallazgos hasta ahora.")
            event_bus.emitir(
                "campaign_stopped",
                "commander",
                {"reportes_acumulados": len(reportes), "fases_completadas": completadas},
            )
            col = coleccion_activa()
            if col is not None and not col.motivo_termino:
                col.set_resultado("detenido_usuario", exito=False)

        print("\n" + "=" * 50)
        print("  REPORTE EJECUTIVO" + (" (PARCIAL — CAMPAÑA DETENIDA)" if detenida else " FINAL"))
        print("=" * 50)
        ruta = reportador.generar_reporte(reportes, target=target, mision=mision)
        print(f"Reporte guardado en: {ruta}")
        event_bus.emitir(
            "campaign_end",
            "commander",
            {
                "ruta_reporte": ruta,
                "fases_completadas": completadas,
                "total_reportes": len(reportes),
                "detenida": detenida,
            },
        )
        return ruta
    except BaseException as e:
        # Cualquier otro fallo (no la detención cooperativa): deja registro del
        # motivo en las métricas y propaga.
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
