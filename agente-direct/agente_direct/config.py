"""Configuração lida de variáveis de ambiente (veja .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _carregar_dotenv(caminho: Path) -> None:
    """Carrega um .env simples (CHAVE=valor) sem sobrescrever o ambiente."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    # Instagram (API oficial da Meta — Instagram API com login do Instagram)
    ig_access_token: str = ""
    ig_app_secret: str = ""
    ig_verify_token: str = ""
    ig_user_id: str = ""
    graph_versao: str = "v23.0"

    # Claude
    modelo: str = "claude-opus-5-5"
    esforco: str = "medium"

    # Comportamento
    espera_agrupar_s: float = 8.0
    pausa_humano_horas: float = 24.0
    banco: Path = field(default_factory=lambda: RAIZ / "dados" / "direct.sqlite3")
    pasta_conhecimento: Path = field(default_factory=lambda: RAIZ / "conhecimento")
    notificar_url: str = ""
    admin_token: str = ""
    modo_teste: bool = False  # True: não envia nada ao Instagram, só registra no log

    @classmethod
    def do_ambiente(cls) -> "Config":
        _carregar_dotenv(RAIZ / ".env")
        e = os.environ.get
        return cls(
            ig_access_token=e("IG_ACCESS_TOKEN", ""),
            ig_app_secret=e("IG_APP_SECRET", ""),
            ig_verify_token=e("IG_VERIFY_TOKEN", ""),
            ig_user_id=e("IG_USER_ID", ""),
            graph_versao=e("GRAPH_VERSAO", "v23.0"),
            modelo=e("MODELO", "claude-opus-5-5"),
            esforco=e("ESFORCO", "medium"),
            espera_agrupar_s=float(e("ESPERA_AGRUPAR_S", "8")),
            pausa_humano_horas=float(e("PAUSA_HUMANO_HORAS", "24")),
            banco=Path(e("BANCO", str(RAIZ / "dados" / "direct.sqlite3"))),
            pasta_conhecimento=Path(e("PASTA_CONHECIMENTO", str(RAIZ / "conhecimento"))),
            notificar_url=e("NOTIFICAR_URL", ""),
            admin_token=e("ADMIN_TOKEN", ""),
            modo_teste=e("MODO_TESTE", "0").lower() in ("1", "true", "sim"),
        )
