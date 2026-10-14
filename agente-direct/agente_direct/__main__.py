"""agente-direct: configura, conecta e confere o agente que atende o direct do Instagram.

    agente-direct configurar     pergunta as chaves, confere cada uma e grava o .env
    agente-direct conectar       liga o webhook da Meta à sua conta
    agente-direct verificar      checklist: o que está funcionando e o que falta
    agente-direct testar         conversa com o agente no terminal, sem Instagram
    agente-direct gerar-tom ARQ  escreve um rascunho do seu tom de voz a partir dos seus textos
    agente-direct iniciar        sobe o servidor (o Docker já faz isso por você)
    agente-direct renovar-token  renova o token do Instagram agora
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import secrets
import shutil
import sys
import time
from pathlib import Path

import anthropic
import httpx

from .cerebro import links_permitidos
from .config import RAIZ, Config
from .instagram import ClienteInstagram, ErroMeta
from .memoria import Memoria

ENV = RAIZ / ".env"
CONHECIMENTO = RAIZ / "conhecimento"
ARQUIVOS = ("tom_de_voz.md", "produtos.md", "metodo_bant.md")
OK, ERRO, AVISO = "✅", "❌", "⚠️ "

ORDEM_ENV = [
    ("# Quem é você", None),
    ("DONO_NOME", ""),
    ("# Claude (console.anthropic.com > API Keys)", None),
    ("ANTHROPIC_API_KEY", ""), ("MODELO", "claude-opus-5-5"), ("ESFORCO", "medium"),
    ("# Instagram (Meta for Developers > seu app > Instagram > API com login do Instagram)", None),
    ("IG_ACCESS_TOKEN", ""), ("IG_APP_SECRET", ""), ("IG_USER_ID", ""), ("IG_USERNAME", ""),
    ("IG_VERIFY_TOKEN", ""), ("GRAPH_VERSAO", "v23.0"),
    ("# Endereço público do servidor (sem https://)", None),
    ("DOMINIO", ""),
    ("# Aviso no Telegram quando alguém espera sua resposta", None),
    ("TELEGRAM_TOKEN", ""), ("TELEGRAM_CHAT_ID", ""),
    ("# Senha das rotas /leads", None),
    ("ADMIN_TOKEN", ""),
    ("# Freios (veja o README)", None),
    ("MAX_MSGS_SESSAO", "15"), ("BLOQUEADOS", ""), ("SANDBOX", ""), ("FOLLOWUP_APOS_H", "20"),
    ("FUSO", "America/Sao_Paulo"), ("MODO_TESTE", "0"),
]


# --- .env ------------------------------------------------------------------
def ler_env() -> dict[str, str]:
    valores: dict[str, str] = {}
    if ENV.exists():
        for linha in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                chave, valor = linha.split("=", 1)
                valores[chave.strip()] = valor.strip()
    return valores


def gravar_env(valores: dict[str, str]) -> None:
    linhas, usadas = [], set()
    for chave, padrao in ORDEM_ENV:
        if padrao is None:
            linhas.append(f"\n{chave}")
            continue
        linhas.append(f"{chave}={valores.get(chave, padrao)}")
        usadas.add(chave)
    extras = [f"{k}={v}" for k, v in valores.items() if k not in usadas]
    if extras:
        linhas += ["\n# Outros"] + extras
    # escreve no mesmo arquivo (no Docker o .env é montado como arquivo)
    with open(ENV, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas).lstrip() + "\n")
    try:
        os.chmod(ENV, 0o600)
    except OSError:
        pass


def mascarar(valor: str) -> str:
    return f"…{valor[-4:]}" if len(valor) > 8 else ("definido" if valor else "")


def perguntar(rotulo: str, atual: str = "", segredo: bool = False, opcional: bool = False) -> str:
    dica = f" [Enter mantém {mascarar(atual) if segredo else atual}]" if atual else (" [opcional]" if opcional else "")
    while True:
        leitura = getpass.getpass if segredo else input
        valor = leitura(f"{rotulo}{dica}: ").strip()
        if valor:
            return valor
        if atual or opcional:
            return atual
        print("   Esse campo é obrigatório.")


def titulo(texto: str) -> None:
    print(f"\n── {texto} " + "─" * max(0, 60 - len(texto)))


# --- checagens que o configurar e o verificar compartilham -------------------
async def checar_claude(chave: str, modelo: str) -> str | None:
    try:
        await anthropic.AsyncAnthropic(api_key=chave).models.retrieve(modelo)
        return None
    except anthropic.AuthenticationError:
        return "chave do Claude recusada"
    except anthropic.NotFoundError:
        return f"o modelo {modelo} não está disponível para esta chave"
    except anthropic.APIError as e:
        return f"erro ao falar com o Claude: {e}"


async def checar_instagram(token: str, versao: str) -> tuple[dict | None, str | None]:
    try:
        return await ClienteInstagram(token, versao).conta(), None
    except ErroMeta as e:
        return None, str(e)
    except httpx.HTTPError as e:
        return None, f"não consegui falar com a Meta ({e})"


def token_atual(cfg: Config) -> str:
    """O servidor renova o token sozinho e guarda no banco; use o mais novo."""
    try:
        memoria = Memoria(cfg.banco)
        if memoria.ajuste("ig_token_origem") == cfg.ig_access_token and memoria.ajuste("ig_token"):
            return memoria.ajuste("ig_token")
    except Exception:
        pass
    return cfg.ig_access_token


async def ip_publico() -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            return (await http.get("https://api.ipify.org")).text.strip()
    except httpx.HTTPError:
        return ""


def placeholders(pasta: Path) -> list[str]:
    """Trechos de modelo que ainda não foram preenchidos, tipo [SEU NOME]."""
    achados = []
    for nome in ARQUIVOS:
        arquivo = pasta / nome
        if arquivo.exists():
            achados += [f"{nome}: {m}" for m in re.findall(r"\[[A-ZÁÉÍÓÚÂÊÔÃÕÇ@ /_.]{4,}[^\]]*\]",
                                                        arquivo.read_text(encoding="utf-8"))]
    return achados


# --- configurar ---------------------------------------------------------------
async def configurar() -> int:
    v = ler_env()
    print("Vou te fazer algumas perguntas e conferir cada chave na hora.\n"
          "Enter mantém o valor atual. Nada do que você digitar aparece na tela quando é senha.")

    titulo("1/6 Quem é você")
    v["DONO_NOME"] = perguntar("Seu nome, do jeito que o agente vai se referir a você", v.get("DONO_NOME", ""))

    titulo("2/6 Claude")
    modelo = v.get("MODELO") or "claude-opus-5-5"
    while True:
        v["ANTHROPIC_API_KEY"] = perguntar("Chave da API do Claude (sk-ant-...)", v.get("ANTHROPIC_API_KEY", ""), segredo=True)
        erro = await checar_claude(v["ANTHROPIC_API_KEY"], modelo)
        if not erro:
            print(f"   {OK} chave aceita, modelo {modelo}")
            break
        print(f"   {ERRO} {erro}. Tente de novo.")
        v["ANTHROPIC_API_KEY"] = ""

    titulo("3/6 Instagram")
    print("   No painel da Meta: seu app > Instagram > Configuração da API com login do Instagram\n"
          "   > Gerar tokens de acesso > Adicionar conta. Copie o token gerado.")
    versao = v.get("GRAPH_VERSAO") or "v23.0"
    while True:
        v["IG_ACCESS_TOKEN"] = perguntar("Token de acesso do Instagram", v.get("IG_ACCESS_TOKEN", ""), segredo=True)
        conta, erro = await checar_instagram(v["IG_ACCESS_TOKEN"], versao)
        if conta:
            v["IG_USER_ID"] = str(conta.get("user_id") or conta.get("id"))
            v["IG_USERNAME"] = conta.get("username", "")
            print(f"   {OK} conectado como @{v['IG_USERNAME']} (conta {conta.get('account_type', 'profissional')})")
            break
        print(f"   {ERRO} {erro}. Gere um token novo e cole de novo.")
        v["IG_ACCESS_TOKEN"] = ""
    print("   Na mesma tela, copie a 'Chave secreta do app do Instagram' (Instagram app secret).")
    while True:
        v["IG_APP_SECRET"] = perguntar("Chave secreta do app do Instagram", v.get("IG_APP_SECRET", ""), segredo=True)
        if re.fullmatch(r"[0-9a-f]{32}", v["IG_APP_SECRET"]):
            break
        print(f"   {AVISO}a chave secreta costuma ter 32 letras e números (0-9, a-f). Confira e cole de novo.")
        if input("   Usar mesmo assim? (s/N) ").strip().lower() == "s":
            break

    titulo("4/6 Endereço do servidor")
    ip = await ip_publico()
    sugestao = v.get("DOMINIO") or (f"{ip.replace('.', '-')}.sslip.io" if ip else "")
    print("   Use um subdomínio seu (ex.: direct.seusite.com.br) apontado para o IP desta máquina,\n"
          "   ou aceite o endereço automático *.sslip.io, que funciona sem domínio próprio.")
    v["DOMINIO"] = perguntar("Endereço (sem https://)", sugestao).removeprefix("https://").strip("/")

    titulo("5/6 Aviso no Telegram (opcional)")
    print("   Quando alguém precisar da sua resposta, você recebe um aviso no Telegram.\n"
          "   Crie um bot com o @BotFather e cole o token aqui. Enter pula.")
    v["TELEGRAM_TOKEN"] = perguntar("Token do bot do Telegram", v.get("TELEGRAM_TOKEN", ""), segredo=True, opcional=True)
    if v["TELEGRAM_TOKEN"] and not v.get("TELEGRAM_CHAT_ID"):
        v["TELEGRAM_CHAT_ID"] = await descobrir_chat_telegram(v["TELEGRAM_TOKEN"])

    titulo("6/6 Conhecimento (tom de voz, produtos, método)")
    preparar_conhecimento()

    v.setdefault("IG_VERIFY_TOKEN", "")
    v["IG_VERIFY_TOKEN"] = v["IG_VERIFY_TOKEN"] or secrets.token_urlsafe(24)
    v["ADMIN_TOKEN"] = v.get("ADMIN_TOKEN") or secrets.token_urlsafe(24)
    gravar_env(v)
    print(f"\n{OK} Configuração gravada em {ENV}.")
    print("Próximo passo: edite os 3 arquivos da pasta conhecimento/ e rode `agente-direct conectar`.")
    return 0


async def descobrir_chat_telegram(token: str) -> str:
    base = f"https://api.telegram.org/bot{token}"
    async with httpx.AsyncClient(timeout=40) as http:
        try:
            eu = (await http.get(f"{base}/getMe")).json()
        except httpx.HTTPError:
            print(f"   {ERRO} não consegui falar com o Telegram. Pulei esta etapa.")
            return ""
        if not eu.get("ok"):
            print(f"   {ERRO} token do Telegram recusado. Pulei esta etapa.")
            return ""
        print(f"   Abra o Telegram, procure @{eu['result']['username']} e mande /start. Esperando…")
        for _ in range(6):
            dados = (await http.get(f"{base}/getUpdates", params={"timeout": 25})).json()
            for item in reversed(dados.get("result", [])):
                chat = (item.get("message") or {}).get("chat", {})
                if chat.get("id"):
                    await http.post(f"{base}/sendMessage", json={
                        "chat_id": chat["id"], "text": "✅ Pronto! Vou te avisar aqui quando alguém esperar sua resposta no direct."})
                    print(f"   {OK} Telegram ligado (te mandei uma mensagem de teste).")
                    return str(chat["id"])
    print(f"   {AVISO}não recebi o /start. Rode `agente-direct configurar` de novo depois.")
    return ""


def preparar_conhecimento() -> None:
    CONHECIMENTO.mkdir(exist_ok=True)
    if all((CONHECIMENTO / n).exists() for n in ARQUIVOS):
        print(f"   {OK} a pasta conhecimento/ já tem os 3 arquivos (não mexi).")
        return
    exemplos = sorted(p.name for p in (RAIZ / "exemplos").iterdir() if p.is_dir()) if (RAIZ / "exemplos").exists() else []
    print("   Com o que você quer começar?\n   1) modelo em branco para preencher")
    for i, nome in enumerate(exemplos, start=2):
        print(f"   {i}) exemplo pronto: {nome}")
    escolha = input("   Escolha [1]: ").strip() or "1"
    origem = RAIZ / "modelos" / "conhecimento"
    if escolha.isdigit() and 2 <= int(escolha) < 2 + len(exemplos):
        origem = RAIZ / "exemplos" / exemplos[int(escolha) - 2]
    for nome in ARQUIVOS:
        if not (CONHECIMENTO / nome).exists():
            shutil.copy(origem / nome, CONHECIMENTO / nome)
    print(f"   {OK} copiei {origem.relative_to(RAIZ)} para conhecimento/.")


# --- conectar -----------------------------------------------------------------
async def conectar() -> int:
    cfg = Config.do_ambiente()
    v = ler_env()
    dominio = v.get("DOMINIO", "")
    if not (cfg.ig_access_token and cfg.ig_verify_token and dominio):
        print(f"{ERRO} Rode `agente-direct configurar` primeiro.")
        return 1
    base = f"https://{dominio}"

    titulo("1/3 Seu servidor está no ar?")
    if not await url_ok(f"{base}/saude"):
        print(f"{ERRO} {base}/saude não respondeu. Confira se o endereço aponta para o IP desta\n"
              "   máquina e se as portas 80 e 443 estão liberadas no firewall. Depois rode de novo.")
        return 1
    print(f"   {OK} {base} respondendo com HTTPS")

    titulo("2/3 Webhook no painel da Meta (a única parte manual)")
    print(f"""   No painel do seu app: Instagram > Configuração da API com login do Instagram
   > Configurar webhooks. Preencha:

      URL de callback:        {base}/webhook
      Token de verificação:   {cfg.ig_verify_token}

   Clique em "Verificar e salvar" e depois ative o campo "messages".
   Em Configurações do app > Básico, use como URL da política de privacidade
   e de exclusão de dados:  {base}/privacidade""")
    input("\n   Feito? Aperte Enter para eu continuar.")

    titulo("3/3 Ligando as mensagens da sua conta")
    ig = ClienteInstagram(token_atual(cfg), cfg.graph_versao)
    try:
        await ig.inscrever_mensagens()
        campos = await ig.inscricoes()
    except ErroMeta as e:
        print(f"{ERRO} A Meta recusou: {e}\n   Confira se o webhook foi salvo no passo 2 e rode de novo.")
        return 1
    print(f"   {OK} conta inscrita no webhook: {', '.join(campos) or 'messages'}")
    print("""
