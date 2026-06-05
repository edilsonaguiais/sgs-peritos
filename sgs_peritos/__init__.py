# -*- coding: utf-8 -*-
#
# sgs-peritos — acesso as series temporais do SGS (Banco Central) para peritos
#
# Nucleo derivado de python-bcb (https://github.com/wilsonfreitas/python-bcb)
# Copyright (c) 2021 Wilson Freitas — Licenca MIT
# Curadoria e adaptacoes (c) 2026 Edilson Aguiais — Licenca MIT
#
"""sgs-peritos: acesso simples ao Sistema Gerenciador de Series Temporais (SGS).

Exemplo rapido
--------------
>>> import sgs_peritos as sgs
>>> sgs.get(432, last=5)                  # Meta Selic, ultimos 5 pontos
>>> sgs.get({"selic": 432, "ipca": 433}, start="2024-01-01")
>>> from sgs_peritos import catalogo
>>> sgs.get(catalogo.codigo("veiculo_pf_mensal"), last=12)
"""

from __future__ import annotations

from ._core import (
    SGSCode,
    get,
    get_json,
    async_get,
    async_get_json,
)
from .exceptions import BCBError, BCBAPIError, BCBRateLimitError, SGSError
from .utils import BRAZILIAN_REGIONS, BRAZILIAN_STATES, Date
from . import catalogo
from . import regional_economy

__version__ = "1.0.0"

__all__ = [
    "SGSCode",
    "get",
    "get_json",
    "async_get",
    "async_get_json",
    "BCBError",
    "BCBAPIError",
    "BCBRateLimitError",
    "SGSError",
    "BRAZILIAN_REGIONS",
    "BRAZILIAN_STATES",
    "Date",
    "catalogo",
    "regional_economy",
    "__version__",
]
