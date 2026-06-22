"""Genera el reporte de métricas de una campaña.

Crea metrics/<YYYY-MM-DD_HH-MM-SS>/ con:
- los gráficos (PNG) generados con matplotlib, y
- reporte_metricas.md que los referencia con rutas relativas (misma carpeta),
  de modo que al abrir el .md las imágenes se ven embebidas.

El reporte se construye SOLO con datos disponibles: si una sección no tiene
datos (p. ej. ninguna tarea se ejecutó), se omite su gráfico y se indica en texto.
"""

import os
from collections import defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # backend sin display: solo guarda PNG
import matplotlib.pyplot as plt

from metricas.collector import MetricsCollector, USD_POR_1M_INPUT, USD_POR_1M_OUTPUT

METRICS_DIR = os.path.join(os.path.dirname(__file__), "..", "metrics")

# Paleta sobria y consistente entre gráficos.
_AZUL, _NARANJA, _VERDE, _ROJO, _GRIS = "#2c6fbb", "#e1812c", "#3a923a", "#c03d3d", "#9aa0a6"


# --- agregaciones -----------------------------------------------------------

def _agg_tokens_por_agente(col: MetricsCollector) -> dict:
    agg = defaultdict(lambda: {"prompt": 0, "completion": 0, "llamadas": 0})
    for c in col.llm_calls:
        a = agg[c["agente"]]
        a["prompt"] += c["prompt_tokens"]
        a["completion"] += c["completion_tokens"]
        a["llamadas"] += 1
    return dict(agg)


def _agg_tareas_por_herramienta(col: MetricsCollector) -> dict:
    agg = defaultdict(lambda: {"ok": 0, "fallo": 0, "latencias": []})
    for t in col.tareas_runner:
        a = agg[t["herramienta"]]
        if t.get("codigo_salida") == 0:
            a["ok"] += 1
        else:
            a["fallo"] += 1
        a["latencias"].append(t.get("latencia") or 0.0)
    return dict(agg)


def _matriz_acuerdo(col: MetricsCollector) -> dict:
    """Cruza la decisión de la IA (continuar/terminar) con la del Juez (aprueba/rechaza)."""
    m = {"ambos_terminar": 0, "ambos_seguir": 0, "ia_rinde_juez_insiste": 0, "juez_corta_ia_seguia": 0}
    for it in col.iteraciones.values():
        ia, juez = it.get("decision_ia"), it.get("decision_juez")
        if ia is None or juez is None:
            continue
        if juez == "aprueba" and ia == "terminar":
            m["ambos_terminar"] += 1
        elif juez == "rechaza" and ia == "continuar":
            m["ambos_seguir"] += 1
        elif juez == "rechaza" and ia == "terminar":
            m["ia_rinde_juez_insiste"] += 1
        elif juez == "aprueba" and ia == "continuar":
            m["juez_corta_ia_seguia"] += 1
    return m


# --- gráficos (devuelven el nombre de archivo o None si no hay datos) --------

def _guardar(fig, carpeta: str, nombre: str) -> str:
    ruta = os.path.join(carpeta, nombre)
    fig.tight_layout()
    fig.savefig(ruta, dpi=120)
    plt.close(fig)
    return nombre


