# -*- coding: utf-8 -*-
#
# Adaptado de python-bcb (https://github.com/wilsonfreitas/python-bcb)
# Copyright (c) 2021 Wilson Freitas — Licenca MIT
# Adaptacoes (c) 2026 Edilson Aguiais — Licenca MIT
#
"""Excecoes do pacote sgs-peritos."""

from __future__ import annotations


class BCBError(Exception):
    """Excecao base para todos os erros do pacote."""


class BCBAPIError(BCBError):
    """Erro de HTTP ou de nivel de API do Banco Central."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class BCBRateLimitError(BCBAPIError):
    """Disparada quando a API retorna 429 (limite de requisicoes excedido)."""


class SGSError(BCBError):
    """Disparada para erros especificos do SGS."""
