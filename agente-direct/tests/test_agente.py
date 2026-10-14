import asyncio
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from agente_direct.app import Orquestrador, criar_app
from agente_direct.cerebro import ESQUEMA_RESPOSTA, Decisao, montar_sistema
from agente_direct.config import Config, RAIZ
from agente_direct.instagram import ClienteInstagram, dividir, extrair_eventos
from agente_direct.memoria import Memoria

SEGREDO = "segredo-do-app"
CONTA = "17841400000000000"
LEAD = "990011"


class CerebroFalso:
    def __init__(self, mensagens=("Fala, Doutor! Você já atua como perito?",), transferir=False):
        self.mensagens, self.transferir, self.chamadas = list(mensagens), transferir, []

    async def decidir(self, historico, contexto_lead=""):
        self.chamadas.append(historico)
        return Decisao(self.mensagens, {"produto_recomendado": "aguias_da_pericia"},
                       self.transferir, "lead pronto" if self.transferir else "")


def montar(cerebro=None, enviados=None):
    cfg = Config(ig_access_token="tok", ig_app_secret=SEGREDO, ig_verify_token="verifica",
                 ig_user_id=CONTA, espera_agrupar_s=0.05, admin_token="adm")
    enviados = enviados if enviados is not None else []

    def handler(request: httpx.Request):
        if request.method == "POST":
            corpo = json.loads(request.content)
            if "message" in corpo:
                enviados.append(corpo["message"]["text"])
            return httpx.Response(200, json={"recipient_id": LEAD, "message_id": f"m_bot_{len(enviados)}"})
        return httpx.Response(200, json={"username": "dra.carla", "name": "Carla"})

    ig = ClienteInstagram("tok", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    orq = Orquestrador(cfg, Memoria(":memory:"), ig, cerebro or CerebroFalso())
    return cfg, orq, enviados


def payload(texto, mid, eco=False):
    remetente, destino = (CONTA, LEAD) if eco else (LEAD, CONTA)
    msg = {"mid": mid, "text": texto}
    if eco:
        msg["is_echo"] = True
    return {"object": "instagram", "entry": [{"id": CONTA, "time": 1, "messaging": [
        {"sender": {"id": remetente}, "recipient": {"id": destino}, "timestamp": 1, "message": msg}]}]}


def assinar(corpo: bytes) -> str:
    return "sha256=" + hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()


def test_verificacao_do_webhook():
    cfg, orq, _ = montar()
    cliente = TestClient(criar_app(cfg, orq))
    ok = cliente.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verifica",
                                         "hub.challenge": "123"})
    assert ok.status_code == 200 and ok.text == "123"
    assert cliente.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "x",
                                           "hub.challenge": "1"}).status_code == 403


def test_rejeita_assinatura_invalida():
    cfg, orq, _ = montar()
    cliente = TestClient(criar_app(cfg, orq))
    corpo = json.dumps(payload("oi", "m1")).encode()
    r = cliente.post("/webhook", content=corpo, headers={"X-Hub-Signature-256": "sha256=errado"})
    assert r.status_code == 401


def test_agrupa_mensagens_e_responde_uma_vez():
    async def cenario():
        _, orq, enviados = montar()
        for i, texto in enumerate(["oi", "vi seu post", "quero saber da mentoria"]):
            for ev in extrair_eventos(payload(texto, f"m{i}"), CONTA):
                orq.receber(ev)
        await asyncio.sleep(0.3)
        return orq, enviados

    orq, enviados = asyncio.run(cenario())
    assert len(orq.cerebro.chamadas) == 1
    assert orq.cerebro.chamadas[0][-1]["content"] == "oi\nvi seu post\nquero saber da mentoria"
    assert enviados == ["Fala, Doutor! Você já atua como perito?"]
    lead = orq.memoria.lead(LEAD)
    assert lead["username"] == "dra.carla"
    assert lead["ficha"]["produto_recomendado"] == "aguias_da_pericia"


def test_webhook_repetido_nao_gera_segunda_resposta():
    async def cenario():
        _, orq, enviados = montar()
        for _ in range(2):
            for ev in extrair_eventos(payload("oi", "m-dup"), CONTA):
                orq.receber(ev)
        await asyncio.sleep(0.2)
        return enviados

    assert len(asyncio.run(cenario())) == 1


