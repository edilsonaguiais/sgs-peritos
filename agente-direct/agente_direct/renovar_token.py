"""Renova o token de longa duração do Instagram (vale 60 dias).

    python -m agente_direct.renovar_token

Agende para rodar todo mês (cron) e atualize IG_ACCESS_TOKEN com o valor impresso.
"""

import asyncio

from .config import Config
from .instagram import ClienteInstagram


async def main() -> None:
    cfg = Config.do_ambiente()
    dados = await ClienteInstagram(cfg.ig_access_token, cfg.graph_versao).renovar_token()
    dias = int(dados.get("expires_in", 0)) // 86400
    print(f"Novo token (expira em ~{dias} dias):\n{dados['access_token']}")


if __name__ == "__main__":
    asyncio.run(main())
