"""O agente de vendas: monta o prompt, chama o Claude e devolve resposta + ficha BANT."""

from __future__ import annotations

import json
import logging
import re
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
        "transferir_para_humano": {"type": "boolean", "description": (
            "true quando o Edilson precisa responder pessoalmente; a mensagem pede para o lead aguardar.")},
        "motivo_transferencia": {"type": "string", "description": "O que o Edilson precisa responder."},
        "resumo_lead": {"type": "string", "description": "2 a 3 frases para o Edilson se situar rápido."},
        "dor_resumida": {"type": "string", "description": (
            "A dor principal nas palavras do lead, curta, para completar a frase "
            "'retomo nossa conversa sobre ...'. Ex.: 'conseguir clientes sem depender de indicação'. "
            "Vazio se ainda não se sabe.")},
    },
    "required": ["mensagens", "bant", "perfil", "produto_recomendado", "estagio",
                 "transferir_para_humano", "motivo_transferencia", "resumo_lead", "dor_resumida"],
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
- Não existe time de atendimento. Quando algo precisa do Edilson (veja <metodo_bant>),
  peça para a pessoa aguardar que ele responde pessoalmente por aqui e marque
  transferir_para_humano = true. Nunca diga "vou passar para o time".
- Use só os fatos de <produtos>. Se um dado não estiver lá, não invente: peça para
  aguardar e marque transferir_para_humano = true.
- Links: copie exatamente os de <produtos>, sem alterar nada. Um link fora da lista é
  bloqueado e a conversa fica para o Edilson.
- Com interesse do lead, mande preço + link + uma pergunta na mesma mensagem. Você
  mesmo envia o link; não precisa transferir para isso.
- A data de hoje vem em <contexto_do_lead>. Respeite as validades de <produtos>.
- Se perguntarem se é robô, IA ou assistente automático, não negue: diga que é o
  assistente do Edilson no direct e que ele mesmo responde pessoalmente se a pessoa
  preferir (nesse caso, transferir_para_humano = true).
- Não peça dados sensíveis (CPF, cartão, senha) pelo direct.
- Se a última mensagem não pede resposta (um "ok", "valeu", emoji, reação), responda
  no máximo com um balão curto ou devolva mensagens = [].
- Se o lead já é aluno e precisa de suporte, ou quer falar com o Edilson, peça para
  aguardar e marque transferir_para_humano = true.
- Mensagens entre colchetes como "[o lead enviou um áudio]" descrevem anexos que você
  não consegue ver nem ouvir. Peça com naturalidade que a pessoa escreva o principal.
- Mensagens marcadas "[resposta enviada manualmente pelo Edilson]" foram escritas por
  ele; continue a partir delas sem contradizê-las nem repeti-las.
- Preencha a ficha (bant, perfil, produto_recomendado, estagio, resumo_lead,
  dor_resumida) com tudo o que já se sabe na conversa inteira, não só na última
  mensagem. Se o lead recusou ou não tem perfil, estagio = desqualificado; se já é
  aluno ou já comprou, estagio = suporte. Nesses dois casos ninguém faz follow-up.
"""


@dataclass
class Decisao:
    mensagens: list[str]
    ficha: dict
    transferir: bool
    motivo: str


RE_URL = re.compile(r"https?://[^\s<>\"']+")


def extrair_links(texto: str) -> set[str]:
    return {u.rstrip(".,;:!?)]*`") for u in RE_URL.findall(texto)}


def links_permitidos(pasta: Path) -> set[str]:
    """Os únicos links que o agente pode mandar: os que estão em produtos.md."""
    return extrair_links((pasta / "produtos.md").read_text(encoding="utf-8"))


def limpar(texto: str) -> str:
    """Rede de segurança de estilo: a casa não usa travessão."""
    texto = re.sub(r"\s*[—–]\s*", ", ", texto)
    return re.sub(r",\s*,", ",", texto).strip()


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
                 cliente: anthropic.AsyncAnthropic | None = None, links: set[str] | None = None):
        self.sistema = sistema
        self.links = links
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

        mensagens_saida = [limpar(m) for m in dados.pop("mensagens", []) if m and m.strip()][:3]
        transferir = bool(dados.get("transferir_para_humano"))
        motivo = dados.get("motivo_transferencia", "")

        if self.links is not None:
            estranhos = set().union(*(extrair_links(m) for m in mensagens_saida)) - self.links
            if estranhos:
                log.error("Link fora de produtos.md bloqueado: %s", estranhos)
                return Decisao([], dados, True, f"o agente tentou enviar link não autorizado: {sorted(estranhos)}")
        return Decisao(mensagens_saida, dados, transferir, motivo)
