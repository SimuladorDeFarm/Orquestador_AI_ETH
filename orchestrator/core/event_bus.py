"""Bus de eventos de la campaña: emisión estructurada para el frontend.

Los agentes siguen imprimiendo por consola con `print()` (útil para depurar en
desarrollo), pero además emiten aquí eventos tipados. El frontend los consume vía
`GET /campaign/logs?desde=N` con un cursor incremental, en vez de leer un "vuelco
de texto" de la terminal.

El bus es un singleton thread-safe: la campaña corre en un hilo de fondo (ver
`core/campaign_manager.py`) y el endpoint lee desde el hilo del servidor. Por eso
todo acceso a la lista de eventos va bajo lock.

Cada evento tiene la forma::

    {
        "id": 0,                       # índice incremental, sirve de cursor
        "timestamp": "...Z",           # ISO 8601 UTC
        "tipo": "tool_call",           # discrimina el componente visual
        "agente": "explorer",          # quién lo emitió
        "fase": "exploracion" | None,  # fase activa de la campaña
        "iteracion": 1 | None,         # iteración Explorador↔Juez en curso
        "datos": {...},                # payload específico del tipo
    }

`limpiar()` se llama al iniciar cada campaña para no mezclar runs.
"""

import threading
from datetime import datetime, timezone


class EventBus:
    """Acumulador thread-safe de eventos de la campaña activa."""

    def __init__(self):
        self._lock = threading.Lock()
        self._eventos: list[dict] = []

    def emitir(
        self,
        tipo: str,
        agente: str,
        datos: dict | None = None,
        fase: str | None = None,
        iteracion: int | None = None,
    ) -> None:
        """Registra un evento. El `id` se asigna por orden de llegada."""
        with self._lock:
            evento = {
                "id": len(self._eventos),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tipo": tipo,
                "agente": agente,
                "fase": fase,
                "iteracion": iteracion,
                "datos": datos or {},
            }
            self._eventos.append(evento)

    def obtener_desde(self, desde: int = 0) -> list[dict]:
        """Devuelve los eventos cuyo `id` es >= `desde` (cursor incremental)."""
        if desde < 0:
            desde = 0
        with self._lock:
            return self._eventos[desde:]

    def total(self) -> int:
        """Cantidad de eventos acumulados (próximo `id` a asignar)."""
        with self._lock:
            return len(self._eventos)

    def limpiar(self) -> None:
        """Vacía el bus. Se llama al iniciar una campaña nueva."""
        with self._lock:
            self._eventos.clear()


# Instancia única compartida por agentes y endpoints (sesión única por ahora,
# igual que campaign_manager).
_bus = EventBus()


def emitir(
    tipo: str,
    agente: str,
    datos: dict | None = None,
    fase: str | None = None,
    iteracion: int | None = None,
) -> None:
    """Atajo de módulo: emite un evento en el bus compartido."""
    _bus.emitir(tipo, agente, datos, fase, iteracion)


def obtener_desde(desde: int = 0) -> list[dict]:
    """Atajo de módulo: lee eventos desde un cursor."""
    return _bus.obtener_desde(desde)


def total() -> int:
    """Atajo de módulo: total de eventos acumulados."""
    return _bus.total()


def limpiar() -> None:
    """Atajo de módulo: limpia el bus compartido."""
    _bus.limpiar()