Falta conferir duas coisas no celular e no painel:
  • App do Instagram > Configurações > Mensagens e respostas a stories > Controles de
    mensagens > Ferramentas conectadas > Permitir acesso a mensagens: LIGADO.
  • Painel da Meta: publique o app (modo Ativo / Live).

Teste: mande uma DM de OUTRA conta para a sua e acompanhe com `agente-direct logs`.""")
    return 0


async def url_ok(url: str, params: dict | None = None, esperado: str | None = None) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as http:
            resp = await http.get(url, params=params)
        return resp.status_code == 200 and (esperado is None or resp.text == esperado)
    except httpx.HTTPError:
        return False


# --- verificar ----------------------------------------------------------------
async def verificar() -> int:
    cfg = Config.do_ambiente()
    v = ler_env()
    falhas = 0

    def linha(ok: bool, texto: str, conserto: str = "") -> None:
        nonlocal falhas
        falhas += 0 if ok else 1
        print(f"{OK if ok else ERRO} {texto}" + ("" if ok or not conserto else f"\n     → {conserto}"))

    faltando = [k for k in ("DONO_NOME", "ANTHROPIC_API_KEY", "IG_ACCESS_TOKEN", "IG_APP_SECRET", "IG_VERIFY_TOKEN")
                if not v.get(k) and not os.environ.get(k)]
    linha(not faltando, "configuração completa" if not faltando else f"faltam no .env: {', '.join(faltando)}",
          "rode `agente-direct configurar`")

    pasta = cfg.pasta_conhecimento
    existentes = [n for n in ARQUIVOS if (pasta / n).exists()]
    linha(len(existentes) == 3, f"conhecimento em {pasta}", "rode `agente-direct configurar` para criar a pasta")
    if len(existentes) == 3:
        pendentes = placeholders(pasta)
        linha(not pendentes, "conhecimento preenchido" if not pendentes else
              f"ainda há campos do modelo para preencher: {'; '.join(pendentes[:5])}",
              "edite os arquivos da pasta conhecimento/")
        links = links_permitidos(pasta)
        linha(bool(links), f"{len(links)} link(s) de venda em produtos.md", "coloque o link de compra em produtos.md")

    if chave := (v.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        erro = await checar_claude(chave, cfg.modelo)
        linha(erro is None, f"Claude ({cfg.modelo})" if not erro else erro, "confira a chave em console.anthropic.com")

    if cfg.ig_access_token:
        token = token_atual(cfg)
        conta, erro = await checar_instagram(token, cfg.graph_versao)
        linha(conta is not None, f"Instagram @{conta['username']}" if conta else f"Instagram: {erro}",
              "confira a internet do servidor; se ela estiver ok, gere um token novo no painel da Meta "
              "e rode `agente-direct configurar`")
        if conta:
            try:
                campos = await ClienteInstagram(token, cfg.graph_versao).inscricoes()
                linha("messages" in campos, "mensagens chegando no webhook" if "messages" in campos
                      else "a conta não está inscrita para mensagens", "rode `agente-direct conectar`")
            except ErroMeta as e:
                linha(False, f"inscrição do webhook: {e}", "rode `agente-direct conectar`")

    if dominio := v.get("DOMINIO"):
        base = f"https://{dominio}"
        linha(await url_ok(f"{base}/saude"), f"servidor no ar em {base}",
              "confira o DNS, as portas 80/443 e `agente-direct logs`")
        linha(await url_ok(f"{base}/webhook", {"hub.mode": "subscribe", "hub.verify_token": cfg.ig_verify_token,
                                               "hub.challenge": "teste123"}, "teste123"),
              "webhook respondendo à verificação da Meta", "confira IG_VERIFY_TOKEN e reinicie")

    print("\nTudo certo! 🎉" if not falhas else f"\n{falhas} item(ns) para resolver.")
    return 1 if falhas else 0


# --- gerar-tom ----------------------------------------------------------------
PROMPT_TOM = """Abaixo estão textos reais de uma pessoa (legendas, mensagens, transcrições).
Escreva o arquivo tom_de_voz.md que vai ensinar um assistente a responder o direct do
Instagram exatamente como essa pessoa escreve. Siga a estrutura do modelo, em português
do Brasil, e baseie cada item em padrões que aparecem de verdade nos textos: saudações,
vocabulário, expressões repetidas, tamanho das frases, uso de emoji, ideias e frases
marcantes (cite literalmente). Não invente o que não estiver nos textos; se algo não der
para saber, deixe o campo do modelo entre colchetes. Responda só com o conteúdo do arquivo.

