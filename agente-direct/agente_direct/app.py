"""Servidor do webhook: recebe o direct do Instagram e responde com o agente.

Rodar:  uvicorn agente_direct.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response

from .cerebro import Cerebro, links_permitidos, montar_sistema
from .config import Config
from .instagram import ClienteInstagram, Evento, assinatura_valida, dividir, extrair_eventos
from .memoria import Memoria

log = logging.getLogger("agente_direct")

# Usada quando a conversa precisa do dono da conta e o modelo não escreveu a mensagem de espera
# (recusa, link bloqueado, teto de mensagens, resposta inválida).
MENSAGEM_ESPERA = "Essa eu quero te responder com calma, pessoalmente. Me dá um tempinho que eu te retorno aqui mesmo, tá?"


class Orquestrador:
    """Agrupa as mensagens de cada lead, chama o agente e envia a resposta."""

    def __init__(self, cfg: Config, memoria: Memoria, ig: ClienteInstagram, cerebro: Cerebro):
        self.cfg, self.memoria, self.ig, self.cerebro = cfg, memoria, ig, cerebro
        self._timers: dict[str, asyncio.Task] = {}
        self._ocupado: set[str] = set()
        self._pendente: set[str] = set()
        self._ecos_esperados: set[tuple[str, str]] = set()

    # --- entrada ---------------------------------------------------------
    def receber(self, evento: Evento) -> None:
        if evento.eco:
            self._receber_eco(evento)
            return
        if not self.memoria.registrar(evento.conversa, "user", evento.texto, evento.mid or None):
            return  # a Meta reenviou um webhook que já processamos
        self.agendar(evento.conversa)

    def _receber_eco(self, evento: Evento) -> None:
        chave = (evento.conversa, evento.texto)
        if chave in self._ecos_esperados:
            self._ecos_esperados.discard(chave)
            return
        if not evento.mid or self.memoria.foi_enviado_pelo_agente(evento.mid):
            return
        # Você respondeu pelo app: registra, tira o agente da conversa por um tempo e,
        # se ela estava esperando por você, devolve ao agente depois desse tempo.
        if self.memoria.registrar(evento.conversa, "humano", evento.texto, evento.mid):
            self.memoria.atualizar_lead(evento.conversa, transferido=0)
            self.memoria.pausar(evento.conversa, self.cfg.pausa_humano_horas)
            log.info("Você respondeu %s manualmente; agente pausado por %sh.",
                     evento.conversa, self.cfg.pausa_humano_horas)

    def agendar(self, conversa: str) -> None:
        if conversa in self._ocupado:
            self._pendente.add(conversa)
            return
        anterior = self._timers.get(conversa)
        if anterior and not anterior.done():
            anterior.cancel()
        self._timers[conversa] = asyncio.create_task(self._esperar_e_responder(conversa))

    async def _esperar_e_responder(self, conversa: str) -> None:
        # Espera o lead terminar de digitar: quem manda 3 balões seguidos recebe 1 resposta.
        await asyncio.sleep(self.cfg.espera_agrupar_s)
        self._ocupado.add(conversa)
        try:
            await self.responder(conversa)
        except Exception as erro:
            log.exception("Erro ao responder %s", conversa)
            # Claude fora do ar, chave errada etc.: o lead não fica no vácuo.
            try:
                await self.esperar_dono(conversa, f"erro técnico ao responder ({type(erro).__name__}); veja os logs")
            except Exception:
                log.exception("Também não consegui pedir para %s aguardar", conversa)
        finally:
            self._ocupado.discard(conversa)
            if conversa in self._pendente:
                self._pendente.discard(conversa)
                self.agendar(conversa)

    # --- resposta --------------------------------------------------------
    async def responder(self, conversa: str) -> None:
        if self.memoria.esta_pausado(conversa):
            return
        historico = self.memoria.historico(conversa)
        if not historico or historico[-1]["role"] != "user":
            return

        lead = self.memoria.lead(conversa)
        if not lead["username"]:
            perfil = await self.ig.perfil(conversa)
            if perfil:
                self.memoria.atualizar_lead(conversa, username=perfil.get("username"),
                                            nome=perfil.get("name"))
                lead = self.memoria.lead(conversa)

        usuario = (lead["username"] or "").lower()
        if usuario in self.cfg.bloqueados or conversa in self.cfg.bloqueados:
            return  # sócio, família, equipe: o agente nunca responde
        if self.cfg.sandbox and usuario not in self.cfg.sandbox:
            log.info("SANDBOX: ignorando @%s (fora da lista de teste).", usuario or conversa)
            return
        if self.memoria.enviadas_desde(conversa, time.time() - 86400) >= self.cfg.max_msgs_sessao:
            await self.esperar_dono(conversa, f"conversa longa: {self.cfg.max_msgs_sessao} mensagens em 24 h")
            return

        hoje = datetime.now(ZoneInfo(self.cfg.fuso)).strftime("%d/%m/%Y")
        contexto = ", ".join(f"{k}: {v}" for k, v in
                             (("data de hoje", hoje), ("nome", lead["nome"]), ("@", lead["username"])) if v)

        await self.ig.digitando(conversa)
        decisao = await self.cerebro.decidir(historico, contexto)

        if decisao.ficha:
            self.memoria.atualizar_lead(conversa, ficha=decisao.ficha)
        for texto in decisao.mensagens:
            if self.memoria.esta_pausado(conversa):
                return  # você assumiu a conversa enquanto o agente pensava
            await self.enviar(conversa, texto)
        if decisao.transferir:
            await self.esperar_dono(conversa, decisao.motivo, avisar_lead=not decisao.mensagens)

    async def enviar(self, conversa: str, texto: str) -> None:
        for pedaco in dividir(texto):
            self._ecos_esperados.add((conversa, pedaco))
        mids = await self.ig.enviar_texto(conversa, texto)
        for mid in mids:
            self.memoria.marcar_enviado(mid)
        self.memoria.registrar(conversa, "assistant", texto, mids[0] if mids else None)

    async def esperar_dono(self, conversa: str, motivo: str, avisar_lead: bool = True) -> None:
        """O agente pede para o lead aguardar, sai da conversa e avisa o dono da conta."""
        if avisar_lead and not self.memoria.esta_pausado(conversa):
            await self.enviar(conversa, MENSAGEM_ESPERA)
        self.memoria.atualizar_lead(conversa, transferido=1)
        await self.notificar(conversa, motivo)

    # --- follow-up ---------------------------------------------------------
    async def verificar_followups(self, agora: float | None = None) -> int:
        """Manda UM toque a quem sumiu, ainda dentro da janela de 24 h do Instagram.

        Fora da janela a Meta não entrega mensagem, por isso não existe segundo toque.
        """
        agora = agora or time.time()
        hora = datetime.fromtimestamp(agora, ZoneInfo(self.cfg.fuso)).hour
        if not (self.cfg.followup_hora_inicio <= hora < self.cfg.followup_hora_fim):
            return 0
        enviados = 0
        for lead in self.memoria.listar_leads():
            conversa = lead["conversa"]
            if self.memoria.esta_pausado(conversa) or conversa in self._ocupado:
                continue
            ultima, ultima_do_lead = self.memoria.ultimas(conversa)
            ficha = lead["ficha"] or {}
            if (not ultima or ultima["papel"] != "assistant"
                    or lead["followup_em"] >= ultima_do_lead
                    or ficha.get("estagio") in ("desqualificado", "suporte")
                    or ficha.get("produto_recomendado") in ("nenhum", None)):
                continue
            idade_h = (agora - ultima_do_lead) / 3600
            if not (self.cfg.followup_apos_h <= idade_h < 23.5):
                continue
            await self.enviar(conversa, texto_followup(lead["nome"], ficha.get("dor_resumida", "")))
            self.memoria.atualizar_lead(conversa, followup_em=agora)
            enviados += 1
        return enviados

    async def renovar_token_se_preciso(self, agora: float | None = None) -> bool:
        """Renova o token a cada 7 dias e guarda no banco: ninguém precisa lembrar."""
        agora = agora or time.time()
        if agora - float(self.memoria.ajuste("ig_token_renovado_em", "0")) < 7 * 86400:
            return False
        dados = await self.ig.renovar_token()
        self.ig.token = dados["access_token"]
        self.memoria.gravar_ajuste("ig_token", self.ig.token)
        self.memoria.gravar_ajuste("ig_token_renovado_em", str(agora))
        log.info("Token do Instagram renovado (vale mais %s dias).", int(dados.get("expires_in", 0)) // 86400)
        return True

    async def laco_token(self, intervalo_s: float = 6 * 3600) -> None:
        while True:
            try:
                await self.renovar_token_se_preciso()
            except Exception:
                log.exception("Não consegui renovar o token do Instagram; rode `agente-direct verificar`.")
            await asyncio.sleep(intervalo_s)

    async def laco_followup(self, intervalo_s: float = 600) -> None:
        while True:
            try:
                await self.verificar_followups()
            except Exception:
                log.exception("Erro no follow-up")
            await asyncio.sleep(intervalo_s)

    async def notificar(self, conversa: str, motivo: str) -> None:
        """Avisa o dono da conta que alguém está esperando resposta no direct."""
        lead = self.memoria.lead(conversa)
        quem = f"@{lead['username']}" if lead["username"] else conversa
        log.warning("ESPERANDO RESPOSTA MANUAL %s: %s", quem, motivo)
        ficha = lead["ficha"] or {}
        texto = (f"📩 {quem} ({lead['nome'] or 'sem nome'}) está esperando sua resposta no direct.\n"
                 f"O que responder: {motivo or 'ver conversa'}\n"
                 f"Resumo: {ficha.get('resumo_lead', '')}\n"
                 f"Produto: {ficha.get('produto_recomendado', '')}")
        async with httpx.AsyncClient(timeout=10) as http:
            if self.cfg.telegram_token and self.cfg.telegram_chat_id:
                try:
                    await http.post(f"https://api.telegram.org/bot{self.cfg.telegram_token}/sendMessage",
                                    json={"chat_id": self.cfg.telegram_chat_id, "text": texto})
                except httpx.HTTPError:
                    log.exception("Falha ao avisar no Telegram")
            if self.cfg.notificar_url:
                try:
                    await http.post(self.cfg.notificar_url, json={
                        "evento": "lead_esperando_resposta", "conversa": conversa,
                        "username": lead["username"], "nome": lead["nome"],
                        "motivo": motivo, "ficha": lead["ficha"], "texto": texto, "em": time.time(),
                    })
                except httpx.HTTPError:
                    log.exception("Falha ao notificar %s", self.cfg.notificar_url)


def texto_followup(nome: str | None, dor: str) -> str:
    """Copy do atalho /sumiu1 da casa."""
    primeiro = (nome or "").split(" ")[0]
    sobre = f" sobre {dor.strip().rstrip('.')}" if dor and dor.strip() else ""
    frase = f"retomo nossa conversa{sobre}. Ficou algum ponto sem resposta para você decidir?"
    return f"{primeiro}, {frase}" if primeiro else frase[0].upper() + frase[1:]


def criar_app(cfg: Config | None = None, orquestrador: Orquestrador | None = None,
              followup: bool = True) -> FastAPI:
    cfg = cfg or Config.do_ambiente()
    if orquestrador is None:
        memoria = Memoria(cfg.banco)
        # o token renovado pelo próprio servidor (no banco) vale mais que o do .env,
        # a não ser que o .env tenha sido trocado depois (agente-direct configurar)
        token = cfg.ig_access_token
        if memoria.ajuste("ig_token_origem") == cfg.ig_access_token and memoria.ajuste("ig_token"):
            token = memoria.ajuste("ig_token")
        else:
            memoria.gravar_ajuste("ig_token_origem", cfg.ig_access_token)
            memoria.gravar_ajuste("ig_token", cfg.ig_access_token)
            memoria.gravar_ajuste("ig_token_renovado_em", str(time.time()))
        ig = ClienteInstagram(token, cfg.graph_versao, cfg.modo_teste)
        cerebro = Cerebro(montar_sistema(cfg.pasta_conhecimento, cfg.dono), cfg.modelo, cfg.esforco,
                          links=links_permitidos(cfg.pasta_conhecimento))
        orquestrador = Orquestrador(cfg, memoria, ig, cerebro)
    orq = orquestrador

    @contextlib.asynccontextmanager
    async def ciclo(_app):
        tarefas = [asyncio.create_task(orq.laco_followup()),
                   asyncio.create_task(orq.laco_token())] if followup else []
        yield
        for tarefa in tarefas:
            tarefa.cancel()

    app = FastAPI(title=f"Agente Direct — {cfg.dono}", lifespan=ciclo)
    app.state.orquestrador = orq

    def _admin(autorizacao: str | None) -> None:
        if not cfg.admin_token or autorizacao != f"Bearer {cfg.admin_token}":
            raise HTTPException(401, "não autorizado")

    @app.get("/saude")
    async def saude():
        return {"ok": True, "modelo": cfg.modelo, "modo_teste": cfg.modo_teste}

    @app.get("/privacidade")
    async def privacidade():
        """Política de privacidade mínima: a Meta exige uma URL dessas para publicar o app."""
        return Response(media_type="text/html; charset=utf-8", content=f"""<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Privacidade — {cfg.dono}</title>
