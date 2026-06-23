"""Acceso a los reportes ejecutivos generados en orchestrator/reports/.

Cada reporte es un par de archivos hermanos:
- reporte_<timestamp>.md   : el documento ejecutivo.
- reporte_<timestamp>.json : metadatos (target, mision, iteraciones).

Los reportes generados antes de añadir el metadata NO tienen .json; para esos
se hace fallback derivando lo posible del nombre del archivo, de modo que la
lista nunca se rompa por reportes históricos.
"""

import json
import os
import re

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")

# reporte_2026-06-22_00-16-44.md  ->  id = 2026-06-22_00-16-44
_PATRON_NOMBRE = re.compile(r"^reporte_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.md$")


def _id_legible(report_id: str) -> str:
    """'2026-06-22_00-16-44' -> '2026-06-22 00:16:44' (best-effort)."""
    try:
        fecha, hora = report_id.split("_")
        return f"{fecha} {hora.replace('-', ':')}"
    except ValueError:
        return report_id


def _metadata_de(report_id: str, nombre_md: str) -> dict:
    """Lee el .json hermano; si no existe, hace fallback desde el nombre."""
    ruta_json = os.path.join(REPORTS_DIR, f"reporte_{report_id}.json")
    base = {
        "id": report_id,
        "fecha": _id_legible(report_id),
        "target": "desconocido",
        "mision": "",
        "iteraciones": None,
        "archivo_md": nombre_md,
    }
    if os.path.isfile(ruta_json):
        try:
            with open(ruta_json, encoding="utf-8") as f:
                datos = json.load(f)
            base.update({
                "target": datos.get("target", base["target"]),
                "mision": datos.get("mision", base["mision"]),
                "iteraciones": datos.get("iteraciones", base["iteraciones"]),
                "archivo_md": datos.get("archivo_md", nombre_md),
            })
        except (json.JSONDecodeError, OSError):
            pass  # JSON corrupto: nos quedamos con el fallback.
    return base


def listar_reportes() -> list[dict]:
    """Devuelve los metadatos de todos los reportes, más nuevos primero."""
    if not os.path.isdir(REPORTS_DIR):
        return []
    reportes = []
    for nombre in os.listdir(REPORTS_DIR):
        m = _PATRON_NOMBRE.match(nombre)
        if m:
            reportes.append(_metadata_de(m.group(1), nombre))
    # El id es el timestamp en formato ordenable lexicográficamente.
    reportes.sort(key=lambda r: r["id"], reverse=True)
    return reportes


def obtener_reporte(report_id: str) -> dict | None:
    """Devuelve un reporte completo (metadatos + contenido .md) o None si no existe."""
    nombre_md = f"reporte_{report_id}.md"
    ruta_md = os.path.join(REPORTS_DIR, nombre_md)
    # Evita path traversal: solo aceptamos ids con el formato esperado.
    if not _PATRON_NOMBRE.match(nombre_md) or not os.path.isfile(ruta_md):
        return None
    meta = _metadata_de(report_id, nombre_md)
    with open(ruta_md, encoding="utf-8") as f:
        meta["contenido"] = f.read()
    return meta
