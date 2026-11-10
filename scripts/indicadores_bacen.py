"""
Indicadores econômicos do Banco Central do Brasil (BACEN).

Camadas:
- raw: extração das APIs PTAX, SGS e Focus, sem regras de negócio
- treated: fechamentos mensais, oscilações e juro real acumulado em 12 meses

Saída: arquivos CSV em data/raw e data/treated
"""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dateutil.relativedelta import relativedelta

ANOS_CONSULTA = 3
TIMEOUT = 120
HEADERS = {"Accept": "application/json"}

URL_PTAX = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"
URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
URL_FOCUS = (
    "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
    "ExpectativasMercadoAnuais"
)

SERIES_SGS = {432: "Selic", 4390: "Selic Mensal", 433: "IPCA Mensal"}

DATA_DIR = Path("data")

COLUNAS_TREATED = [
    "DtReferencia", "AnoReferencia", "NmIndicador", "TpIndicador",
    "ValorMoeda", "ValorPercentual", "FechamentoMoeda", "FechamentoPercentual",
    "OscDiaria", "OscMensal", "TpCotacao",
]


def get_json(url, params=None):
    response = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------- RAW

def extrair_ptax(data_inicial, data_final):
    base = {
        "@dataInicial": f"'{data_inicial:%m-%d-%Y}'",
        "@dataFinalCotacao": f"'{data_final:%m-%d-%Y}'",
        "$format": "json",
        "$select": "cotacaoVenda,dataHoraCotacao",
        "$top": "10000",
    }

    url_dolar = (
        f"{URL_PTAX}/CotacaoDolarPeriodo"
        "(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
    )
    url_euro = (
        f"{URL_PTAX}/CotacaoMoedaPeriodo"
        "(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
    )

    dolar = get_json(url_dolar, base).get("value", [])
    euro = get_json(url_euro, {**base, "@moeda": "'EUR'"}).get("value", [])

    frames = []
    for registros, nome in ((dolar, "Dólar"), (euro, "Euro")):
        df = pd.DataFrame(registros)
        frames.append(pd.DataFrame({
            "DtReferencia": pd.to_datetime(df["dataHoraCotacao"]),
            "NmIndicador": nome,
            "Valor": df["cotacaoVenda"].astype(float),
            "AnoReferencia": None,
        }))
    return pd.concat(frames, ignore_index=True)


def extrair_sgs(codigo, data_inicial, data_final):
    params = {
        "formato": "json",
        "dataInicial": f"{data_inicial:%d/%m/%Y}",
        "dataFinal": f"{data_final:%d/%m/%Y}",
    }
    df = pd.DataFrame(get_json(URL_SGS.format(codigo=codigo), params))
    return pd.DataFrame({
        "DtReferencia": pd.to_datetime(df["data"], format="%d/%m/%Y"),
        "NmIndicador": SERIES_SGS[codigo],
        "Valor": df["valor"].astype(float),
        "AnoReferencia": None,
    })


def extrair_focus(data_inicial):
    url = (
        "https://olinda.bcb.gov.br/olinda/servico/"
        "Expectativas/versao/v1/odata/"
        "ExpectativasMercadoAnuais"
        "?$filter=Indicador%20eq%20'Selic'"
        "%20and%20baseCalculo%20eq%200"
        f"%20and%20Data%20ge%20'{data_inicial:%Y-%m-%d}'"
        "&$select=Indicador,Data,DataReferencia,Mediana,baseCalculo"
        "&$orderby=Data%20asc,DataReferencia%20asc"
        "&$top=10000"
        "&$format=json"
    )
    df = pd.DataFrame(get_json(url)["value"])
    return pd.DataFrame({
        "DtReferencia": pd.to_datetime(df["Data"]),
        "NmIndicador": "Selic Focus",
        "Valor": df["Mediana"].astype(float),
        "AnoReferencia": df["DataReferencia"].astype(int),
    })


def extrair_raw(hoje=None):
    hoje = hoje or date.today()
    inicio_ptax = hoje.replace(year=hoje.year - ANOS_CONSULTA)
    inicio_sgs = hoje - relativedelta(years=ANOS_CONSULTA, months=12)

    partes = [extrair_ptax(inicio_ptax, hoje)]
    partes += [extrair_sgs(codigo, inicio_sgs, hoje) for codigo in SERIES_SGS]
    partes.append(extrair_focus(inicio_sgs))

    raw = pd.concat(partes, ignore_index=True)
    raw["DtLoad"] = pd.Timestamp.now()
    return raw[["DtReferencia", "NmIndicador", "Valor", "AnoReferencia", "DtLoad"]]


# ---------------------------------------------------------------- TREATED

def ultima_cotacao_do_dia(df):
    """Mantém apenas a última cotação registrada em cada dia."""
    df = df.sort_values("DtReferencia")
    df = df.assign(Dia=df["DtReferencia"].dt.normalize())
    return df.groupby("Dia").tail(1).drop(columns="Dia")


def marcar_fechamento_mensal(df):
    """Adiciona ValorFechamento (último valor do mês) e OscMensal (variação entre fechamentos)."""
    df = df.copy()
    mes = df["DtReferencia"].dt.to_period("M")
    ultima_data = df.groupby(mes)["DtReferencia"].transform("max")

    df["ValorFechamento"] = df["Valor"].where(df["DtReferencia"] == ultima_data)

    fechamentos = df.loc[df["ValorFechamento"].notna(), "ValorFechamento"]
    df["OscMensal"] = fechamentos.pct_change().reindex(df.index)
    return df


