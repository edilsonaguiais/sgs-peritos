# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Edilson Aguiais — Licenca MIT
#
"""Exemplos minimos de uso do sgs-peritos."""

import sgs_peritos as sgs
from sgs_peritos import catalogo


def main() -> None:
    print("=== Catalogo de codigos para peritos ===")
    catalogo.listar()

    print("\n=== Meta Selic - ultimos 6 pontos ===")
    print(sgs.get(catalogo.codigo("selic_meta"), last=6))

    print("\n=== IPCA mensal + INPC mensal (2025) ===")
    print(
        sgs.get(
            {"IPCA": catalogo.codigo("ipca_mensal"), "INPC": catalogo.codigo("inpc_mensal")},
            start="2025-01-01",
            end="2025-12-31",
        )
    )

    print("\n=== Juros financiamento veiculo PF (% a.m.) - ultimos 12 meses ===")
    print(sgs.get(catalogo.codigo("veiculo_pf_mensal"), last=12))


if __name__ == "__main__":
    main()
