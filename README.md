# Indicadores Econômicos do BACEN

Pipeline em Python que extrai indicadores econômicos das APIs públicas do Banco Central do Brasil e os organiza em duas camadas: **raw** (dados brutos) e **treated** (dados prontos para análise).

## Indicadores

| Indicador | Fonte | Descrição |
|---|---|---|
| Dólar (PTAX) | API PTAX | Cotação de venda diária |
| Euro (PTAX) | API PTAX | Cotação de venda diária |
| Selic | SGS (série 432) | Taxa básica de juros |
| Selic Mensal | SGS (série 4390) | Selic acumulada no mês |
| IPCA Mensal | SGS (série 433) | Inflação mensal |
| Selic Esperada Próximo Ano | API Focus | Mediana das expectativas de mercado |
| Juro Real | Calculado | Taxa real acumulada em 12 meses |

## Camadas do pipeline

**Raw:** consulta as APIs e padroniza os dados em um único formato, sem aplicar regras de negócio.

**Treated:** aplica as regras de tratamento:

- **Última cotação do dia** para Dólar e Euro.
- **Fechamento mensal**: último valor disponível de cada mês.
- **Oscilação diária e mensal**: variação percentual entre períodos.
- **Focus do próximo ano**: mantém apenas a expectativa para o ano seguinte ao da observação.
- **Juro real**: `((1 + Selic 12M) / (1 + IPCA 12M)) - 1`, com acumulado por capitalização composta.

## Estrutura do projeto

```
indicadores-bacen/
├── scripts/
│   └── indicadores_bacen.py
├── data/              # gerado pelo script (não versionado)
│   ├── raw/
│   └── treated/
├── images/
├── notebooks/
├── requirements.txt
└── README.md
```

## Como executar

1. Clone o repositório e entre na pasta:

```bash
git clone https://github.com/SEU_USUARIO/indicadores-bacen.git
cd indicadores-bacen
```

2. Crie e ative o ambiente virtual:

```bash
python -m venv .venv
.venv\Scripts\activate
```

No Linux ou macOS, use `source .venv/bin/activate`.

3. Instale as dependências:

```bash
pip install -r requirements.txt
```

4. Rode o pipeline a partir da raiz do projeto:

```bash
python scripts/indicadores_bacen.py
```

Ao final, os arquivos `data/raw/indicadores_economicos.csv` e `data/treated/indicadores_economicos.csv` estarão gerados.

## Tecnologias

- Python
- pandas e numpy
- requests (consumo de APIs REST)
- python-dateutil

## Observações

- Os dados são consultados diretamente das APIs públicas do BACEN a cada execução, então os valores refletem a data em que o script rodou.
- A camada treated segue a mesma lógica do notebook original, que rodava em Spark, adaptada aqui para pandas com saída em CSV.