<body style="font-family:sans-serif;max-width:680px;margin:40px auto;padding:0 16px;line-height:1.5">
<h1>Política de privacidade</h1>
<p>Este serviço responde mensagens enviadas ao Instagram de {cfg.dono}, com ajuda de
inteligência artificial. Guardamos o texto das conversas, o nome e o @ do Instagram
de quem escreve, apenas para continuar o atendimento e oferecer os produtos de {cfg.dono}.</p>
<p>Os dados não são vendidos nem compartilhados, exceto com os provedores técnicos
necessários para o funcionamento: Meta (Instagram) e Anthropic (Claude).</p>
<h2>Exclusão de dados</h2>
<p>Para apagar seus dados, envie no direct a mensagem "apagar meus dados". O pedido é
atendido manualmente por {cfg.dono} em até 15 dias.</p>
</body></html>""")

    @app.get("/webhook")
    async def verificar(modo: str = Query("", alias="hub.mode"),
                        token: str = Query("", alias="hub.verify_token"),
                        desafio: str = Query("", alias="hub.challenge")):
        # A Meta chama isto uma vez, quando você cadastra a URL do webhook no painel.
        if modo == "subscribe" and cfg.ig_verify_token and token == cfg.ig_verify_token:
            return Response(content=desafio, media_type="text/plain")
        raise HTTPException(403, "token de verificação inválido")

    @app.post("/webhook")
    async def webhook(request: Request, x_hub_signature_256: str | None = Header(None)):
        corpo = await request.body()
        if not assinatura_valida(corpo, x_hub_signature_256, cfg.ig_app_secret):
            raise HTTPException(401, "assinatura inválida")
        for evento in extrair_eventos(await request.json(), cfg.ig_user_id):
            orq.receber(evento)
        return {"ok": True}  # responder rápido: a Meta reenvia se demorar

    @app.get("/leads")
    async def leads(authorization: str | None = Header(None)):
        _admin(authorization)
        return orq.memoria.listar_leads()

    @app.get("/leads/{conversa}")
    async def lead(conversa: str, authorization: str | None = Header(None)):
        _admin(authorization)
        return {**orq.memoria.lead(conversa), "historico": orq.memoria.historico(conversa, 200)}

    @app.post("/leads/{conversa}/retomar")
    async def retomar(conversa: str, authorization: str | None = Header(None)):
        """Devolve a conversa para o agente (depois de uma transferência ou pausa)."""
        _admin(authorization)
        orq.memoria.atualizar_lead(conversa, pausado_ate=0, transferido=0)
        return {"ok": True}

    @app.post("/leads/{conversa}/pausar")
    async def pausar(conversa: str, horas: float = 24 * 365, authorization: str | None = Header(None)):
        _admin(authorization)
        orq.memoria.pausar(conversa, horas)
        return {"ok": True}

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def __getattr__(nome: str):
    # `uvicorn agente_direct.app:app` cria o app só quando é pedido (os testes não precisam de .env).
    if nome == "app":
        return criar_app()
    raise AttributeError(nome)