def tratar_moeda(raw, nome):
    df = ultima_cotacao_do_dia(raw[raw["NmIndicador"] == nome].copy())
    df = df.sort_values("DtReferencia").reset_index(drop=True)

    ultima_data = df["DtReferencia"].dt.normalize().max()
    df["TpCotacao"] = np.where(
        df["DtReferencia"].dt.normalize() == ultima_data, "Parcial", "Fechamento"
    )
    df["OscDiaria"] = df["Valor"].pct_change()
    return marcar_fechamento_mensal(df)


def tratar_selic(raw):
    df = raw[raw["NmIndicador"] == "Selic"].sort_values("DtReferencia")
    df = marcar_fechamento_mensal(df)
    df = df[df["ValorFechamento"].notna()]
    return pd.DataFrame({
        "DtReferencia": df["DtReferencia"].dt.normalize(),
        "AnoReferencia": None,
        "NmIndicador": "Selic",
        "TpIndicador": "Percentual",
        "ValorMoeda": np.nan,
        "ValorPercentual": df["Valor"] / 100,
        "FechamentoMoeda": np.nan,
        "FechamentoPercentual": df["Valor"] / 100,
        "OscDiaria": np.nan,
        "OscMensal": np.nan,
        "TpCotacao": "Fechamento",
    })


def tratar_focus(raw):
    df = raw[raw["NmIndicador"] == "Selic Focus"].copy()
    # Mantém apenas a expectativa para o ano seguinte ao ano da observação
    df = df[df["AnoReferencia"] == df["DtReferencia"].dt.year + 1]
    df = df.astype({"AnoReferencia": int})
    df = df.sort_values("DtReferencia").reset_index(drop=True)

    df["NmIndicador"] = "Selic Esperada Próximo Ano"
    df["OscDiaria"] = df["Valor"].pct_change()
    df = marcar_fechamento_mensal(df)

    return pd.DataFrame({
        "DtReferencia": df["DtReferencia"].dt.normalize(),
        "AnoReferencia": df["AnoReferencia"],
        "NmIndicador": df["NmIndicador"],
        "TpIndicador": "Percentual",
        "ValorMoeda": np.nan,
        "ValorPercentual": df["Valor"] / 100,
        "FechamentoMoeda": np.nan,
        "FechamentoPercentual": df["ValorFechamento"] / 100,
        "OscDiaria": df["OscDiaria"],
        "OscMensal": df["OscMensal"],
        "TpCotacao": "Fechamento",
    })


def tratar_juro_real(raw):
    selic = (
        raw[raw["NmIndicador"] == "Selic Mensal"][["DtReferencia", "Valor"]]
        .rename(columns={"Valor": "SelicMensal"})
    )
    ipca = (
        raw[raw["NmIndicador"] == "IPCA Mensal"][["DtReferencia", "Valor"]]
        .rename(columns={"Valor": "IpcaMensal"})
    )

    df = (
        selic.merge(ipca, on="DtReferencia", how="inner")
        .sort_values("DtReferencia")
        .reset_index(drop=True)
    )

    # Acumulado de 12 meses por capitalização composta
    selic_12m = np.exp(np.log1p(df["SelicMensal"] / 100).rolling(12).sum()) - 1
    ipca_12m = np.exp(np.log1p(df["IpcaMensal"] / 100).rolling(12).sum()) - 1
    df["JuroReal12M"] = (1 + selic_12m) / (1 + ipca_12m) - 1
    df = df.dropna(subset=["JuroReal12M"])

    return pd.DataFrame({
        "DtReferencia": df["DtReferencia"].dt.normalize(),
        "AnoReferencia": None,
        "NmIndicador": "Juro Real",
        "TpIndicador": "Percentual",
        "ValorMoeda": np.nan,
        "ValorPercentual": df["JuroReal12M"],
        "FechamentoMoeda": np.nan,
        "FechamentoPercentual": df["JuroReal12M"],
        "OscDiaria": np.nan,
        "OscMensal": np.nan,
        "TpCotacao": "Fechamento",
    })


def padronizar_moeda(df):
    return pd.DataFrame({
        "DtReferencia": df["DtReferencia"].dt.normalize(),
        "AnoReferencia": None,
        "NmIndicador": df["NmIndicador"],
        "TpIndicador": "Moeda",
        "ValorMoeda": df["Valor"],
        "ValorPercentual": np.nan,
        "FechamentoMoeda": df["ValorFechamento"],
        "FechamentoPercentual": np.nan,
        "OscDiaria": df["OscDiaria"],
        "OscMensal": df["OscMensal"],
        "TpCotacao": df["TpCotacao"],
    })


def montar_treated(raw):
    partes = [
        padronizar_moeda(tratar_moeda(raw, "Dólar")),
        padronizar_moeda(tratar_moeda(raw, "Euro")),
        tratar_selic(raw),
        tratar_focus(raw),
        tratar_juro_real(raw),
    ]
    treated = pd.concat(partes, ignore_index=True)[COLUNAS_TREATED]
    treated["MesAno"] = treated["DtReferencia"].dt.strftime("%m/%Y")
    treated["MesAnoOrdem"] = treated["DtReferencia"].dt.year * 100 + treated["DtReferencia"].dt.month
    treated["DtLoad"] = pd.Timestamp.now()
    return treated


# ---------------------------------------------------------------- GRAVAÇÃO

def salvar(df, caminho):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(caminho, index=False)
    print(f"{len(df)} registros gravados em {caminho}")


def main():
    raw = extrair_raw()
    salvar(raw, DATA_DIR / "raw" / "indicadores_economicos.csv")

    treated = montar_treated(raw)
    salvar(treated, DATA_DIR / "treated" / "indicadores_economicos.csv")


if __name__ == "__main__":
    main()