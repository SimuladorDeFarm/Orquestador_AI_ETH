"""Endpoints de control del orquestador (campaña de exploración).

Sesión única: por ahora no se usa id de campaña. El control multi-campaña
con identificadores se añadirá más adelante.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.campaign_manager import campaign_manager
from config import SESION_ID

router = APIRouter(prefix="/campaign", tags=["campaign"])


class IniciarCampaña(BaseModel):
    target: str = Field(..., description="IP o host objetivo (entorno autorizado)")
    sesion_id: int = Field(SESION_ID, description="ID de sesión del runner")


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
