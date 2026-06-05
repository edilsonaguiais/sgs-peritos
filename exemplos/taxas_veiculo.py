# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Edilson Aguiais — Licenca MIT
#
"""
Taxas de juros - Financiamento de veiculos (PF e PJ) -> CSV
===========================================================

Baixa a serie historica completa das taxas medias mensais do Banco Central
(SGS) para financiamento de veiculos PF e PJ e gera um CSV pronto para Excel
(UTF-8 com BOM, separador ';', decimal com virgula).

Codigos SGS (validados ao vivo contra a API do BCB):
  20749 = Taxa MEDIA ANUAL  (% a.a.) - PF - Aquisicao de veiculos
  25471 = Taxa MEDIA MENSAL (% a.m.) - PF - Aquisicao de veiculos
  20728 = Taxa MEDIA ANUAL  (% a.a.) - PJ - Aquisicao de veiculos
  25447 = Taxa MEDIA MENSAL (% a.m.) - PJ - Aquisicao de veiculos

Coerencia conferida: (1 + mensal/100) ** 12 - 1 ≈ anual.

Uso:
  python taxas_veiculo.py [diretorio_saida]
"""

import argparse
import csv
import datetime as dt
import os

import sgs_peritos as sgs
from sgs_peritos import catalogo


def fmt_br(num: float, casas: int = 4) -> str:
    return f"{num:.{casas}f}".replace(".", ",")


def main() -> None:
    parser = argparse.ArgumentParser(description="Taxas Bacen - veiculos PF/PJ")
    parser.add_argument("outdir", nargs="?", default=".", help="Diretorio de saida")
    parser.add_argument("--nome-csv", default=None, help="Nome do CSV")
    args = parser.parse_args()

    codigos = {
        "PF_anual": catalogo.codigo("veiculo_pf_anual"),
        "PF_mensal": catalogo.codigo("veiculo_pf_mensal"),
        "PJ_anual": catalogo.codigo("veiculo_pj_anual"),
        "PJ_mensal": catalogo.codigo("veiculo_pj_mensal"),
    }

    print("[SGS] Baixando series de financiamento de veiculo (PF e PJ)...")
    df = sgs.get(codigos)  # DataFrame multivariado indexado por data
    df = df.sort_index()
    print(f"  -> {len(df)} meses recebidos ({df.index.min().date()} a {df.index.max().date()})")

    nome = args.nome_csv or (
        dt.date.today().strftime("%Y.%m.%d") + " - Taxas Bacen - Financiamento de Veiculo.csv"
    )
    caminho = os.path.join(args.outdir, nome)

    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow([
            "Data",
            "Taxa anual PF (% a.a.)",
            "Taxa mensal PF (% a.m.)",
            "Taxa anual PJ (% a.a.)",
            "Taxa mensal PJ (% a.m.)",
            "Fonte",
        ])
        fonte = (
            f"Bacen SGS {codigos['PF_anual']} (PF a.a.) / {codigos['PF_mensal']} (PF a.m.) / "
            f"{codigos['PJ_anual']} (PJ a.a.) / {codigos['PJ_mensal']} (PJ a.m.)"
        )
        for data, row in df.iterrows():
            ym = f"{data.year:04d}-{data.month:02d}"

            def cel(col: str) -> str:
                v = row.get(col)
                return fmt_br(float(v)) if v is not None and v == v else ""  # v==v: nao-NaN

            w.writerow([
                ym,
                cel("PF_anual"),
                cel("PF_mensal"),
                cel("PJ_anual"),
                cel("PJ_mensal"),
                fonte,
            ])

    print(f"\nOK - CSV gravado em:\n  {caminho}")


if __name__ == "__main__":
    main()
