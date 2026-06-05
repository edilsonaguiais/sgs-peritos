# sgs-peritos

**As taxas médias de juros do Banco Central, prontas para o perito — sem caçar
código de série no SGS.**

Ferramenta para **todo perito e assistente técnico** que precisa dos números
oficiais do Banco Central do Brasil — perito **bancário, trabalhista,
tributário, previdenciário, financeiro e contábil**, atuando como **perito
judicial ou assistente técnico**, além de **advogados e contadores**.

Serve a revisão de contratos, liquidação de sentença, superendividamento,
atualização de débitos e benefícios, correção monetária e perícia financeira em
geral — em qualquer área, é a mesma fonte oficial (BCB) que sustenta o cálculo.

Autor e curadoria: **Edilson Aguiais** — advogado (OAB-GO 59.889), contador
(CRC-GO 27.798), economista (CORECON-GO 2.337/D), professor e perito.

---

## Por que isso importa para o perito

Em perícia financeira — bancária, trabalhista, tributária, previdenciária —, o
erro mais comum, inclusive de quem tenta usar IA sem critério, é **trabalhar com
a taxa pactuada/divulgada pela própria instituição financeira**. Essa não é a
referência correta.

A referência é a **taxa MÉDIA de juros praticada pelo mercado**, por
modalidade, que o **Banco Central apura e divulga oficialmente** no SGS (Sistema
Gerenciador de Séries Temporais). É com ela que se demonstra abusividade,
recalcula o contrato e se sustenta o laudo.

O problema: essas séries estão espalhadas em **milhares de códigos numéricos** e
o perito perde tempo (e erra) tentando achar a série certa. Já vi código de
*aquisição de veículos* ser usado como se fosse *crédito pessoal* — o número sai
errado e o laudo cai.

**Este pacote resolve isso:** entrega as taxas médias de juros de **todas as
modalidades de crédito** (PF e PJ), com o nome correto e o código já validado
contra o catálogo oficial do BCB, acessíveis em uma linha de Python.

---

## O que tem aqui (catálogo curado e validado)

Todas as **modalidades de taxa média de juros** das operações de crédito com
recursos livres, em versão **anual (% a.a.)** e **mensal (% a.m.)**:

**Pessoa Física** — crédito pessoal não consignado · consignado (privado,
público, INSS, total) · aquisição de veículos · aquisição de outros bens ·
cheque especial · cartão de crédito (rotativo, parcelado, total) · arrendamento
mercantil · desconto de cheques · e o total PF.

**Pessoa Jurídica** — capital de giro (até/acima de 365 dias, rotativo, total) ·
desconto de duplicatas e recebíveis · conta garantida · cheque especial ·
antecipação de faturas de cartão · aquisição de veículos/bens · vendor · compror
· ACC · financiamento a importações/exportações · cartão de crédito · e o total
PJ.

> Cada código foi conferido contra o catálogo oficial de dados abertos do BCB
> (nome da série) **e** pela equivalência `(1 + mensal/100)¹² − 1 ≈ anual`.

Como apoio (correção monetária e referência), também inclui os índices macro:
**Selic, CDI, IPCA, INPC, IGP-M e dólar PTAX**.

> ⚠️ **Uso pericial:** os dados vêm direto da API pública do BCB. Confirme sempre
> a modalidade correta para o caso concreto — o pacote facilita o acesso, mas a
> escolha da série adequada é responsabilidade técnica do perito.

---

## Instalação

```bash
git clone https://github.com/edilsonaguiais/sgs-peritos.git
cd sgs-peritos
pip install .
```

Dependências: `pandas`, `httpx`, `tenacity`.

---

## Uso

```python
import sgs_peritos as sgs
from sgs_peritos import catalogo

# Taxa média de juros — crédito pessoal não consignado PF (% a.m.), últimos 12 meses
sgs.get(catalogo.codigo("pf_pessoal_nao_consignado_mensal"), last=12)

# Aquisição de veículos PF — anual e mensal juntos, a partir de uma data
sgs.get(
    {
        "veiculo_pf_aa": catalogo.codigo("pf_veiculos_anual"),
        "veiculo_pf_am": catalogo.codigo("pf_veiculos_mensal"),
    },
    start="2018-01-01",
)

# Achar todas as modalidades de consignado
catalogo.buscar("consignado")

# Listar um grupo inteiro
catalogo.listar("juros_pf")    # juros_pf | juros_pj | juros_geral | indices_macro
```

### Inadimplência por estado/região

```python
from sgs_peritos.regional_economy import get_non_performing_loans
from sgs_peritos import BRAZILIAN_REGIONS

get_non_performing_loans(["GO"], mode="PF", last=12)
get_non_performing_loans(BRAZILIAN_REGIONS["NE"], mode="PJ", last=6)
```

### Script pronto: CSV de taxas de financiamento de veículo

```bash
python exemplos/taxas_veiculo.py "C:\\saida"
```

Gera CSV (UTF-8 com BOM, `;`, decimal com vírgula — pronto para Excel) com a
série histórica completa PF/PJ, anual e mensal.

---

## Como localizar qualquer outra série do SGS

1. Localizador oficial do Bacen:
   <https://www3.bcb.gov.br/sgspub/>
2. Nome oficial de um código:
   `https://dadosabertos.bcb.gov.br/api/3/action/package_search?fq=codigo_sgs:{CODIGO}`
3. Último valor:
   `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{CODIGO}/dados/ultimos/1?formato=json`

---

## Créditos e licença

Projeto **MIT**.

O **motor de acesso ao SGS** (busca, download, parsing e montagem das séries em
`DataFrame`, com retry e suporte assíncrono) é **derivado do projeto
[`python-bcb`](https://github.com/wilsonfreitas/python-bcb), de Wilson Freitas**
(© 2021, MIT) — o crédito da engenharia base é dele, e esta distribuição
preserva o aviso de copyright original conforme exige a licença MIT.

Sobre esse motor, o **`sgs-peritos`** acrescenta a camada de produto voltada à
perícia: o pacote independente e focado em SGS, o **catálogo curado e validado
de todas as taxas médias de juros por modalidade** (o que o perito realmente
usa), a reorganização para uso forense e os exemplos prontos. Essa curadoria é
de **Edilson Aguiais** (© 2026).

Veja o arquivo [`LICENSE`](LICENSE) (atribuição dupla).

---

## Isenção de responsabilidade

Software fornecido "como está", sem garantias. Os dados são de responsabilidade
do Banco Central do Brasil. A conferência da série correta para cada finalidade
pericial é responsabilidade do usuário.
