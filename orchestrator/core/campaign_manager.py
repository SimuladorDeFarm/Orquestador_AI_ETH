"""Gestión del ciclo de vida de una campaña de exploración.

Envuelve el orquestador (que es un proceso largo y bloqueante) en un hilo de
fondo controlable mediante start / pause / resume / stop, exponiendo su estado.

Por ahora se maneja UNA sola sesión a la vez (sin id de campaña). El soporte
multi-campaña con identificadores se implementará más adelante.
"""

import enum
import threading

from agents.explorer import crear_explorador, explorador, decidir_iteracion
from agents.judge import crear_juez
from agents.reporter import crear_reportador
from config import SESION_ID

# Límite de iteraciones del orquestador (idéntico al flujo original).
MAX_ITERACIONES = 6


class EstadoCampaña(str, enum.Enum):
    INACTIVO = "inactivo"
    EJECUTANDO = "ejecutando"
    PAUSADO = "pausado"
    DETENIDO = "detenido"
    FINALIZADO = "finalizado"
    ERROR = "error"


class CampañaDetenida(Exception):
    """Se lanza desde un checkpoint cuando se solicitó detener la campaña."""


def run_campaign(target: str, sesion_id: int = SESION_ID, control: "CampaignManager | None" = None) -> str:
    """Ejecuta el flujo completo de exploración para un objetivo.

    `control`, si se entrega, se consulta en checkpoints para permitir pausar
    o detener la ejecución de forma cooperativa. Devuelve la ruta del reporte
    ejecutivo final.
    """
    agente = crear_explorador(sesion_id=sesion_id, objetivo_target=target)
    juez = crear_juez()
    reportador = crear_reportador()

    reportes = []
    i = 0
    while not juez.aprueba and i < MAX_ITERACIONES:
        if control is not None:
            control.checkpoint()
            control.set_iteracion(i + 1)

        reporte = explorador(agente, target, primera_iteracion=(i == 0), control=control)
        reportes.append(reporte)
        i += 1

        decidir_iteracion(agente)

        print("\n" + "=" * 50)
        print("  JUEZ — EVALUACIÓN DEL REPORTE")
        print("=" * 50)
        juez.evaluar_reporte(reporte)

    print("\n" + "=" * 50)
    print("  REPORTE EJECUTIVO FINAL")
    print("=" * 50)
    ruta = reportador.generar_reporte(reportes)
    print(f"Reporte guardado en: {ruta}")
    return ruta


class CampaignManager:
    """Orquestador controlable: corre `run_campaign` en un hilo de fondo."""

    def __init__(self):
        self._lock = threading.Lock()
        self._hilo: threading.Thread | None = None
        # _evento_pausa "set" = libre para avanzar; "clear" = pausado.
        self._evento_pausa = threading.Event()
        self._evento_pausa.set()
        self._evento_stop = threading.Event()

        self.estado = EstadoCampaña.INACTIVO
        self.target: str | None = None
        self.sesion_id: int = SESION_ID
        self.iteracion_actual = 0
        self.ruta_reporte: str | None = None
        self.error: str | None = None

    # --- API de control (llamada desde los endpoints) ---

    def iniciar(self, target: str, sesion_id: int = SESION_ID) -> None:
        with self._lock:
            if self.estado in (EstadoCampaña.EJECUTANDO, EstadoCampaña.PAUSADO):
                raise RuntimeError("Ya hay una campaña en curso. Deténla antes de iniciar otra.")

            # Reset de estado y señales para una sesión limpia.
            self._evento_pausa.set()
            self._evento_stop.clear()
            self.estado = EstadoCampaña.EJECUTANDO
            self.target = target
            self.sesion_id = sesion_id
            self.iteracion_actual = 0
            self.ruta_reporte = None
            self.error = None

            self._hilo = threading.Thread(target=self._run, args=(target, sesion_id), daemon=True)
            self._hilo.start()

    def pausar(self) -> None:
        with self._lock:
            if self.estado != EstadoCampaña.EJECUTANDO:
                raise RuntimeError("No hay una campaña en ejecución para pausar.")
            self._evento_pausa.clear()
            self.estado = EstadoCampaña.PAUSADO

    def reanudar(self) -> None:
        with self._lock:
            if self.estado != EstadoCampaña.PAUSADO:
                raise RuntimeError("No hay una campaña pausada para reanudar.")
            self._evento_pausa.set()
            self.estado = EstadoCampaña.EJECUTANDO

    def detener(self) -> None:
        with self._lock:
            if self.estado not in (EstadoCampaña.EJECUTANDO, EstadoCampaña.PAUSADO):
                raise RuntimeError("No hay una campaña activa para detener.")
            self._evento_stop.set()
            # Si estaba pausada, la despertamos para que llegue al checkpoint y termine.
            self._evento_pausa.set()
            self.estado = EstadoCampaña.DETENIDO

    def estado_actual(self) -> dict:
        with self._lock:
            return {
                "estado": self.estado.value,
                "target": self.target,
                "sesion_id": self.sesion_id,
                "iteracion_actual": self.iteracion_actual,
                "ruta_reporte": self.ruta_reporte,
                "error": self.error,
            }

    # --- Cooperación con el hilo de trabajo ---

    def checkpoint(self) -> None:
        """Llamado desde el flujo de exploración. Bloquea si está pausado y
        lanza CampañaDetenida si se solicitó detener."""
        if self._evento_stop.is_set():
            raise CampañaDetenida()
        self._evento_pausa.wait()  # bloquea mientras esté pausado
        if self._evento_stop.is_set():
            raise CampañaDetenida()

    def set_iteracion(self, n: int) -> None:
        with self._lock:
            self.iteracion_actual = n

    # --- Hilo de trabajo ---

    def _run(self, target: str, sesion_id: int) -> None:
        try:
            ruta = run_campaign(target, sesion_id=sesion_id, control=self)
            with self._lock:
                self.ruta_reporte = ruta
                # Si se solicitó detener justo al final (sin checkpoint pendiente
                # que lo honre), el stop debe prevalecer sobre el fin natural.
                self.estado = (
                    EstadoCampaña.DETENIDO
                    if self._evento_stop.is_set()
                    else EstadoCampaña.FINALIZADO
                )
        except CampañaDetenida:
            with self._lock:
                self.estado = EstadoCampaña.DETENIDO
        except Exception as e:  # noqa: BLE001 - se reporta vía estado/error
            with self._lock:
                self.error = str(e)
                self.estado = EstadoCampaña.ERROR


# Instancia única compartida por la API (sesión única por ahora).
campaign_manager = CampaignManager()
