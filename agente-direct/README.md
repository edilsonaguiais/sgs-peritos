# Agente Direct

Um agente de IA que atende o direct do seu Instagram com o seu jeito de escrever,
descobre o perfil de quem chegou (método BANT) e vende o produto certo, mandando
preço e link de compra. Quando a pergunta precisa de você, ele pede para a pessoa
aguardar e te avisa no Telegram.

Usa a **API oficial da Meta** (sem senha, sem robô de navegador, sem risco de
bloqueio) e o **Claude** como cérebro. Cada pessoa instala no próprio servidor, com o
próprio app da Meta: não depende de ninguém e não precisa de aprovação da Meta para
atender a própria conta.

## O que você precisa

| Item | Onde conseguir | Custo aproximado |
|---|---|---|
| Conta do Instagram **profissional** (Empresa ou Criador) | App do Instagram > Configurações > Tipo de conta | grátis |
| Conta de desenvolvedor da Meta | <https://developers.facebook.com> | grátis |
| Chave da API do Claude | <https://console.anthropic.com> > API Keys | por uso |
| Um servidor Linux (Ubuntu ou Debian), 1 GB de RAM | qualquer VPS: Hostinger, Contabo, DigitalOcean, Hetzner… | ~US$ 5/mês |
| Domínio próprio (opcional) | se não tiver, o instalador usa um endereço grátis `*.sslip.io` | |
| Bot do Telegram (opcional) | @BotFather no Telegram | grátis |

## Instalação em 4 passos

### 1. Crie o app na Meta (10 minutos, uma vez só)
Siga o [GUIA-META.md](GUIA-META.md). No fim você terá um **token de acesso** e a
**chave secreta do app**.

### 2. Rode um comando no servidor
Entre no servidor por SSH e cole:

```bash
curl -fsSL https://raw.githubusercontent.com/edilsonaguiais/sgs-peritos/claude/agente-direct-instagram/agente-direct/instalar.sh | sudo bash
```

O instalador:
1. instala o Docker, se precisar;
2. baixa o agente para `/opt/agente-direct`;
3. pergunta as chaves (Claude, Instagram, Telegram) e **confere cada uma na hora**;
4. sobe o servidor com HTTPS automático;
5. mostra a URL e o token que você cola no painel da Meta e liga as mensagens da
   sua conta.

### 3. Ensine o agente
Ele aprende com 3 arquivos de texto, na pasta `conhecimento/`:

| Arquivo | O que vai nele | Comando |
|---|---|---|
| `tom_de_voz.md` | como você escreve: saudação, expressões, o que você nunca faz | `agente-direct editar tom_de_voz.md` |
| `produtos.md` | o que você vende: para quem é, preço, link de compra | `agente-direct editar produtos.md` |
| `metodo_bant.md` | como conduzir a venda e quando deixar para você | `agente-direct editar metodo_bant.md` |

Os arquivos já vêm com um modelo para preencher. Para o tom de voz tem atalho: junte
de 20 a 50 textos seus (legendas, respostas de direct, transcrições de vídeo) num
arquivo, coloque em `/opt/agente-direct/conhecimento/textos.txt` e rode:

```bash
agente-direct gerar-tom textos.txt
```

O Claude escreve um rascunho (`tom_de_voz.rascunho.md`) para você revisar.

Tem um exemplo completo e real em [`exemplos/edilson-aguiais/`](exemplos/edilson-aguiais),
com três mentorias, preços, links e regras de venda.

> **Segurança dos links:** o agente só consegue enviar links que estão em
> `produtos.md`. Qualquer outro é bloqueado antes de sair.

### 4. Teste e libere
```bash
agente-direct testar      # converse com o agente no terminal, sem Instagram
agente-direct verificar   # checklist de tudo: chaves, conhecimento, servidor, webhook
```
Depois mande uma DM de **outra** conta para a sua e acompanhe com
`agente-direct logs`. Leia as 10 primeiras conversas reais antes de divulgar: só
libere se você assinaria todas as respostas.

## Comandos do dia a dia

