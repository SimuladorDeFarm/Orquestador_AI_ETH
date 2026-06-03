import os
from datetime import datetime
from agents.base_agent import BaseAgent

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


class ReporterAgent(BaseAgent):
    def generar_reporte(self, reportes: list[str]) -> str:
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
        ruta = os.path.join(REPORTS_DIR, f"reporte_{timestamp}.md")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(reporte)

        return ruta