def test_eco_do_agente_e_ignorado_e_resposta_humana_pausa():
    async def cenario():
        _, orq, enviados = montar()
        for ev in extrair_eventos(payload("oi", "m1"), CONTA):
            orq.receber(ev)
        await asyncio.sleep(0.2)
        # eco da mensagem que o próprio agente enviou: não pausa
        for ev in extrair_eventos(payload(enviados[0], "m_bot_1", eco=True), CONTA):
            orq.receber(ev)
        assert not orq.memoria.esta_pausado(LEAD)
        # você responde pelo app: pausa e o agente fica quieto
        for ev in extrair_eventos(payload("Oi Carla, aqui é o Edilson!", "m_humano", eco=True), CONTA):
            orq.receber(ev)
        assert orq.memoria.esta_pausado(LEAD)
        for ev in extrair_eventos(payload("que legal!", "m2"), CONTA):
            orq.receber(ev)
        await asyncio.sleep(0.2)
        return orq, enviados

    orq, enviados = asyncio.run(cenario())
    assert len(enviados) == 1
    hist = orq.memoria.historico(LEAD)
    assert "[resposta enviada manualmente pela equipe]" in hist[1]["content"]


def test_transferencia_para_humano_desliga_agente():
    async def cenario():
        _, orq, enviados = montar(CerebroFalso(["Vou te passar pro time agora."], transferir=True))
        for ev in extrair_eventos(payload("quero pagar à vista", "m1"), CONTA):
            orq.receber(ev)
        await asyncio.sleep(0.2)
        for ev in extrair_eventos(payload("e aí?", "m2"), CONTA):
            orq.receber(ev)
        await asyncio.sleep(0.2)
        return orq, enviados

    orq, enviados = asyncio.run(cenario())
    assert enviados == ["Vou te passar pro time agora."]
    assert orq.memoria.lead(LEAD)["transferido"] == 1


def test_anexos_viram_descricao():
    p = payload("", "m1")
    p["entry"][0]["messaging"][0]["message"] = {"mid": "m1", "attachments": [{"type": "audio"}]}
    assert extrair_eventos(p, CONTA)[0].texto == "[o lead enviou um áudio]"


def test_dividir_respeita_limite_de_bytes():
    texto = "perícia " * 400
    partes = dividir(texto)
    assert all(len(p.encode()) <= 1000 for p in partes)
    assert " ".join(partes) == texto.strip()


def test_prompt_inclui_os_tres_documentos():
    sistema = montar_sistema(RAIZ / "conhecimento")
    for marca in ("<tom_de_voz>", "<produtos>", "<metodo_bant>", "ÁGUIAS ONE", "AutorIA 10X", "8df263aed54d460"):
        assert marca in sistema


def _sem_propriedades_soltas(no):
    if isinstance(no, dict):
        if no.get("type") == "object":
            assert no.get("additionalProperties") is False
            assert set(no["required"]) == set(no["properties"])
        for v in no.values():
            _sem_propriedades_soltas(v)


def test_esquema_valido_para_saida_estruturada():
    _sem_propriedades_soltas(ESQUEMA_RESPOSTA)


# --- salvaguardas novas ----------------------------------------------------
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx2

from agente_direct.app import texto_followup
from agente_direct.cerebro import Cerebro, limpar, links_permitidos


def _resposta_claude(mensagens, **extra):
    corpo = {"mensagens": mensagens,
             "bant": {k: {"status": "desconhecido", "evidencia": ""} for k in ("budget", "authority", "need", "timing")},
             "perfil": "", "produto_recomendado": "aguias_one", "estagio": "apresentacao",
             "transferir_para_humano": False, "motivo_transferencia": "", "resumo_lead": "",
             "dor_resumida": "", **extra}

    def handler(request):
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": json.dumps(corpo)}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})
    import anthropic
    return anthropic.AsyncAnthropic(api_key="x", http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))


def test_links_oficiais_estao_na_lista_permitida():
    links = links_permitidos(RAIZ / "conhecimento")
    assert "https://go.eduq.tec.br/r/8df263aed54d460" in links      # ONE fora do evento
    assert "https://go.eduq.tec.br/r/8df26455d32e839" in links      # Águias fora do evento
    assert "https://inscricao.eduqtecnologia.com.br/detalhes/218?dominio=ibcappa" in links
    assert "https://go.eduq.tec.br/r/8df2639b988a75a" not in links  # ONE preço de evento
    assert "https://go.eduq.tec.br/r/8df26454b4d6cdc" not in links  # Águias preço de evento


def test_link_nao_autorizado_e_bloqueado_e_transfere():
    links = links_permitidos(RAIZ / "conhecimento")
    cliente = _resposta_claude(["Segue o link: https://go.eduq.tec.br/r/8df2639b988a75a"])
    cerebro = Cerebro("sistema", cliente=cliente, links=links)
    d = asyncio.run(cerebro.decidir([{"role": "user", "content": "quero o link"}]))
    assert d.mensagens == [] and d.transferir


