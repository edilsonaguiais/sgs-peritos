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


class SGSTransientError(SGSError):
    """Erro transitorio do SGS — vale a pena tentar de novo.

    Cobre situacoes em que o servico do BCB responde, mas de forma
    invalida/instavel, e nao a ausencia definitiva da serie:

    * pagina de WAF/proxy ("Requisicao invalida! / Bad request") devolvida
      com status HTTP 200 e corpo HTML/XML em vez do JSON esperado;
    * corpo nao-JSON ou truncado;
    * erro interno do BCB (``5xx``), inclusive quando devolvido com
      ``status 200`` mas com ``{"erro": {"statusCode": 5xx}}`` no corpo.

    O cliente HTTP faz retry com backoff exponencial nesses casos.
    """
