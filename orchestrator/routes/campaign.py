"""Endpoints de control del orquestador (campaña de exploración).

Sesión única: por ahora no se usa id de campaña. El control multi-campaña
con identificadores se añadirá más adelante.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.campaign_manager import campaign_manager
from core.reports_handler import listar_reportes, obtener_reporte
from config import SESION_ID

router = APIRouter(prefix="/campaign", tags=["campaign"])


class IniciarCampaña(BaseModel):
    target: str = Field(..., description="IP o host objetivo (entorno autorizado)")
    sesion_id: int = Field(SESION_ID, description="ID de sesión del runner")


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


@router.post("/start")
def iniciar(payload: IniciarCampaña):
    """Inicia la exploración contra el objetivo indicado."""
    try:
        campaign_manager.iniciar(payload.target, payload.sesion_id)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return campaign_manager.estado_actual()


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