def _grafico_summarizer(col: MetricsCollector, carpeta: str) -> str | None:
    if len(col.ingestas) < 1:
        return None
    x = [i["comando"] for i in col.ingestas]
    crudo = [i["crudo_acumulado"] for i in col.ingestas]
    memoria = [i["memoria_len"] for i in col.ingestas]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(x, crudo, marker="o", color=_ROJO, label="Crudo acumulado (sin memoria)")
    ax.plot(x, memoria, marker="o", color=_VERDE, label="Memoria estructurada (KB)")
    ax.fill_between(x, memoria, crudo, color=_VERDE, alpha=0.08)
    ax.set_title("Ahorro de contexto del Summarizer")
    ax.set_xlabel("Comando #")
    ax.set_ylabel("Tamaño (caracteres)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    return _guardar(fig, carpeta, "summarizer_ahorro.png")


def _grafico_tokens_agente(col: MetricsCollector, carpeta: str) -> str | None:
    agg = _agg_tokens_por_agente(col)
    if not agg:
        return None
    agentes = sorted(agg, key=lambda a: agg[a]["prompt"] + agg[a]["completion"], reverse=True)
    prompt = [agg[a]["prompt"] for a in agentes]
    completion = [agg[a]["completion"] for a in agentes]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(agentes, prompt, color=_AZUL, label="Prompt (entrada)")
    ax.bar(agentes, completion, bottom=prompt, color=_NARANJA, label="Completion (salida)")
    ax.set_title("Tokens consumidos por agente")
    ax.set_ylabel("Tokens")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    return _guardar(fig, carpeta, "tokens_por_agente.png")


def _grafico_tareas_iteracion(col: MetricsCollector, carpeta: str) -> str | None:
    its = sorted(n for n in col.iteraciones if col.iteraciones[n].get("tareas_generadas"))
    if not its:
        return None
    valores = [col.iteraciones[n]["tareas_generadas"] for n in its]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([str(n) for n in its], valores, color=_AZUL)
    ax.set_title("Tareas generadas por iteración")
    ax.set_xlabel("Iteración")
    ax.set_ylabel("N.º de tareas")
    ax.grid(True, axis="y", alpha=0.3)
    return _guardar(fig, carpeta, "tareas_por_iteracion.png")


def _grafico_tiempo(col: MetricsCollector, carpeta: str) -> str | None:
    t_llm = sum(c["latencia"] for c in col.llm_calls)
    t_runner = sum(t["latencia"] for t in col.tareas_runner)
    otro = max(col.duracion - t_llm - t_runner, 0)
    if t_llm + t_runner + otro <= 0:
        return None
    etiquetas, valores, colores = [], [], []
    for et, val, cl in [("LLM (pensar)", t_llm, _AZUL),
                        ("Runner (ejecutar)", t_runner, _NARANJA),
                        ("Otro/overhead", otro, _GRIS)]:
        if val > 0:
            etiquetas.append(f"{et}\n{val:.1f}s")
            valores.append(val)
            colores.append(cl)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.pie(valores, labels=etiquetas, colors=colores, autopct="%1.0f%%", startangle=90)
    ax.set_title("Distribución del tiempo de la campaña")
    return _guardar(fig, carpeta, "tiempo_distribucion.png")


def _grafico_exito_herramientas(col: MetricsCollector, carpeta: str) -> str | None:
    agg = _agg_tareas_por_herramienta(col)
    if not agg:
        return None
    herramientas = sorted(agg)
    ok = [agg[h]["ok"] for h in herramientas]
    fallo = [agg[h]["fallo"] for h in herramientas]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(herramientas, ok, color=_VERDE, label="Éxito (código 0)")
    ax.bar(herramientas, fallo, bottom=ok, color=_ROJO, label="Fallo")
    ax.set_title("Ejecución de herramientas: éxito vs fallo")
    ax.set_ylabel("N.º de ejecuciones")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    return _guardar(fig, carpeta, "exito_herramientas.png")


# --- markdown ---------------------------------------------------------------

def _fmt_seg(s: float) -> str:
    m, seg = divmod(int(s), 60)
    return f"{m}m {seg}s" if m else f"{seg}s"


def _img(nombre: str | None, alt: str) -> str:
    return f"![{alt}]({nombre})\n" if nombre else f"_Sin datos para «{alt}»._\n"


def _construir_md(col: MetricsCollector, g: dict) -> str:
    agg_tok = _agg_tokens_por_agente(col)
    total_prompt = sum(a["prompt"] for a in agg_tok.values())
    total_compl = sum(a["completion"] for a in agg_tok.values())
    total_tokens = total_prompt + total_compl
    total_llamadas = sum(a["llamadas"] for a in agg_tok.values())
    costo = (total_prompt / 1_000_000) * USD_POR_1M_INPUT + (total_compl / 1_000_000) * USD_POR_1M_OUTPUT

    t_llm = sum(c["latencia"] for c in col.llm_calls)
    t_runner = sum(t["latencia"] for t in col.tareas_runner)

    n_tareas = len(col.tareas_runner)
    n_ok = sum(1 for t in col.tareas_runner if t.get("codigo_salida") == 0)
    tasa_ok = (n_ok / n_tareas * 100) if n_tareas else 0.0

    n_iter = len([n for n in col.iteraciones if col.iteraciones[n].get("tareas_generadas")
                  or col.iteraciones[n].get("decision_juez")])
    m = _matriz_acuerdo(col)

    exito_txt = {True: "✅ Sí", False: "❌ No", None: "—"}[col.exito]
    mem = col.memoria_final or {}

    L = []
    L.append(f"# Reporte de métricas — {datetime.fromtimestamp(col.inicio):%Y-%m-%d %H:%M:%S}\n")
    L.append(f"- **Objetivo (target):** `{col.target}`")
    L.append(f"- **Misión:** {col.mision}")
    L.append(f"- **Duración total:** {_fmt_seg(col.duracion)}")
    L.append(f"- **Resultado:** {exito_txt}  ·  **Motivo de término:** `{col.motivo_termino or '—'}`")
    L.append("")

    L.append("## Resumen ejecutivo\n")
    L.append("| Métrica | Valor |")
    L.append("|---|---|")
    L.append(f"| Iteraciones | {n_iter} |")
    L.append(f"| Llamadas al LLM | {total_llamadas} |")
    L.append(f"| Tokens totales | {total_tokens:,} (entrada {total_prompt:,} / salida {total_compl:,}) |")
    L.append(f"| Costo estimado LLM | ~${costo:.4f} USD |")
    L.append(f"| Tareas ejecutadas (runner) | {n_tareas} |")
    L.append(f"| Tasa de éxito de ejecución | {tasa_ok:.0f}% ({n_ok}/{n_tareas}) |")
    L.append(f"| Tiempo en LLM / runner | {_fmt_seg(t_llm)} / {_fmt_seg(t_runner)} |")
    L.append("")
    L.append("> El costo es **estimado** con tarifas orientativas de DeepSeek "
             f"(${USD_POR_1M_INPUT}/1M entrada, ${USD_POR_1M_OUTPUT}/1M salida); ajústalas en `metricas/collector.py`.\n")

    L.append("## Tiempo\n")
    L.append(_img(g.get("tiempo"), "Distribución del tiempo"))

    L.append("## Consumo de LLM (tokens y costo)\n")
    L.append(_img(g.get("tokens"), "Tokens por agente"))
    if agg_tok:
        L.append("| Agente | Llamadas | Prompt | Completion | Total |")
        L.append("|---|---|---|---|---|")
        for a in sorted(agg_tok, key=lambda x: agg_tok[x]["prompt"] + agg_tok[x]["completion"], reverse=True):
            d = agg_tok[a]
            L.append(f"| {a} | {d['llamadas']} | {d['prompt']:,} | {d['completion']:,} | {d['prompt']+d['completion']:,} |")
        L.append("")

    L.append("## Eficiencia del Summarizer (memoria estructurada)\n")
    L.append(_img(g.get("summarizer"), "Ahorro de contexto del Summarizer"))
    if col.ingestas:
        ult = col.ingestas[-1]
        crudo, memo = ult["crudo_acumulado"], ult["memoria_len"]
        ratio = (crudo / memo) if memo else 0
        ahorro = (1 - memo / crudo) * 100 if crudo else 0
        L.append(f"Tras {len(col.ingestas)} comando(s): crudo acumulado **{crudo:,}** chars vs "
                 f"memoria **{memo:,}** chars → compresión **{ratio:.1f}×** "
                 f"(~{ahorro:.0f}% menos contexto que arrastrar todo el transcript).\n")

    L.append("## Iteraciones y decisiones (IA ↔ Juez)\n")
    L.append(_img(g.get("tareas"), "Tareas por iteración"))
    if col.iteraciones:
        L.append("| Iteración | Tareas | Decisión IA | Decisión Juez |")
        L.append("|---|---|---|---|")
        for n in sorted(col.iteraciones):
            it = col.iteraciones[n]
            L.append(f"| {n} | {it.get('tareas_generadas', 0)} | "
                     f"{it.get('decision_ia') or '—'} | {it.get('decision_juez') or '—'} |")
        L.append("")
    L.append("**Acuerdo IA ↔ Juez** (cuándo coinciden y cuándo no):\n")
    L.append("| Situación | Veces |")
    L.append("|---|---|")
    L.append(f"| Ambos coinciden en terminar | {m['ambos_terminar']} |")
    L.append(f"| Ambos coinciden en seguir | {m['ambos_seguir']} |")
    L.append(f"| IA quería terminar pero el Juez insistió | {m['ia_rinde_juez_insiste']} |")
    L.append(f"| IA quería seguir pero el Juez aprobó (cortó) | {m['juez_corta_ia_seguia']} |")
    L.append("")

    L.append("## Ejecución de herramientas\n")
    L.append(_img(g.get("exito"), "Éxito vs fallo por herramienta"))
    agg_h = _agg_tareas_por_herramienta(col)
    if agg_h:
        L.append("| Herramienta | Ejecuciones | Éxito | Fallo | Latencia media |")
        L.append("|---|---|---|---|---|")
        for h in sorted(agg_h):
            d = agg_h[h]
            tot = d["ok"] + d["fallo"]
            lat = sum(d["latencias"]) / len(d["latencias"]) if d["latencias"] else 0
            L.append(f"| {h} | {tot} | {d['ok']} | {d['fallo']} | {lat:.1f}s |")
        L.append("")

    L.append("## Cobertura final (KB del Explorador)\n")
    L.append("| Categoría | Cantidad |")
    L.append("|---|---|")
    for campo in ["servicios", "rutas", "archivos", "flags", "hallazgos", "pendientes", "descartado"]:
        L.append(f"| {campo} | {len(mem.get(campo, []) or [])} |")
    L.append("")
    if mem.get("flags"):
        L.append("**Flags encontradas:** " + ", ".join(f"`{f}`" for f in mem["flags"]) + "\n")

    if col.errores:
        L.append("## Errores registrados\n")
        for e in col.errores:
            L.append(f"- **{e['origen']}**: {e['detalle']}")
        L.append("")

    return "\n".join(L)


# --- punto de entrada -------------------------------------------------------

def generar_reporte_metricas(col: MetricsCollector) -> str:
    """Crea metrics/<timestamp>/ con los gráficos y el reporte_metricas.md."""
    ts = datetime.fromtimestamp(col.inicio).strftime("%Y-%m-%d_%H-%M-%S")
    carpeta = os.path.join(METRICS_DIR, ts)
    os.makedirs(carpeta, exist_ok=True)

    graficos = {
        "tiempo": _grafico_tiempo(col, carpeta),
        "tokens": _grafico_tokens_agente(col, carpeta),
        "summarizer": _grafico_summarizer(col, carpeta),
        "tareas": _grafico_tareas_iteracion(col, carpeta),
        "exito": _grafico_exito_herramientas(col, carpeta),
    }

    md = _construir_md(col, graficos)
    ruta_md = os.path.join(carpeta, "reporte_metricas.md")
    with open(ruta_md, "w", encoding="utf-8") as f:
        f.write(md)
    return ruta_md
