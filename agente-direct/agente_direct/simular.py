"""Converse com o agente no terminal, sem Instagram, para testar tom e BANT.

    python -m agente_direct.simular
"""

from __future__ import annotations

import asyncio
import json

from datetime import date

from .cerebro import Cerebro, links_permitidos, montar_sistema
from .config import Config


async def main() -> None:
    cfg = Config.do_ambiente()
    cerebro = Cerebro(montar_sistema(cfg.pasta_conhecimento), cfg.modelo, cfg.esforco,
                      links=links_permitidos(cfg.pasta_conhecimento))
    historico: list[dict] = []
    print("Você é o lead. Escreva como se fosse no direct (Ctrl+C para sair).\n")
    while True:
        try:
            fala = input("lead> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not fala:
            continue
        if historico and historico[-1]["role"] == "user":
            historico[-1]["content"] += "\n" + fala
        else:
            historico.append({"role": "user", "content": fala})
        decisao = await cerebro.decidir(historico, f"data de hoje: {date.today():%d/%m/%Y}")
        for texto in decisao.mensagens:
            print(f"agente> {texto}")
        if decisao.mensagens:
            historico.append({"role": "assistant", "content": "\n".join(decisao.mensagens)})
        print("   ficha:", json.dumps(decisao.ficha, ensure_ascii=False))
        if decisao.transferir:
            print(f"   >>> ESPERANDO O EDILSON RESPONDER À MÃO: {decisao.motivo}")


if __name__ == "__main__":
    asyncio.run(main())
