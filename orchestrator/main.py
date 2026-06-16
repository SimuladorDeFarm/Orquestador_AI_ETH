"""Punto de entrada de la API REST de Dani-ETH.

Ejecutar desde el directorio orchestrator/:

    uvicorn main:app --reload

Documentación interactiva en http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI

from routes.campaign import router as campaign_router

app = FastAPI(title="Dani-ETH Orchestrator API")
app.include_router(campaign_router)


@app.get("/")
def root():
    return {"status": "ok", "service": "dani-eth-orchestrator"}
