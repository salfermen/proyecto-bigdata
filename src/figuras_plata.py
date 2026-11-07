"""Figuras exploratorias sobre la capa Plata (escenario principal).

Uso:  python src/figuras_plata.py   ->  reportes/figuras/*.png
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from config import DIR_PLATA, DIR_REPORTES, ESCENARIO_PRINCIPAL  # noqa: E402

AZUL, NARANJA = "#2a78d6", "#eb6834"          # slots categóricos 1 y 2 (validados CVD)
TINTA, TINTA_2, TENUE = "#0b0b0b", "#52514e", "#898781"
REJILLA, EJE = "#e1e0d9", "#c3c2b7"
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 9,
    "text.color": TINTA, "axes.labelcolor": TINTA_2, "xtick.color": TENUE, "ytick.color": TENUE,
    "axes.edgecolor": EJE, "axes.linewidth": 0.8, "figure.facecolor": "white", "axes.facecolor": "white",
})
miles = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", "."))


def estilo(ax, titulo):
    ax.set_title(titulo, loc="left", fontsize=9.5, fontweight="semibold", color=TINTA, pad=6)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.grid(axis="y", color=REJILLA, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.yaxis.set_major_formatter(miles)


def cargar():
    c = pd.read_parquet(DIR_PLATA / "cuentas.parquet")
    t = pd.read_parquet(DIR_PLATA / "transacciones.parquet")
    c = c[c.escenario == ESCENARIO_PRINCIPAL]
    t = t[t.escenario == ESCENARIO_PRINCIPAL].copy()
    fraude = set(c.loc[c.es_fraude == 1, "cuenta_id"])
    t["entre_fraude"] = t.cuenta_origen.isin(fraude) & t.cuenta_destino.isin(fraude)
    return c, t


def fig_montos(t, salida):
    bordes = np.arange(0, 610, 10)
    fig, axes = plt.subplots(2, 1, figsize=(6.2, 3.9), sharex=True, gridspec_kw={"hspace": 0.55})
    grupos = [(t[~t.entre_fraude], AZUL, "Resto de transacciones"),
              (t[t.entre_fraude], NARANJA, "Transacciones entre cuentas fraudulentas")]
    for ax, (df, color, nombre) in zip(axes, grupos):
        ax.hist(df.monto, bins=bordes, color=color, rwidth=0.82)
        estilo(ax, f"{nombre}  (n = {len(df):,})".replace(",", "."))
        ax.axvline(100, color=TINTA_2, linewidth=0.9)
        ax.set_ylabel("Transacciones")
    minimo = t.loc[~t.entre_fraude, "monto"].min()
    axes[0].text(94, axes[0].get_ylim()[1] * 0.68, f"monto mínimo\n= {minimo:.2f}".replace(".", ","),
                 color=TINTA_2, fontsize=8, ha="right", va="center")
    axes[1].set_xlabel("Monto por transacción (unidades del simulador)")
    axes[1].set_xlim(0, 600)
    fig.savefig(salida, dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_volumen(t, salida):
    diario = t.groupby("fecha").agg(total=("tx_id", "size"), fraude=("entre_fraude", "sum"))
    diario.index = pd.to_datetime(diario.index)
    fig, axes = plt.subplots(2, 1, figsize=(6.2, 3.6), sharex=True, gridspec_kw={"hspace": 0.55})
    for ax, col, color, nombre in ((axes[0], "total", AZUL, "Todas las transacciones por día"),
                                   (axes[1], "fraude", NARANJA, "Transacciones entre cuentas fraudulentas por día")):
        ax.plot(diario.index, diario[col], color=color, linewidth=1.6, solid_capstyle="round")
        ax.fill_between(diario.index, diario[col], color=color, alpha=0.10, linewidth=0)
        ax.set_ylim(bottom=0)
        estilo(ax, nombre)
    axes[1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[1].xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"{MESES[mdates.num2date(v).month - 1]} {mdates.num2date(v).year}"))
    axes[1].set_xlim(diario.index.min(), diario.index.max())
    fig.savefig(salida, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    destino = DIR_REPORTES / "figuras"
    destino.mkdir(parents=True, exist_ok=True)
    _, t = cargar()
    fig_montos(t, destino / "fig1_distribucion_montos.png")
    fig_volumen(t, destino / "fig2_volumen_diario.png")
    print(f"[figuras] -> {destino}")


if __name__ == "__main__":
    main()