<modelo>
{modelo}
</modelo>

<textos>
{textos}
</textos>"""


async def gerar_tom(arquivo: str) -> int:
    cfg = Config.do_ambiente()
    caminho = Path(arquivo)
    if not caminho.exists() and (CONHECIMENTO / arquivo).exists():
        caminho = CONHECIMENTO / arquivo
    if not caminho.exists():
        print(f"{ERRO} Não achei {arquivo}. Coloque o arquivo na pasta conhecimento/ e rode de novo.")
        return 1
    textos = caminho.read_text(encoding="utf-8", errors="ignore")
    modelo = (RAIZ / "modelos" / "conhecimento" / "tom_de_voz.md").read_text(encoding="utf-8")
    print(f"Lendo {len(textos):,} caracteres e escrevendo seu tom de voz…")
    cliente = anthropic.AsyncAnthropic()
    async with cliente.messages.stream(
        model=cfg.modelo, max_tokens=16000, output_config={"effort": "high"},
        messages=[{"role": "user", "content": PROMPT_TOM.format(modelo=modelo, textos=textos)}],
    ) as stream:
        resp = await stream.get_final_message()
    if resp.stop_reason == "refusal":
        print(f"{ERRO} O modelo não conseguiu processar esses textos.")
        return 1
    texto = next((b.text for b in resp.content if b.type == "text"), "").strip()
    destino = CONHECIMENTO / "tom_de_voz.rascunho.md"
    CONHECIMENTO.mkdir(exist_ok=True)
    destino.write_text(texto + "\n", encoding="utf-8")
    print(f"{OK} Rascunho em {destino}. Revise e, se gostar, renomeie para tom_de_voz.md.")
    return 0


# --- outros -------------------------------------------------------------------
async def renovar_token() -> int:
    cfg = Config.do_ambiente()
    memoria = Memoria(cfg.banco)
    ig = ClienteInstagram(token_atual(cfg), cfg.graph_versao)
    try:
        dados = await ig.renovar_token()
    except httpx.HTTPStatusError as e:
        print(f"{ERRO} A Meta recusou a renovação: {e.response.text[:300]}")
        return 1
    memoria.gravar_ajuste("ig_token_origem", cfg.ig_access_token)
    memoria.gravar_ajuste("ig_token", dados["access_token"])
    memoria.gravar_ajuste("ig_token_renovado_em", str(time.time()))
    print(f"{OK} Token renovado; vale mais {int(dados.get('expires_in', 0)) // 86400} dias. Reinicie o agente.")
    return 0


def iniciar() -> int:
    import uvicorn
    uvicorn.run("agente_direct.app:app", host="0.0.0.0", port=int(os.environ.get("PORTA", "8000")), workers=1)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agente-direct", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    for nome in ("configurar", "conectar", "verificar", "testar", "iniciar", "renovar-token"):
        sub.add_parser(nome)
    tom = sub.add_parser("gerar-tom")
    tom.add_argument("arquivo", help="arquivo .txt com textos seus")
    args = parser.parse_args(argv)

    try:
        if args.comando == "iniciar":
            return iniciar()
        if args.comando == "testar":
            from .simular import main as simular
            asyncio.run(simular())
            return 0
        acoes = {"configurar": configurar, "conectar": conectar, "verificar": verificar,
                 "renovar-token": renovar_token}
        if args.comando == "gerar-tom":
            return asyncio.run(gerar_tom(args.arquivo))
        return asyncio.run(acoes[args.comando]())
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
