# sgs-peritos

**Acesso simples às séries temporais do SGS (Sistema Gerenciador de Séries
Temporais) do Banco Central do Brasil — pensado para peritos.**

O SGS é a base pública do Bacen com milhares de séries econômicas: Selic, CDI,
IPCA, INPC, IGP-M, dólar, taxas de juros por modalidade de crédito,
inadimplência por estado/região e muito mais. Este pacote dá acesso direto a
essas séries em Python, devolvendo um `DataFrame` do pandas pronto para uso em
laudos, planilhas e cálculos periciais.

> ⚠️ **Aviso pericial:** os valores vêm direto da API pública do BCB. Antes de
> citar qualquer série em laudo, confirme o **nome oficial** e a metodologia da
> série no localizador do próprio Banco Central (link no final). Códigos de
> crédito por modalidade mudam conforme a base metodológica.

---

## Créditos e licença

Este projeto é **MIT**. O núcleo de acesso ao SGS é **derivado do excelente
projeto [`python-bcb`](https://github.com/wilsonfreitas/python-bcb) de Wilson
Freitas** (© 2021, MIT). Esta distribuição preserva o aviso de copyright
original, conforme exige a licença MIT, e adiciona:

- empacotamento independente focado em SGS;
- um **catálogo curado de códigos úteis em perícia** (validados ao vivo);
- um **script pronto** que gera CSV de taxas de financiamento de veículo.

Curadoria e adaptações: **Edilson Aguiais** (© 2026). Veja o arquivo
[`LICENSE`](LICENSE).

---

## Instalação

```bash
git clone https://github.com/edilsonaguiais/sgs-peritos.git
cd sgs-peritos
pip install .
```

Dependências: `pandas`, `httpx`, `tenacity`.

---

## Uso rápido

```python
import sgs_peritos as sgs

# Uma série, últimos 12 pontos (Meta Selic = código 432)
sgs.get(432, last=12)

# Várias séries nomeadas, a partir de uma data
sgs.get({"selic": 432, "ipca": 433, "igpm": 189}, start="2024-01-01")

# Período fechado
sgs.get(20749, start="2020-01-01", end="2024-12-31")  # juros veículo PF (% a.a.)

# JSON bruto da API, sem pandas
sgs.get(432, last=1, output="text")
```

### Catálogo de códigos para peritos

```python
from sgs_peritos import catalogo

catalogo.listar()                     # imprime todos os códigos curados
catalogo.codigo("veiculo_pf_mensal")  # -> 25471
sgs.get(catalogo.codigo("ipca_12m"), last=1)
```

Códigos incluídos (validados ao vivo contra a API do BCB):

| Chave | Código | Série | Unidade |
|---|---|---|---|
| `selic_meta` | 432 | Meta Selic (Copom) | % a.a. |
| `selic_diaria` | 11 | Selic diária | % a.d. |
| `selic_mes_anualizada` | 4189 | Selic acum. mês anualizada (base 252) | % a.a. |
| `selic_acum_mes` | 4390 | Selic acumulada no mês | % a.m. |
| `cdi_diaria` | 12 | CDI diária | % a.d. |
| `cdi_acum_mes` | 4391 | CDI acumulada no mês | % a.m. |
| `ipca_mensal` | 433 | IPCA — variação mensal | % |
| `ipca_12m` | 13522 | IPCA — acumulado 12 meses | % |
| `inpc_mensal` | 188 | INPC — variação mensal | % |
| `igpm_mensal` | 189 | IGP-M — variação mensal | % |
| `dolar_ptax_compra` | 1 | Dólar PTAX — compra | R$ |
| `veiculo_pf_anual` | 20749 | Juros aquisição de veículos — PF | % a.a. |
| `veiculo_pf_mensal` | 25471 | Juros aquisição de veículos — PF | % a.m. |
| `veiculo_pj_anual` | 20728 | Juros aquisição de veículos — PJ | % a.a. |
| `veiculo_pj_mensal` | 25447 | Juros aquisição de veículos — PJ | % a.m. |

### Inadimplência por estado/região

```python
from sgs_peritos.regional_economy import get_non_performing_loans
from sgs_peritos import BRAZILIAN_REGIONS

get_non_performing_loans(["GO"], mode="PF", last=12)        # Goiás, pessoa física
get_non_performing_loans(BRAZILIAN_REGIONS["NE"], mode="PJ", last=6)
```

### Script pronto: taxas de financiamento de veículo

Gera um CSV (UTF-8 com BOM, separador `;`, decimal com vírgula — pronto para
Excel) com a série histórica das taxas PF e PJ, anual e mensal:

```bash
python exemplos/taxas_veiculo.py "C:\\saida"
```

---

## Como localizar o código de qualquer outra série

1. Localizador oficial do Bacen:
   <https://www3.bcb.gov.br/sgspub/localizarseries/localizarSeries.do>
2. Checar um código pela API:
   `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{CODIGO}/dados/ultimos/1?formato=json`

---

## Isenção de responsabilidade

Software fornecido "como está", sem garantias. Os dados são de
responsabilidade do Banco Central do Brasil. A conferência da série correta
para cada finalidade pericial é responsabilidade do usuário.
