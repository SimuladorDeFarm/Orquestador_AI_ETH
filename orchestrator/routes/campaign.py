"""Endpoints de control del orquestador (campaña de exploración).

Sesión única: por ahora no se usa id de campaña. El control multi-campaña
con identificadores se añadirá más adelante.
"""

import ipaddress
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.campaign_manager import campaign_manager
from core.reports_handler import listar_reportes, obtener_reporte
from core import event_bus
from config import SESION_ID, construir_mision

router = APIRouter(prefix="/campaign", tags=["campaign"])

# Valores válidos de los enums (se validan a mano para devolver el cuerpo de
# error exacto del contrato; Pydantic generaría su propio formato 422).
MODOS_VALIDOS = [
    "solo_reconocimiento",
    "reconocimiento_vulnerabilidades",
    "reconocimiento_explotacion",
]
PROFUNDIDADES_VALIDAS = ["superficial", "estandar", "exhaustivo"]

FLAG_FORMAT_DEFAULT = "FLAG{...}"

# hostname: labels alfanuméricos (con guiones internos) separados por puntos.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


def _target_valido(valor: str) -> bool:
    """True si `valor` es una IP (v4/v6) o un hostname con forma válida."""
    try:
        ipaddress.ip_address(valor)
        return True
    except ValueError:
        pass
    return bool(_HOSTNAME_RE.match(valor))


class Restricciones(BaseModel):
    no_pivoting: bool = True
    modo_ctf: bool = False
    flag_format: str = FLAG_FORMAT_DEFAULT
    solo_reportar_criticos: bool = False
    stealth: bool = False


class IniciarCampaña(BaseModel):
    # target se acepta opcional para validarlo a mano y emitir el cuerpo de
    # error 'campo_requerido' del contrato (ausente / null / vacío → mismo error).
    target: str | None = Field(None, description="IP o host objetivo (entorno autorizado)")
    sesion_id: int = Field(SESION_ID, description="ID de sesión del runner")
    modo: str = Field("solo_reconocimiento", description="Modo de ataque")
    profundidad: str = Field("estandar", description="Nivel de profundidad")
    restricciones: Restricciones = Field(default_factory=Restricciones)


class ReporteResumen(BaseModel):
    id: str = Field(..., description="Identificador del reporte (timestamp)")
    fecha: str = Field(..., description="Fecha legible 'YYYY-MM-DD HH:MM:SS'")
    target: str = Field(..., description="Objetivo evaluado")
    mision: str = Field("", description="Misión de la campaña")
    iteraciones: int | None = Field(None, description="Nº de iteraciones (null si es un reporte antiguo sin metadata)")


class ListaReportes(BaseModel):
    reportes: list[ReporteResumen]


class ReporteCompleto(ReporteResumen):
    archivo_md: str = Field(..., description="Nombre del archivo .md")
    contenido: str = Field(..., description="Contenido completo del reporte en markdown")


class EventoCampaña(BaseModel):
    id: int = Field(..., description="Índice incremental del evento (sirve de cursor)")
    timestamp: str = Field(..., description="Marca de tiempo ISO 8601 (UTC)")
    tipo: str = Field(..., description="Tipo de evento (discrimina el componente visual)")
    agente: str = Field(..., description="Agente que emitió el evento")
    fase: str | None = Field(None, description="Fase activa de la campaña, si aplica")
    iteracion: int | None = Field(None, description="Iteración Explorador↔Juez en curso, si aplica")
    datos: dict = Field(default_factory=dict, description="Payload específico del tipo de evento")


class LogsCampaña(BaseModel):
    eventos: list[EventoCampaña] = Field(..., description="Eventos nuevos desde el cursor pedido")
    total: int = Field(..., description="Total de eventos acumulados (próximo cursor a pedir)")


