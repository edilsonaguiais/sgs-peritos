# -*- coding: utf-8 -*-
#
# Adaptado de python-bcb (https://github.com/wilsonfreitas/python-bcb)
# Copyright (c) 2021 Wilson Freitas — Licenca MIT
# Adaptacoes (c) 2026 Edilson Aguiais — Licenca MIT
#
"""Cliente HTTP compartilhado (sincrono e assincrono) com retry."""

from __future__ import annotations

from typing import Callable, TypeVar

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

# Timeout padrao de todas as requisicoes HTTP (segundos)
DEFAULT_TIMEOUT = 30.0

# Cliente HTTP sincrono compartilhado
_CLIENT = httpx.Client(
    timeout=DEFAULT_TIMEOUT,
    follow_redirects=True,
)

# Cliente HTTP assincrono compartilhado
_ASYNC_CLIENT = httpx.AsyncClient(
    timeout=DEFAULT_TIMEOUT,
    follow_redirects=True,
)


# Decorador de retry para falhas transitorias
# (erros de conexao, timeouts, HTTP 5xx, etc.)
_retry_decorator = retry(
    stop=stop_after_attempt(4),  # 1 inicial + 3 retries = 4 tentativas
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)


def get_client() -> httpx.Client:
    """Retorna o cliente HTTP sincrono compartilhado."""
    return _CLIENT


def get_async_client() -> httpx.AsyncClient:
    """Retorna o cliente HTTP assincrono compartilhado."""
    return _ASYNC_CLIENT


def close_async_client() -> None:
    """Fecha o cliente assincrono compartilhado.

    Chame em aplicacoes de longa duracao antes do shutdown para encerrar
    corretamente as conexoes HTTP.
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_ASYNC_CLIENT.aclose())
        else:
            loop.run_until_complete(_ASYNC_CLIENT.aclose())
    except RuntimeError:
        asyncio.run(_ASYNC_CLIENT.aclose())


T = TypeVar("T")


def with_retry(func: Callable[..., T]) -> Callable[..., T]:
    """Adiciona retry automatico com backoff exponencial a qualquer funcao."""
    return _retry_decorator(func)
