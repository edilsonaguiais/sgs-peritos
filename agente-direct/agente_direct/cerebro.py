"""O agente de vendas: monta o prompt, chama o Claude e devolve resposta + ficha BANT."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

STATUS_BANT = ["desconhecido", "nao_atende", "parcial", "atende"]
PRODUTOS = ["aguias_da_pericia", "aguias_one", "autoria10x", "mastermind", "nenhum", "indefinido"]
ESTAGIOS = ["abertura", "qualificacao", "apresentacao", "objecao", "fechamento",
            "suporte", "desqualificado"]


def _item_bant(descricao: str) -> dict:
    return {
        "type": "object",
        "description": descricao,
        "properties": {
            "status": {"type": "string", "enum": STATUS_BANT},
            "evidencia": {"type": "string", "description": "O que o lead disse que sustenta o status."},
        },
        "required": ["status", "evidencia"],
        "additionalProperties": False,
    }


ESQUEMA_RESPOSTA = {
    "type": "object",
    "properties": {
        "mensagens": {
            "type": "array",
            "description": "1 a 3 balões de direct, na ordem de envio. Lista vazia = não responder.",
            "items": {"type": "string"},
        },
        "bant": {
            "type": "object",
            "properties": {
                "budget": _item_bant("Orçamento / capacidade de investir."),
                "authority": _item_bant("Decide sozinho ou depende de alguém."),
                "need": _item_bant("Dor/necessidade que um dos produtos resolve."),
                "timing": _item_bant("Quer resolver agora ou depois."),
            },
            "required": ["budget", "authority", "need", "timing"],
            "additionalProperties": False,
        },
        "perfil": {"type": "string", "description": "Ex.: perito bancário, fatura ~R$ 8 mil/mês, Planeta Explorador."},
        "produto_recomendado": {"type": "string", "enum": PRODUTOS},
        "estagio": {"type": "string", "enum": ESTAGIOS},
        "transferir_para_humano": {"type": "boolean"},
        "motivo_transferencia": {"type": "string"},
        "resumo_lead": {"type": "string", "description": "2 a 3 frases para a equipe comercial."},
    },
    "required": ["mensagens", "bant", "perfil", "produto_recomendado", "estagio",
                 "transferir_para_humano", "motivo_transferencia", "resumo_lead"],
    "additionalProperties": False,
}

INSTRUCOES = """\
Você atende o direct do Instagram do Edilson Aguiais (Instituto IBCAPPA). Seu trabalho
é conversar com quem chega, entender o perfil da pessoa e vender, quando fizer
sentido, UM destes produtos: Mentoria Águias da Perícia, Águias One ou AutorIA 10X.
O método de venda é o BANT, descrito abaixo. A seguir estão três documentos: o tom
de voz, os produtos e o método. Siga-os.

Regras que valem acima de tudo:
- Escreva com o tom de voz do documento. Mensagens curtas de direct, sem markdown,
  uma pergunta por vez.
- Use só os fatos de <produtos>. Se um dado estiver marcado [PREENCHER] ou não
  existir, não invente: diga que vai confirmar com o time e marque
  transferir_para_humano = true.
- Se perguntarem se é robô, IA ou assistente automático, não negue: diga que é o
  assistente do Edilson no direct e ofereça chamar alguém do time.
- Não peça dados sensíveis (CPF, cartão, senha) pelo direct.
- Se a última mensagem não pede resposta (um "ok", "valeu", emoji, reação), responda
  no máximo com um balão curto ou devolva mensagens = [].
- Se o lead já é aluno e precisa de suporte, ou quer falar com uma pessoa, faça a
  ponte com uma frase e transfira.
- Mensagens entre colchetes como "[o lead enviou um áudio]" descrevem anexos que você
  não consegue ver nem ouvir. Peça com naturalidade que a pessoa escreva o principal.
- Mensagens marcadas "[resposta enviada manualmente pela equipe]" foram escritas pelo
  time; continue a partir delas sem contradizê-las.
- Preencha a ficha (bant, perfil, produto_recomendado, estagio, resumo_lead) com tudo o
  que já se sabe na conversa inteira, não só na última mensagem.
"""


@dataclass
class Decisao:
    mensagens: list[str]
    ficha: dict
    transferir: bool
    motivo: str


def montar_sistema(pasta: Path) -> str:
    def ler(nome: str) -> str:
        return (pasta / nome).read_text(encoding="utf-8").strip()

    return (
        f"{INSTRUCOES}\n"
        f"<tom_de_voz>\n{ler('tom_de_voz.md')}\n</tom_de_voz>\n\n"
        f"<produtos>\n{ler('produtos.md')}\n</produtos>\n\n"
        f"<metodo_bant>\n{ler('metodo_bant.md')}\n</metodo_bant>"
    )


class Cerebro:
    def __init__(self, sistema: str, modelo: str = "claude-opus-5-5", esforco: str = "medium",
                 cliente: anthropic.AsyncAnthropic | None = None):
        self.sistema = sistema
        self.modelo = modelo
        self.esforco = esforco
        self.cliente = cliente or anthropic.AsyncAnthropic()

    async def decidir(self, historico: list[dict], contexto_lead: str = "") -> Decisao:
        """Gera a próxima resposta para a conversa. O histórico termina numa fala do lead."""
        mensagens = [dict(m) for m in historico]
        if contexto_lead and mensagens and mensagens[-1]["role"] == "user":
            mensagens[-1]["content"] = [
                {"type": "text", "text": mensagens[-1]["content"]},
                {"type": "text", "text": f"<contexto_do_lead>{contexto_lead}</contexto_do_lead>"},
            ]

        resp = await self.cliente.beta.messages.create(
            model=self.modelo,
            max_tokens=8000,
            system=[{"type": "text", "text": self.sistema, "cache_control": {"type": "ephemeral"}}],
            messages=mensagens,
            output_config={"effort": self.esforco,
                           "format": {"type": "json_schema", "schema": ESQUEMA_RESPOSTA}},
            # Se um classificador de segurança recusar, a API refaz no modelo de reserva indicado.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

        if resp.stop_reason == "refusal":
            log.warning("Recusa do modelo (%s); transferindo para humano.", resp.stop_details)
            return Decisao([], {}, True, "o modelo recusou responder; revisar manualmente")
        if resp.stop_reason == "max_tokens":
            log.warning("Resposta cortada por max_tokens; transferindo para humano.")
            return Decisao([], {}, True, "resposta incompleta do modelo")

        texto = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            dados = json.loads(texto)
        except json.JSONDecodeError:
            log.error("JSON inválido do modelo: %r", texto[:500])
            return Decisao([], {}, True, "resposta inválida do modelo")

        mensagens_saida = [m.strip() for m in dados.pop("mensagens", []) if m and m.strip()][:3]
        transferir = bool(dados.get("transferir_para_humano"))
        return Decisao(mensagens_saida, dados, transferir, dados.get("motivo_transferencia", ""))
