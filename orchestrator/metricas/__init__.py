"""Paquete de métricas del orquestador.

Recolecta métricas de una campaña (tokens, tiempos, decisiones, cobertura...) y
genera un reporte en markdown con gráficos en metrics/<timestamp>/.

Uso típico (lo hace el Commander automáticamente):

    from metricas import iniciar_coleccion, finalizar_coleccion
    from metricas.reporte import generar_reporte_metricas

    iniciar_coleccion(target, mision)
    ...  # corre la campaña
    col = finalizar_coleccion()
    generar_reporte_metricas(col)
"""

from metricas.collector import (
    MetricsCollector,
    iniciar_coleccion,
    finalizar_coleccion,
    coleccion_activa,
)

__all__ = [
    "MetricsCollector",
    "iniciar_coleccion",
    "finalizar_coleccion",
    "coleccion_activa",
]