| Comando | O que faz |
|---|---|
| `agente-direct logs` | mostra as conversas acontecendo |
| `agente-direct editar produtos.md` | muda preço, link ou produto (reinicia sozinho) |
| `agente-direct verificar` | diz o que está funcionando e o que falta |
| `agente-direct configurar` | troca uma chave (o resto fica como está) |
| `agente-direct reiniciar` / `parar` | liga e desliga |
| `agente-direct atualizar` | baixa a versão nova, mantendo suas configurações e conversas |

## Como o agente se comporta

- **Fala como você.** Mensagens curtas, uma pergunta por vez, sem markdown.
- **Vende com BANT.** Descobre Necessidade, Momento, quem Decide e Orçamento ao longo
  da conversa. Quando há interesse, manda preço + link + uma pergunta.
- **Não inventa.** Só usa o que está em `produtos.md`. Se não sabe, pede para a pessoa
  aguardar e te avisa.
- **Você assume quando quiser.** Respondeu um lead pelo app do Instagram? O agente sai
  daquela conversa por 24 horas.
- **Não deixa ninguém no vácuo.** Se o Claude falhar ou a conversa ficar longa demais,
  o lead recebe "me dá um tempinho que eu te retorno" e você recebe o aviso.
- **É honesto.** Se perguntarem se é robô, ele diz que é seu assistente.
- **Um follow-up só.** Se o lead sumir, manda um toque cerca de 20 horas depois, entre
  8h e 21h. O Instagram não deixa mandar mensagem depois de 24 horas da última fala do
  lead, então não existe segundo toque.
- **Renova o token sozinho.** O token da Meta vence em 60 dias; o servidor renova toda
  semana.

## Freios (no arquivo `/opt/agente-direct/.env`)

| Variável | Para quê | Padrão |
|---|---|---|
| `SANDBOX` | fase de teste: só atende estes @, separados por vírgula | vazio (todos) |
| `BLOQUEADOS` | @ que o agente nunca atende (família, sócios, equipe) | vazio |
| `MAX_MSGS_SESSAO` | teto de mensagens do agente por conversa em 24 h | 15 |
| `PAUSA_HUMANO_HORAS` | quanto tempo ele fica fora depois que você responde | 24 |
| `FOLLOWUP_APOS_H` | horas até o follow-up | 20 |
| `ESFORCO` | `low` gasta menos, `high` pensa mais | `medium` |
| `MODELO` | modelo do Claude | `claude-opus-5-5` |
| `MODO_TESTE` | `1` = não envia nada ao Instagram, só mostra no log | `0` |

Depois de editar o `.env`, rode `agente-direct reiniciar`.

## Painel de leads

Cada conversa gera uma ficha com o BANT, o produto recomendado e um resumo. Consulte
com a senha `ADMIN_TOKEN` que está no `.env`:

```bash
curl -H "Authorization: Bearer SUA_SENHA" https://SEU_DOMINIO/leads
```

## Custo do Claude
Cada resposta é uma chamada ao Claude. O texto fixo (tom, produtos, método) fica em
cache, então o custo fica em poucos centavos de dólar por resposta. Para gastar menos,
use `ESFORCO=low` ou `MODELO=claude-sonnet-5-5`.

## Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `verificar` diz que o servidor não está no ar | domínio não aponta para o IP, ou portas 80/443 fechadas | confira o DNS e o firewall do provedor da VPS |
| Meta não aceita o webhook ("Verificar e salvar" falha) | token de verificação diferente | copie de novo o que o `conectar` mostrou |
| Mensagens das contas de teste chegam, de estranhos não | app em modo de desenvolvimento | publique o app (modo Ativo), veja o GUIA-META |
| Nada chega | acesso a mensagens desligado no app do Instagram | Configurações > Mensagens > Ferramentas conectadas > Permitir acesso |
| Agente parou de responder um lead | ele pediu para aguardar você | responda pelo app; 24 h depois ele volta |

## Para desenvolvedores

```bash
pip install -r requirements.txt pytest
python -m pytest -q
python -m agente_direct --help
```

Estrutura: `agente_direct/` (código), `modelos/conhecimento/` (modelo em branco),
`exemplos/` (conhecimento de exemplo), `instalar.sh` (instalador),
`docker-compose.yml` + `Caddyfile` (servidor com HTTPS automático).