@router.post("/start")
def iniciar(payload: IniciarCampaña):
    """Inicia la exploración contra el objetivo indicado."""
    target = (payload.target or "").strip()

    if not target:
        return JSONResponse(
            status_code=422,
            content={
                "error": "campo_requerido",
                "campo": "target",
                "mensaje": "El campo 'target' es obligatorio. Debes indicar la IP o el hostname del objetivo.",
            },
        )

    if not _target_valido(target):
        return JSONResponse(
            status_code=422,
            content={
                "error": "formato_invalido",
                "campo": "target",
                "mensaje": f"El valor '{target}' no es una IP ni un hostname válido.",
                "ejemplos_validos": ["10.10.10.5", "scanme.nmap.org", "192.168.1.100"],
            },
        )

    if payload.modo not in MODOS_VALIDOS:
        return JSONResponse(
            status_code=422,
            content={
                "error": "valor_invalido",
                "campo": "modo",
                "valor_recibido": payload.modo,
                "valores_validos": MODOS_VALIDOS,
                "mensaje": "Modo de ataque no reconocido. Se usará 'solo_reconocimiento' si omites este campo.",
            },
        )

    if payload.profundidad not in PROFUNDIDADES_VALIDAS:
        return JSONResponse(
            status_code=422,
            content={
                "error": "valor_invalido",
                "campo": "profundidad",
                "valor_recibido": payload.profundidad,
                "valores_validos": PROFUNDIDADES_VALIDAS,
                "mensaje": "Nivel de profundidad no reconocido. Se usará 'estandar' si omites este campo.",
            },
        )

    advertencias: list[dict] = []
    if payload.restricciones.modo_ctf and not payload.restricciones.flag_format.strip():
        payload.restricciones.flag_format = FLAG_FORMAT_DEFAULT
        advertencias.append(
            {
                "campo": "flag_format",
                "mensaje": "No se proporcionó formato de flag. Se usará el valor por defecto: FLAG{...}",
            }
        )

    restricciones = payload.restricciones.model_dump()
    mision = construir_mision(target, payload.modo, payload.profundidad, restricciones)

    try:
        campaign_manager.iniciar(
            target,
            payload.sesion_id,
            mision=mision,
            modo=payload.modo,
            profundidad=payload.profundidad,
            restricciones=restricciones,
        )
    except RuntimeError:
        estado = campaign_manager.estado_actual()
        return JSONResponse(
            status_code=409,
            content={
                "error": "campaña_en_curso",
                "mensaje": "Ya hay una campaña activa. Detenla antes de iniciar una nueva.",
                "estado_actual": {
                    "estado": estado["estado"],
                    "target": estado["target"],
                    "iteracion_actual": estado["iteracion_actual"],
                },
            },
        )

    respuesta = campaign_manager.estado_actual()
    respuesta["advertencias"] = advertencias
    return respuesta


@router.post("/pause")
def pausar():
    """Pausa la campaña en curso (toma efecto en el próximo checkpoint)."""
    try:
        campaign_manager.pausar()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return campaign_manager.estado_actual()


@router.post("/resume")
def reanudar():
    """Reanuda una campaña pausada."""
    try:
        campaign_manager.reanudar()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return campaign_manager.estado_actual()


@router.post("/stop")
def detener():
    """Detiene la campaña en curso (toma efecto en el próximo checkpoint)."""
    try:
        campaign_manager.detener()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return campaign_manager.estado_actual()


@router.get("/status")
def estado():
    """Devuelve el estado actual del orquestador."""
    return campaign_manager.estado_actual()


@router.get("/logs", response_model=LogsCampaña)
def logs(desde: int = 0):
    """Devuelve los eventos estructurados de la campaña desde el cursor `desde`.

    Pensado para polling incremental desde el frontend: guarda el `total`
    devuelto y pásalo como `desde` en la siguiente petición para recibir solo los
    eventos nuevos. El bus se vacía al iniciar cada campaña, así que tras un
    `start` el cursor vuelve a empezar en 0.
    """
    eventos = event_bus.obtener_desde(desde)
    return {"eventos": eventos, "total": event_bus.total()}


# --- Reportes ejecutivos ---------------------------------------------------
# La ruta exacta /reports debe declararse antes que /reports/{id}.

@router.get("/reports", response_model=ListaReportes)
def reportes():
    """Lista todos los reportes ejecutivos (más nuevos primero)."""
    return {"reportes": listar_reportes()}


@router.get("/reports/{id}", response_model=ReporteCompleto)
def reporte(id: str):
    """Devuelve el contenido completo de un reporte por su id (timestamp)."""
    datos = obtener_reporte(id)
    if datos is None:
        raise HTTPException(status_code=404, detail=f"Reporte '{id}' no encontrado")
    return datos
