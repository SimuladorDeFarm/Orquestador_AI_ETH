from fastapi import FastAPI
from pydantic import BaseModel
import threading
import time
import Orquestador

app = FastAPI()


class ScanRequest(BaseModel):
    target: str


class ConfirmRequest(BaseModel):
    aprobado: bool


# def test_start_scan(target: str):
#     global _test_cancelar, _test_en_curso
#     _test_cancelar = False
#     _test_en_curso = True
#     i = 1
#     while not _test_cancelar:
#         print(f"[TEST] scaneando {target} — ciclo {i}")
#         i += 1
#         time.sleep(1)
#     _test_en_curso = False
#
# def test_cancel_scan():
#     global _test_cancelar
#     _test_cancelar = True


@app.get("/")
def root():
    return {"mensaje": "Dani-ETH online"}


# ─── Scan ────────────────────────────────────────────────

@app.post("/scan/start")
def start_scan(body: ScanRequest):
    if Orquestador._en_curso:
        return {"status": "error", "mensaje": "Ya hay un scan en curso"}

    hilo = threading.Thread(target=Orquestador.iniciar_scan, args=(body.target,), daemon=True)
    hilo.start()

    return {"status": "started", "target": body.target}

    # if _test_en_curso:
    #     return {"status": "error", "mensaje": "Ya hay un scan en curso"}
    # hilo = threading.Thread(target=test_start_scan, args=(body.target,), daemon=True)
    # hilo.start()
    # return {"status": "started", "target": body.target}


@app.get("/scan/status")
def scan_status():
    return {"en_curso": Orquestador._en_curso}

    # return {"en_curso": _test_en_curso}


@app.post("/scan/cancel")
def cancel_scan():
    if not Orquestador._en_curso:
        return {"status": "error", "mensaje": "No hay scan en curso"}

    return Orquestador.cancelar_scan()

    # if not _test_en_curso:
    #     return {"status": "error", "mensaje": "No hay scan en curso"}
    # test_cancel_scan()
    # return {"status": "cancelling"}


# ─── Confirmaciones ──────────────────────────────────────

@app.get("/scan/pending")
def get_pending():
    return {
        "esperando": Orquestador._esperando_confirmacion,
        "accion": Orquestador._accion_pendiente if Orquestador._esperando_confirmacion else None,
    }


@app.post("/scan/confirm")
def confirm_action(body: ConfirmRequest):
    if not Orquestador._esperando_confirmacion:
        return {"status": "error", "mensaje": "No hay acción pendiente de confirmación"}

    Orquestador.responder_confirmacion(body.aprobado)

    return {
        "status": "ok",
        "aprobado": body.aprobado,
    }
