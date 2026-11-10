from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ENTRADA = Path("data/treated/indicadores_economicos.csv")
SAIDA = Path("images/indicadores_bacen.png")


def serie(df, nome, coluna):
    return (
        df[df["NmIndicador"] == nome]
        .dropna(subset=[coluna])
        .sort_values("DtReferencia")
    )


def main():
    df = pd.read_csv(ENTRADA, parse_dates=["DtReferencia"])

    ultimo_ano = df["DtReferencia"].max() - pd.DateOffset(years=1)
    dolar = serie(df, "Dólar", "ValorMoeda")
    euro = serie(df, "Euro", "ValorMoeda")
    dolar_ano = dolar[dolar["DtReferencia"] >= ultimo_ano]
    euro_ano = euro[euro["DtReferencia"] >= ultimo_ano]

    selic = serie(df, "Selic", "ValorPercentual")
    focus = serie(df, "Selic Esperada Próximo Ano", "ValorPercentual")
    juro = serie(df, "Juro Real", "ValorPercentual")

    spread = pd.merge(
        dolar_ano[["DtReferencia", "ValorMoeda"]],
        euro_ano[["DtReferencia", "ValorMoeda"]],
        on="DtReferencia",
        suffixes=("_usd", "_eur"),
    )
    spread["Spread"] = spread["ValorMoeda_eur"] - spread["ValorMoeda_usd"]

    fig, eixos = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("Indicadores Econômicos - BACEN", fontsize=16, fontweight="bold")

    ax = eixos[0, 0]
    ax.plot(dolar_ano["DtReferencia"], dolar_ano["ValorMoeda"], label="Dólar (PTAX)")
    ax.plot(euro_ano["DtReferencia"], euro_ano["ValorMoeda"], label="Euro (PTAX)")
    ax.set_title("Câmbio nos últimos 12 meses (R$)")
    ax.legend()

    ax = eixos[0, 1]
    ax.plot(selic["DtReferencia"], selic["ValorPercentual"] * 100, label="Selic")
    ax.plot(focus["DtReferencia"], focus["ValorPercentual"] * 100, label="Selic esperada próx. ano")
    ax.set_title("Selic e expectativa de mercado (%)")
    ax.legend()

    ax = eixos[1, 0]
    ax.plot(juro["DtReferencia"], juro["ValorPercentual"] * 100, color="tab:orange")
    ax.set_title("Juro real acumulado em 12 meses (%)")

    ax = eixos[1, 1]
    ax.plot(spread["DtReferencia"], spread["Spread"], color="tab:gray")
    ax.set_title("Spread EUR - USD nos últimos 12 meses (R$)")

    for ax in eixos.flat:
        ax.grid(alpha=0.3)
        ax.tick_params(axis="x", rotation=30)

    fig.text(0.01, 0.01, "Fonte: APIs públicas do Banco Central do Brasil (PTAX, SGS e Focus)", fontsize=9)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(SAIDA, dpi=150)
    print(f"Painel gravado em {SAIDA}")


if __name__ == "__main__":
    main()