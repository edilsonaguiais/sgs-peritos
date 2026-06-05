# -*- coding: utf-8 -*-
#
# Catalogo de codigos SGS uteis em pericia
# Copyright (c) 2026 Edilson Aguiais — Licenca MIT
#
"""
Catalogo curado de codigos do SGS (Banco Central) uteis em pericia.

Cada codigo aqui foi VALIDADO ao vivo contra a API publica do BCB, conferindo
a magnitude do ultimo valor e, nos pares anual/mensal, a equivalencia
``(1 + mensal/100) ** 12 - 1 ≈ anual``.

ATENCAO PERICIAL: o BCB publica MUITAS series de credito por modalidade e os
codigos mudam conforme a base metodologica. Antes de usar qualquer codigo em
laudo, confirme o nome oficial da serie no localizador do proprio BCB:

    https://www3.bcb.gov.br/sgspub/localizarseries/localizarSeries.do

Para descobrir/checar um codigo via API:

    https://api.bcb.gov.br/dados/serie/bcdata.sgs.{CODIGO}/dados/ultimos/1?formato=json
"""

from __future__ import annotations

from typing import Dict, NamedTuple


class SerieInfo(NamedTuple):
    codigo: int
    descricao: str
    unidade: str
    frequencia: str  # diaria | mensal | anual


# --- Indices e taxas macroeconomicas (validados por magnitude) ---------------
INDICES_MACRO: Dict[str, SerieInfo] = {
    "selic_meta": SerieInfo(432, "Meta Selic definida pelo Copom", "% a.a.", "diaria"),
    "selic_diaria": SerieInfo(11, "Taxa Selic diaria", "% a.d.", "diaria"),
    "selic_mes_anualizada": SerieInfo(
        4189, "Taxa Selic acumulada no mes anualizada (base 252)", "% a.a.", "mensal"
    ),
    "selic_acum_mes": SerieInfo(4390, "Taxa Selic acumulada no mes", "% a.m.", "mensal"),
    "cdi_diaria": SerieInfo(12, "Taxa CDI diaria", "% a.d.", "diaria"),
    "cdi_acum_mes": SerieInfo(4391, "Taxa CDI acumulada no mes", "% a.m.", "mensal"),
    "ipca_mensal": SerieInfo(433, "IPCA - variacao mensal", "%", "mensal"),
    "ipca_12m": SerieInfo(13522, "IPCA - acumulado em 12 meses", "%", "mensal"),
    "inpc_mensal": SerieInfo(188, "INPC - variacao mensal", "%", "mensal"),
    "igpm_mensal": SerieInfo(189, "IGP-M - variacao mensal", "%", "mensal"),
    "dolar_ptax_compra": SerieInfo(1, "Dolar dos EUA (PTAX) - compra", "R$", "diaria"),
}

# --- Taxas de juros - Financiamento de veiculos (validados por equivalencia)--
# (1 + mensal/100) ** 12 - 1 ≈ anual, conferido em abr/2026:
#   PF: 1,99% a.m. -> 26,6% a.a. (serie reporta 26,64)
#   PJ: 1,42% a.m. -> 18,4% a.a. (serie reporta 18,50)
JUROS_FINANCIAMENTO_VEICULOS: Dict[str, SerieInfo] = {
    "veiculo_pf_anual": SerieInfo(
        20749, "Juros - Aquisicao de veiculos - Pessoa Fisica", "% a.a.", "mensal"
    ),
    "veiculo_pf_mensal": SerieInfo(
        25471, "Juros - Aquisicao de veiculos - Pessoa Fisica", "% a.m.", "mensal"
    ),
    "veiculo_pj_anual": SerieInfo(
        20728, "Juros - Aquisicao de veiculos - Pessoa Juridica", "% a.a.", "mensal"
    ),
    "veiculo_pj_mensal": SerieInfo(
        25447, "Juros - Aquisicao de veiculos - Pessoa Juridica", "% a.m.", "mensal"
    ),
}

# Catalogo completo (uniao de todos os grupos)
CATALOGO: Dict[str, SerieInfo] = {
    **INDICES_MACRO,
    **JUROS_FINANCIAMENTO_VEICULOS,
}


def codigo(chave: str) -> int:
    """Retorna o codigo SGS a partir da chave do catalogo.

    >>> from sgs_peritos import catalogo
    >>> catalogo.codigo("selic_meta")
    432
    """
    return CATALOGO[chave].codigo


def listar() -> None:
    """Imprime o catalogo formatado (codigo, descricao, unidade)."""
    largura = max(len(k) for k in CATALOGO)
    for chave, info in CATALOGO.items():
        print(
            f"{chave:<{largura}}  {info.codigo:>6}  "
            f"{info.descricao} ({info.unidade}, {info.frequencia})"
        )
