import json
import os
from datetime import datetime
from agents.base_agent import BaseAgent

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


class ReporterAgent(BaseAgent):
    def generar_reporte(
        self,
        reportes: list[str],
        target: str = "desconocido",
        mision: str = "",
        iteraciones: int | None = None,
    ) -> str:
        """Sintetiza los reportes de iteración en el reporte ejecutivo final.

        Guarda dos archivos hermanos en reports/:
        - reporte_<timestamp>.md   : el reporte ejecutivo en markdown.
        - reporte_<timestamp>.json : metadatos para listar reportes rápido
          (sin leer el .md completo) desde la API.

        `iteraciones`, si no se entrega, se infiere del nº de reportes recibidos.
        """
        contenido = "\n\n---\n\n".join(reportes)
        reporte = self.preguntar(
            f"Se completaron todas las iteraciones de exploración. "
            f"A continuación están los reportes de cada iteración:\n\n{contenido}\n\n"
            f"Genera el reporte ejecutivo final en markdown siguiendo la estructura de tu system prompt. "
            f"Presta especial atención a: flags encontradas (no omitas ninguna), "
            f"rutas y archivos descubiertos (incluyendo los de ffuf), "
            f"y contenido de páginas web leídas con curl."
        )

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        nombre_md = f"reporte_{timestamp}.md"
        ruta = os.path.join(REPORTS_DIR, nombre_md)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(reporte)

        # Metadatos hermanos: best-effort, no deben tumbar la campaña si fallan.
        try:
            metadata = {
                "id": timestamp,
                "timestamp": timestamp,
                "target": target,
                "mision": mision,
                "iteraciones": iteraciones if iteraciones is not None else len(reportes),
                "archivo_md": nombre_md,
            }
            ruta_json = os.path.join(REPORTS_DIR, f"reporte_{timestamp}.json")
            with open(ruta_json, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:  # noqa: BLE001 - el .md ya se guardó; el metadata es secundario
            print(f"[REPORTER] No se pudo escribir el metadata JSON: {e}")

        return ruta
