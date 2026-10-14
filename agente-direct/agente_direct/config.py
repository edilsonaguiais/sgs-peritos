"""Configuração lida do arquivo .env (criado por `agente-direct configurar`)."""

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
    # Quem é o dono da conta (como o agente se refere a ele)
    dono: str = "o dono da conta"

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
    telegram_token: str = ""     # bot do Telegram que te avisa quando alguém espera sua resposta
    telegram_chat_id: str = ""
    admin_token: str = ""
    modo_teste: bool = False  # True: não envia nada ao Instagram, só registra no log

    # Freios
    max_msgs_sessao: int = 15           # mensagens do agente por conversa em 24 h; no teto, passa para humano
    bloqueados: frozenset = frozenset()  # @ (sem arroba) ou IGSID que o agente nunca atende
    sandbox: frozenset = frozenset()     # se preenchido, o agente SÓ atende estes @ (fase de teste)

    # Follow-up (um único toque, dentro da janela de 24 h do Instagram)
    followup_apos_h: float = 20.0
    fuso: str = "America/Sao_Paulo"
    followup_hora_inicio: int = 8
    followup_hora_fim: int = 21

    @classmethod
    def do_ambiente(cls) -> "Config":
        _carregar_dotenv(RAIZ / ".env")
        e = os.environ.get
        return cls(
            dono=e("DONO_NOME", "o dono da conta"),
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
            telegram_token=e("TELEGRAM_TOKEN", ""),
            telegram_chat_id=e("TELEGRAM_CHAT_ID", ""),
            admin_token=e("ADMIN_TOKEN", ""),
            modo_teste=e("MODO_TESTE", "0").lower() in ("1", "true", "sim"),
            max_msgs_sessao=int(e("MAX_MSGS_SESSAO", "15")),
            bloqueados=_lista(e("BLOQUEADOS", "")),
            sandbox=_lista(e("SANDBOX", "")),
            followup_apos_h=float(e("FOLLOWUP_APOS_H", "20")),
            fuso=e("FUSO", "America/Sao_Paulo"),
        )


def _lista(valor: str) -> frozenset:
    return frozenset(v.strip().lstrip("@").lower() for v in valor.split(",") if v.strip())
