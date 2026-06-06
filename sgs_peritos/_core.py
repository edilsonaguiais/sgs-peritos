# -*- coding: utf-8 -*-
#
# Adaptado de python-bcb (https://github.com/wilsonfreitas/python-bcb)
# Copyright (c) 2021 Wilson Freitas — Licenca MIT
# Adaptacoes (c) 2026 Edilson Aguiais — Licenca MIT
#
"""
Sistema Gerenciador de Series Temporais (SGS)
=============================================

O modulo obtem os dados do webservice do Banco Central (interface JSON do
servico BCData/SGS):
https://www3.bcb.gov.br/sgspub/localizarseries/localizarSeries.do?method=prepararTelaLocalizarSeries
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from io import StringIO
from typing import (
    Dict,
    Generator,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
    TypeAlias,
    Union,
    overload,
)

import pandas as pd

from .http import _CLIENT, _ASYNC_CLIENT, with_retry
from .exceptions import BCBRateLimitError, SGSError, SGSTransientError
from .utils import Date, DateInput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SGSCode:
    """Codigo de serie SGS com nome legivel opcional."""

    value: int
    name: str

    @classmethod
    def from_code(cls, code: int | str) -> "SGSCode":
        code_int = int(code)
        return cls(value=code_int, name=str(code_int))

    @classmethod
    def from_named(cls, code: int | str, name: str) -> "SGSCode":
        return cls(value=int(code), name=name)

    def __repr__(self) -> str:
        return f"{self.value} - {self.name}"


SGSCodeInput: TypeAlias = Union[
    int,
    str,
    Tuple[str, Union[int, str]],
    List[Union[int, str, Tuple[str, Union[int, str]]]],
    Mapping[str, Union[int, str]],
]


def _validate_sgs_code(code: SGSCode) -> None:
    if code.value <= 0:
        raise ValueError(f"Codigo SGS deve ser inteiro positivo, recebido {code.value}")


def _codes(codes: SGSCodeInput) -> Generator[SGSCode, None, None]:
    if isinstance(codes, int) or isinstance(codes, str):
        code_obj = SGSCode.from_code(codes)
        _validate_sgs_code(code_obj)
        yield code_obj
    elif isinstance(codes, tuple):
        code_obj = SGSCode.from_named(codes[1], codes[0])
        _validate_sgs_code(code_obj)
        yield code_obj
    elif isinstance(codes, list):
        for cd in codes:
            if isinstance(cd, tuple):
                code_obj = SGSCode.from_named(cd[1], cd[0])
            else:
                code_obj = SGSCode.from_code(cd)
            _validate_sgs_code(code_obj)
            yield code_obj
    elif isinstance(codes, Mapping):
        for name, code in codes.items():
            code_obj = SGSCode.from_named(code, name)
            _validate_sgs_code(code_obj)
            yield code_obj


def _get_url_and_payload(
    code: int,
    start_date: Optional[DateInput],
    end_date: Optional[DateInput],
    last: int,
) -> Tuple[str, Dict[str, str]]:
    payload: Dict[str, str] = {"formato": "json"}
    if last == 0:
        if start_date is not None or end_date is not None:
            payload["dataInicial"] = Date(start_date).date.strftime("%d/%m/%Y")  # type: ignore[arg-type]
            end_date = end_date if end_date else "today"
            payload["dataFinal"] = Date(end_date).date.strftime("%d/%m/%Y")
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
    else:
        url = (
            f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados/ultimos/{last}"
        )

    return url, payload


def _format_df(df: pd.DataFrame, code: SGSCode, freq: Optional[str]) -> pd.DataFrame:
    cns = {"data": "Date", "valor": code.name, "datafim": "enddate"}
    df = df.rename(columns=cns)
    if "Date" in df:
        df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y")
    if "enddate" in df:
        df["enddate"] = pd.to_datetime(df["enddate"], format="%d/%m/%Y")
    df = df.set_index("Date")
    if freq:
        df.index = df.index.to_period(freq)
    return df


@overload
def get(
    codes: SGSCodeInput,
    start: Optional[DateInput] = ...,
    end: Optional[DateInput] = ...,
    last: int = ...,
    multi: bool = ...,
    freq: Optional[str] = ...,
    output: Literal["dataframe"] = ...,
) -> Union[pd.DataFrame, List[pd.DataFrame]]: ...


@overload
def get(
    codes: SGSCodeInput,
    start: Optional[DateInput] = ...,
    end: Optional[DateInput] = ...,
    last: int = ...,
    multi: bool = ...,
    freq: Optional[str] = ...,
    output: Literal["text"] = ...,
) -> Union[str, Dict[int, str]]: ...


def get(
    codes: SGSCodeInput,
    start: Optional[DateInput] = None,
    end: Optional[DateInput] = None,
    last: int = 0,
    multi: bool = True,
    freq: Optional[str] = None,
    output: str = "dataframe",
) -> Union[pd.DataFrame, List[pd.DataFrame], str, Dict[int, str]]:
    """
    Retorna um DataFrame pandas com series temporais obtidas do SGS.

    Parameters
    ----------
    codes : {int, List[int], List[str], Dict[str:int]}
        Pode ser:

        * ``int`` : codigo da serie temporal
        * ``list`` / ``tuple`` : varios codigos
        * ``list`` / ``tuple`` : pares ``('nome', codigo)``
        * ``dict`` : ``{'nome': codigo}``

        Com codigos numericos e interessante usar nomes para nomear as colunas.
    start : str, int, date, datetime, Timestamp
        Data de inicio da serie.
    end : str, int, date, datetime, Timestamp
        Data final da serie.
    last : int
        Retorna os ultimos ``last`` elementos. Se > 0, ignora ``start``/``end``.
    multi : bool
        Quando varias series, retorna multivariada (True) ou lista (False).
    freq : str
        Frequencia a ser usada na serie temporal.
    output : str
        ``'dataframe'`` (padrao) ou ``'text'`` (JSON bruto da API).

    Returns
    -------
    DataFrame, list, str ou dict conforme os parametros.
    """
    if output == "text":
        results: Dict[int, str] = {}
        for code in _codes(codes):
            results[code.value] = get_json(code.value, start, end, last)
        values = list(results.values())
        if len(values) == 1:
            return values[0]
        return results

    dfs = []
    for code in _codes(codes):
        text = get_json(code.value, start, end, last)
        df = pd.read_json(StringIO(text))
        df = _format_df(df, code, freq)
        dfs.append(df)
    if len(dfs) == 1:
        return dfs[0]
    else:
        if multi:
            return pd.concat(dfs, axis=1)
        else:
            return dfs


def _parse_sgs_response(code: int, status_code: int, text: str) -> str:
    """Valida a resposta do SGS e devolve o JSON bruto (texto).

    Trata os casos em que o BCB "responde" mas de forma invalida — em
    especial a pagina de WAF/proxy devolvida com ``status 200`` e corpo
    HTML, e o erro interno (``5xx``) que tambem vem com ``status 200`` e
    ``{"erro": {"statusCode": 5xx}}`` no corpo. Esses casos viram
    :class:`SGSTransientError` para que o cliente faca retry.

    Raises
    ------
    BCBRateLimitError
        Status 429 (limite de requisicoes).
    SGSTransientError
        Falha transitoria (WAF, 5xx, corpo nao-JSON) — vale tentar de novo.
    SGSError
        Erro definitivo do SGS (ex.: serie inexistente).
    """
    if status_code == 429:
        raise BCBRateLimitError(
            "Limite de requisicoes da API do BCB excedido. Tente novamente mais tarde.",
            status_code=429,
        )

    if status_code >= 500:
        raise SGSTransientError(
            f"BCB indisponivel (HTTP {status_code}) ao baixar codigo = {code}."
        )

    stripped = text.lstrip()

    # Pagina de WAF/proxy: corpo HTML/XML ("Requisicao invalida!") com
    # status 200. Nao e JSON e tende a se resolver sozinha — retry.
    if stripped.startswith("<"):
        raise SGSTransientError(
            f"BCB rejeitou a requisicao (pagina de WAF/HTML em vez de JSON) "
            f"para o codigo = {code}. Servico instavel; tente de novo."
        )

    try:
        res_json = json.loads(text)
    except json.JSONDecodeError:
        if status_code != 200:
            raise SGSError(f"Erro ao baixar: codigo = {code} (HTTP {status_code})")
        raise SGSTransientError(
            f"Resposta nao-JSON do BCB para o codigo = {code}. "
            f"Servico instavel; tente de novo."
        )

    # O BCB devolve erros como objeto JSON ({"erro": ...} / {"error": ...}),
    # as vezes ate com status 200. Um 5xx embutido e transitorio.
    if isinstance(res_json, dict):
        err = res_json.get("erro") or res_json.get("error")
        if err is not None:
            detail = err.get("detail", err) if isinstance(err, dict) else err
            inner_status = err.get("statusCode") if isinstance(err, dict) else None
            if (inner_status and int(inner_status) >= 500) or status_code >= 500:
                raise SGSTransientError(
                    f"Erro interno do BCB ao baixar codigo = {code}: {detail}"
                )
            raise SGSError(f"Erro do BCB (codigo = {code}): {detail}")

    if status_code != 200:
        raise SGSError(f"Erro ao baixar: codigo = {code} (HTTP {status_code})")

    return str(text)


@with_retry
def get_json(
    code: int,
    start: Optional[DateInput] = None,
    end: Optional[DateInput] = None,
    last: int = 0,
) -> str:
    """Retorna o JSON bruto de uma serie temporal do SGS.

    Faz retry automatico com backoff em falhas transitorias do BCB
    (timeouts, 5xx, pagina de WAF, rate limit).
    """
    url, payload = _get_url_and_payload(code, start, end, last)
    logger.debug(f"Baixando serie SGS code={code} de {url.split('/dados')[0]}")
    res = _CLIENT.get(url, params=payload)
    logger.debug(f"Resposta SGS: status={res.status_code}, length={len(res.text)}")
    return _parse_sgs_response(code, res.status_code, res.text)


@with_retry
async def async_get_json(
    code: int,
    start: Optional[DateInput] = None,
    end: Optional[DateInput] = None,
    last: int = 0,
) -> str:
    """Versao assincrona de :func:`get_json` (com o mesmo retry)."""
    url, payload = _get_url_and_payload(code, start, end, last)
    logger.debug(f"Baixando serie SGS (async) code={code} de {url.split('/dados')[0]}")
    res = await _ASYNC_CLIENT.get(url, params=payload)
    logger.debug(f"Resposta SGS (async): status={res.status_code}, length={len(res.text)}")
    return _parse_sgs_response(code, res.status_code, res.text)


async def async_get(
    codes: SGSCodeInput,
    start: Optional[DateInput] = None,
    end: Optional[DateInput] = None,
    last: int = 0,
    multi: bool = True,
    freq: Optional[str] = None,
    output: str = "dataframe",
) -> Union[pd.DataFrame, List[pd.DataFrame], str, Dict[int, str]]:
    """Versao assincrona de :func:`get` (usa ``asyncio.gather``)."""
    code_list = list(_codes(codes))

    texts = await asyncio.gather(
        *[async_get_json(c.value, start, end, last) for c in code_list]
    )

    if output == "text":
        results: Dict[int, str] = {c.value: t for c, t in zip(code_list, texts)}
        values = list(results.values())
        if len(values) == 1:
            return values[0]
        return results

    dfs = [
        _format_df(pd.read_json(StringIO(t)), c, freq) for c, t in zip(code_list, texts)
    ]
    if len(dfs) == 1:
        return dfs[0]
    else:
        if multi:
            return pd.concat(dfs, axis=1)
        else:
            return dfs