def test_link_oficial_passa_mesmo_com_pontuacao():
    links = links_permitidos(RAIZ / "conhecimento")
    texto = "São 12x de R$ 1.500. Matrícula: https://go.eduq.tec.br/r/8df263aed54d460. Faz sentido para você?"
    cerebro = Cerebro("sistema", cliente=_resposta_claude([texto]), links=links)
    d = asyncio.run(cerebro.decidir([{"role": "user", "content": "quanto custa?"}]))
    assert d.mensagens == [texto] and not d.transferir


def test_tira_travessao():
    assert limpar("Não é sobre laudo — é sobre negócio") == "Não é sobre laudo, é sobre negócio"


def test_bloqueados_e_sandbox():
    async def cenario(cfg_extra):
        cfg, orq, enviados = montar()
        orq.cfg = Config(**{**cfg.__dict__, **cfg_extra})
        for ev in extrair_eventos(payload("oi", "m1"), CONTA):
            orq.receber(ev)
        await asyncio.sleep(0.2)
        return enviados

    assert asyncio.run(cenario({"bloqueados": frozenset({"dra.carla"})})) == []
    assert asyncio.run(cenario({"sandbox": frozenset({"outra.pessoa"})})) == []
    assert len(asyncio.run(cenario({"sandbox": frozenset({"dra.carla"})}))) == 1


def test_teto_de_mensagens_passa_para_humano():
    async def cenario():
        cfg, orq, enviados = montar()
        orq.cfg = Config(**{**cfg.__dict__, "max_msgs_sessao": 1})
        for i in range(2):
            for ev in extrair_eventos(payload(f"msg {i}", f"m{i}"), CONTA):
                orq.receber(ev)
            await asyncio.sleep(0.2)
        return orq, enviados

    orq, enviados = asyncio.run(cenario())
    assert len(enviados) == 1
    assert orq.memoria.lead(LEAD)["transferido"] == 1


def test_followup_um_unico_toque_dentro_da_janela():
    fuso = ZoneInfo("America/Sao_Paulo")
    t_lead = datetime(2026, 10, 14, 14, 0, tzinfo=fuso).timestamp()   # lead falou às 14h

    async def cenario():
        _, orq, enviados = montar()
        for ev in extrair_eventos(payload("quero saber do ONE", "m1"), CONTA):
            orq.receber(ev)
        await asyncio.sleep(0.2)
        orq.memoria._db.execute("UPDATE mensagens SET criado_em = ? WHERE papel = 'user'", (t_lead,))
        orq.memoria._db.execute("UPDATE mensagens SET criado_em = ? WHERE papel = 'assistant'", (t_lead + 60,))
        orq.memoria.atualizar_lead(LEAD, ficha={"produto_recomendado": "aguias_one", "estagio": "apresentacao",
                                                "dor_resumida": "conseguir clientes sem indicação"})
        cedo = await orq.verificar_followups(t_lead + 5 * 3600)        # 19h, cedo demais
        primeiro = await orq.verificar_followups(t_lead + 21 * 3600)   # 11h do dia seguinte
        segundo = await orq.verificar_followups(t_lead + 21.2 * 3600)  # já mandou, não repete
        fora = await orq.verificar_followups(t_lead + 30 * 3600)       # janela de 24 h fechada
        return cedo, primeiro, segundo, fora, enviados

    cedo, primeiro, segundo, fora, enviados = asyncio.run(cenario())
    assert (cedo, primeiro, segundo, fora) == (0, 1, 0, 0)
    assert enviados[-1] == ("Carla, retomo nossa conversa sobre conseguir clientes sem indicação. "
                            "Ficou algum ponto sem resposta para você decidir?")


def test_followup_respeita_silencio_noturno():
    fuso = ZoneInfo("America/Sao_Paulo")
    t_lead = datetime(2026, 10, 14, 5, 0, tzinfo=fuso).timestamp()    # 20 h depois = 1h da manhã

    async def cenario():
        _, orq, _ = montar()
        for ev in extrair_eventos(payload("oi", "m1"), CONTA):
            orq.receber(ev)
        await asyncio.sleep(0.2)
        orq.memoria._db.execute("UPDATE mensagens SET criado_em = ?", (t_lead,))
        orq.memoria.atualizar_lead(LEAD, ficha={"produto_recomendado": "aguias_one", "estagio": "apresentacao"})
        return await orq.verificar_followups(t_lead + 20.5 * 3600)

    assert asyncio.run(cenario()) == 0


def test_texto_followup_sem_nome_e_sem_dor():
    assert texto_followup(None, "") == "Retomo nossa conversa. Ficou algum ponto sem resposta para você decidir?"
