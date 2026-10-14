"""Integração oficial com a Instagram API (Meta) — webhooks e envio de mensagens.

Usa a "Instagram API com login do Instagram" (graph.instagram.com), que exige
conta profissional (Empresa ou Criador de conteúdo) e as permissões
instagram_business_basic + instagram_business_manage_messages.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

LIMITE_TEXTO = 1000  # a Send API aceita até 1000 bytes UTF-8 por mensagem de texto


def assinatura_valida(corpo: bytes, cabecalho: str | None, app_secret: str) -> bool:
    """Confere o X-Hub-Signature-256 que a Meta manda em todo POST do webhook."""
    if not app_secret or not cabecalho or not cabecalho.startswith("sha256="):
        return False
    esperado = hmac.new(app_secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecalho.removeprefix("sha256="))


@dataclass
class Evento:
    """Uma mensagem de direct recebida pelo webhook."""
    conversa: str        # IGSID do lead (id do usuário com escopo no Instagram)
    mid: str
    texto: str
    eco: bool            # True quando a mensagem saiu da sua conta (agente ou você no app)


def extrair_eventos(payload: dict, ig_user_id: str = "") -> list[Evento]:
    """Converte o JSON do webhook em eventos de mensagem. Ignora leituras, reações etc."""
    eventos: list[Evento] = []
    if payload.get("object") != "instagram":
        return eventos
    for entrada in payload.get("entry", []):
        conta = str(entrada.get("id", ""))
        for item in entrada.get("messaging", []):
            msg = item.get("message")
            if not msg or msg.get("is_deleted") or msg.get("is_unsupported"):
                continue
            remetente = str(item.get("sender", {}).get("id", ""))
            destinatario = str(item.get("recipient", {}).get("id", ""))
            eco = bool(msg.get("is_echo")) or remetente in {conta, ig_user_id} - {""}
            conversa = destinatario if eco else remetente
            eventos.append(Evento(conversa=conversa, mid=msg.get("mid", ""), texto=_texto(msg), eco=eco))
    return eventos


def _texto(msg: dict) -> str:
    """Texto da mensagem, com uma descrição entre colchetes para anexos e respostas a stories."""
    partes = []
    reply_to = msg.get("reply_to") or {}
    if "story" in reply_to:
        partes.append("[o lead respondeu a um story seu]")
    for anexo in msg.get("attachments", []) or []:
        tipo = anexo.get("type", "arquivo")
        nomes = {"audio": "um áudio", "image": "uma imagem", "video": "um vídeo",
                 "share": "uma publicação compartilhada", "story_mention": "uma menção em story",
                 "ig_reel": "um reel", "file": "um arquivo"}
        partes.append(f"[o lead enviou {nomes.get(tipo, 'um anexo')}]")
    if msg.get("text"):
        partes.append(msg["text"])
    return " ".join(partes) or "[mensagem sem texto]"


def dividir(texto: str, limite: int = LIMITE_TEXTO) -> list[str]:
    """Quebra um texto longo em pedaços que cabem no limite de bytes da Send API."""
    pedacos, atual = [], ""
    for palavra in texto.split(" "):
        candidato = f"{atual} {palavra}".strip()
        if len(candidato.encode()) > limite and atual:
            pedacos.append(atual)
            atual = palavra
        else:
            atual = candidato
    if atual:
        pedacos.append(atual)
    return pedacos


class ClienteInstagram:
    def __init__(self, access_token: str, versao: str = "v23.0", modo_teste: bool = False,
                 http: httpx.AsyncClient | None = None):
        self.token = access_token
        self.base = f"https://graph.instagram.com/{versao}"
        self.modo_teste = modo_teste
        self.http = http or httpx.AsyncClient(timeout=20)

    async def enviar_texto(self, igsid: str, texto: str) -> list[str]:
        """Envia texto ao lead e devolve os message_id gerados."""
        mids = []
        for pedaco in dividir(texto):
            if self.modo_teste:
                log.info("[MODO_TESTE] para %s: %s", igsid, pedaco)
                mids.append(f"teste-{len(mids)}-{hash(pedaco)}")
                continue
            resp = await self.http.post(
                f"{self.base}/me/messages",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"recipient": {"id": igsid}, "message": {"text": pedaco}},
            )
            if resp.status_code >= 400:
                log.error("Falha ao enviar para %s: %s %s", igsid, resp.status_code, resp.text)
                resp.raise_for_status()
            mids.append(resp.json().get("message_id", ""))
        return mids

    async def digitando(self, igsid: str) -> None:
        """Mostra "digitando..." para o lead (melhor esforço, ignora erro)."""
        if self.modo_teste:
            return
        try:
            await self.http.post(
                f"{self.base}/me/messages",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"recipient": {"id": igsid}, "sender_action": "typing_on"},
            )
        except httpx.HTTPError:
            pass

    async def perfil(self, igsid: str) -> dict:
        """Nome e @ do lead (permitido depois que ele te mandou mensagem)."""
        if self.modo_teste:
            return {}
        try:
            resp = await self.http.get(
                f"{self.base}/{igsid}",
                params={"fields": "name,username,is_user_follow_business,follower_count"},
                headers={"Authorization": f"Bearer {self.token}"},
            )
            return resp.json() if resp.status_code == 200 else {}
        except httpx.HTTPError:
            return {}

    async def renovar_token(self) -> dict:
        """Renova o token de longa duração (vale 60 dias; o servidor renova sozinho toda semana)."""
        resp = await self.http.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": self.token},
        )
        resp.raise_for_status()
        return resp.json()

    # --- configuração da conta (usado pelo comando agente-direct) -----------
    async def conta(self) -> dict:
        """Confere o token e devolve {user_id, username} da conta profissional."""
        resp = await self.http.get(f"{self.base}/me", params={
            "fields": "user_id,username,account_type", "access_token": self.token})
        if resp.status_code != 200:
            raise ErroMeta(_mensagem_erro(resp))
        return resp.json()

    async def inscrever_mensagens(self) -> None:
        """Liga o envio de DMs desta conta para o webhook do app."""
        resp = await self.http.post(f"{self.base}/me/subscribed_apps", params={
            "subscribed_fields": "messages", "access_token": self.token})
        if resp.status_code != 200 or not resp.json().get("success"):
            raise ErroMeta(_mensagem_erro(resp))

    async def inscricoes(self) -> list[str]:
        resp = await self.http.get(f"{self.base}/me/subscribed_apps", params={"access_token": self.token})
        if resp.status_code != 200:
            raise ErroMeta(_mensagem_erro(resp))
        campos: list[str] = []
        for app in resp.json().get("data", []):
            campos += app.get("subscribed_fields", [])
        return campos


class ErroMeta(Exception):
    pass


def _mensagem_erro(resp: httpx.Response) -> str:
    try:
        erro = resp.json().get("error", {})
        return f"{erro.get('message', resp.text)} (código {erro.get('code', resp.status_code)})"
    except ValueError:
        return f"HTTP {resp.status_code}: {resp.text[:200]}"
