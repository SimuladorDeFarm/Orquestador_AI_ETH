"""Punto de entrada de la API REST de Dani-ETH.

Ejecutar desde el directorio orchestrator/:

    uvicorn main:app --reload

Documentación interactiva en http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from routes.campaign import router as campaign_router

app = FastAPI(title="Dani-ETH Orchestrator API")

# CORS: permite que el frontend (otro origen) consuma la API desde el navegador.
# allow_headers=["*"] es imprescindible para aceptar la cabecera 'Authorization'
# del token JWT de Firebase en el preflight. No se usa allow_origins=["*"] junto
# a allow_credentials=True (combinación que el navegador rechaza).
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(campaign_router)


@app.get("/")
def root():
    return {"status": "ok", "service": "dani-eth-orchestrator"}
