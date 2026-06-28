"""Gestión del ciclo de vida de una campaña de exploración.

Envuelve el orquestador (que es un proceso largo y bloqueante) en un hilo de
fondo controlable mediante start / pause / resume / stop, exponiendo su estado.

Por ahora se maneja UNA sola sesión a la vez (sin id de campaña). El soporte
multi-campaña con identificadores se implementará más adelante.
"""

import enum
import threading

from agents.commander import dirigir_campaña
from config import SESION_ID
from core import event_bus


class EstadoCampaña(str, enum.Enum):
    INACTIVO = "inactivo"
    EJECUTANDO = "ejecutando"
    PAUSADO = "pausado"
    DETENIDO = "detenido"
    FINALIZADO = "finalizado"
    ERROR = "error"


class CampañaDetenida(Exception):
    """Se lanza desde un checkpoint cuando se solicitó detener la campaña."""


def run_campaign(
    target: str,
    sesion_id: int = SESION_ID,
    control: "CampaignManager | None" = None,
    mision: str | None = None,
) -> str:
    """Ejecuta el flujo completo de la campaña para un objetivo.

    Delega la orquestación en el Commander (`dirigir_campaña`), que decide qué
    fases/agentes actúan. `control`, si se entrega, se propaga para permitir
    pausar o detener de forma cooperativa. `mision` es el prompt de misión ya
    construido; si es None, el Commander cae al fallback de `objetivo.txt`.
    Devuelve la ruta del reporte final.
    """
    return dirigir_campaña(target, sesion_id=sesion_id, control=control, mision=mision)


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
        self.mision: str | None = None
        self.modo: str | None = None
        self.profundidad: str | None = None
        self.restricciones: dict | None = None
        self.iteracion_actual = 0
        self.ruta_reporte: str | None = None
        self.error: str | None = None

    # --- API de control (llamada desde los endpoints) ---

    def iniciar(
        self,
        target: str,
        sesion_id: int = SESION_ID,
        mision: str | None = None,
        modo: str | None = None,
        profundidad: str | None = None,
        restricciones: dict | None = None,
    ) -> None:
        with self._lock:
            if self.estado in (EstadoCampaña.EJECUTANDO, EstadoCampaña.PAUSADO):
                raise RuntimeError("Ya hay una campaña en curso. Deténla antes de iniciar otra.")

            # Reset de estado y señales para una sesión limpia.
            # Vacía el bus de eventos para no mezclar logs del run anterior.
            event_bus.limpiar()
            self._evento_pausa.set()
            self._evento_stop.clear()
            self.estado = EstadoCampaña.EJECUTANDO
            self.target = target
            self.sesion_id = sesion_id
            self.mision = mision
            self.modo = modo
            self.profundidad = profundidad
            self.restricciones = restricciones
            self.iteracion_actual = 0
            self.ruta_reporte = None
            self.error = None

            self._hilo = threading.Thread(target=self._run, args=(target, sesion_id, mision), daemon=True)
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
                "modo": self.modo,
                "profundidad": self.profundidad,
                "restricciones": self.restricciones,
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

    def _run(self, target: str, sesion_id: int, mision: str | None = None) -> None:
        try:
            ruta = run_campaign(target, sesion_id=sesion_id, control=self, mision=mision)
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
