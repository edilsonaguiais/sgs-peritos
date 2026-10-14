# Agente Direct — vendas no Instagram com BANT

Agente que atende o direct do Instagram do Edilson Aguiais com o tom de voz dele,
qualifica o lead pelo método BANT e vende o produto certo para o perfil:
**Mentoria Águias da Perícia**, **Águias One** ou **AutorIA 10X**.

A conexão é a **oficial da Meta** (Instagram API com login do Instagram, webhooks
e Send API). Não usa senha, automação de navegador nem ferramenta não oficial, então
não coloca a conta em risco de bloqueio.

## Como funciona

```
Lead manda DM ──► Meta (webhook) ──► /webhook deste servidor
                                         │ espera ~8 s o lead terminar de digitar
                                         ▼
                              Claude lê: tom de voz + produtos + BANT + conversa
                                         │
                       ┌─────────────────┴──────────────────┐
                       ▼                                    ▼
          responde no direct (1 a 3 balões)     atualiza a ficha BANT do lead
                                                 e, se for hora, passa para humano
```

- **Tom de voz, produtos e método** ficam em `conhecimento/` como texto simples. Para
  mudar o que o agente fala, edite esses arquivos e reinicie. Não precisa mexer em código.
- **Você assume quando quiser.** Se você responder um lead pelo app do Instagram, o
  agente percebe e sai daquela conversa por 24 h (`PAUSA_HUMANO_HORAS`).
- **O próprio agente fecha.** Com interesse, ele manda preço + link da EduQ + uma
  pergunta, como no método Damásio. Não segura o link nem força call.
- **Transferência para humano.** Quando o lead pede desconto ou a garantia do Águias,
  quer falar com você, é aluno com problema, ou pergunta algo que não está em
  `produtos.md`, o agente faz a ponte, para de responder e avisa em `NOTIFICAR_URL`
  (Make, Zapier, n8n ou Slack).
- **Ficha do lead.** A cada resposta o agente grava a situação de Budget, Authority,
  Need e Timing, o perfil, o produto recomendado, o estágio e um resumo para o time.
  Consulte em `GET /leads`.
- **Honestidade.** Se perguntarem se é robô, ele não nega: diz que é o assistente do
  Edilson e oferece chamar alguém.

## De onde vêm preço, links e regras

`conhecimento/produtos.md` foi montado a partir dos repositórios de vendas
(`mentoria-aguias-one/vendas`, `mentoria-aguias-da-pericia/vendas`,
`unibcappa-produtos/mentoria/02-autoria-10x`), que espelham o Dropbox. Os dados
vigentes em 14/10/2026 são estes:

| Produto | Preço no direct (fora do evento) | Matrícula EduQ |
|---|---|---|
| Águias ONE | 12x R$ 1.500 ou R$ 15.000 | https://go.eduq.tec.br/r/8df263aed54d460 (processo 232) |
| Águias da Perícia | 12x R$ 4.000 ou R$ 45.000 | https://go.eduq.tec.br/r/8df26455d32e839 (processo 237) |
| AutorIA 10X Autor Digital | R$ 2.996,40 | https://inscricao.eduqtecnologia.com.br/detalhes/218?dominio=ibcappa |
| AutorIA 10X Legado Profissional | R$ 5.964,00 | https://inscricao.eduqtecnologia.com.br/detalhes/219?dominio=ibcappa |
| AutorIA 10X Autoridade Black | R$ 17.964,00 (passa pelo time) | https://inscricao.eduqtecnologia.com.br/detalhes/220?dominio=ibcappa |

O agente também segue as regras dos playbooks: método Damásio (com interesse, manda
preço + link + uma pergunta), preço do III Encontro nunca no direct, parcelado
primeiro, sem desconto, "mentoria que certifica como pós-graduação" (nunca "é uma
pós", nunca "MEC"), garantia do Águias bloqueada até conferir o contrato.

**Quando o preço ou o link mudar, mude `produtos.md` e reinicie.** O agente só
consegue enviar links que estão nesse arquivo. Qualquer outro link, inclusive os de
preço de evento, é bloqueado antes de sair, e a conversa vai para o time.

## Freios

| Freio | Variável | Padrão |
|---|---|---|
| Agrupa mensagens quebradas do lead | `ESPERA_AGRUPAR_S` | 8 s |
| Sai da conversa quando você responde pelo app | `PAUSA_HUMANO_HORAS` | 24 h |
| Teto de mensagens do agente por conversa em 24 h (no teto, passa para o time) | `MAX_MSGS_SESSAO` | 15 |
| Pessoas que o agente nunca atende (sócios, família, equipe) | `BLOQUEADOS` | vazio |
| Fase de teste: só atende estes @ | `SANDBOX` | vazio (todos) |
| Um follow-up (copy do `/sumiu1`) se o lead sumir, dentro da janela de 24 h, entre 8h e 21h | `FOLLOWUP_APOS_H` | 20 h |
| Sem travessão e sem link fora da lista | (sempre ligado) | |

O Instagram só entrega mensagem até 24 h depois da última fala do lead. Por isso o
`/sumiu2` do playbook (dia 3) não existe no direct: o agente faz um único toque.

> **Atenção, Sofia:** a Sofia (SellFlux, política 40838) já vende o ONE. Se ela
> estiver ligada ao mesmo Instagram, desligue um dos dois nesse canal. Dois agentes
> na mesma caixa respondem em dobro.

## Passo a passo da conexão oficial

### 1. Conta do Instagram
A conta precisa ser **profissional** (Empresa ou Criador de conteúdo). No app do
Instagram: *Configurações → Mensagens e respostas a stories → Controles de mensagens
→ Ferramentas conectadas → Permitir acesso a mensagens* (ative).

### 2. App na Meta
1. Em <https://developers.facebook.com/apps>, clique em **Criar app** e escolha o tipo
   **Empresa**.
2. Adicione o produto **Instagram** e abra **Configuração da API com login do Instagram**.
3. Em **Gerar tokens de acesso**, adicione a sua conta e faça login. Copie:
   - o **token** → `IG_ACCESS_TOKEN`;
   - o **ID da conta do Instagram** → `IG_USER_ID`.
4. Na mesma tela, copie a **Chave secreta do app do Instagram** → `IG_APP_SECRET`.

### 3. Servidor no ar (HTTPS)
A Meta só entrega mensagens a uma URL pública com HTTPS. Qualquer uma destas opções
serve: Render, Railway, Fly.io ou uma VPS.

```bash
cd agente-direct
cp .env.example .env        # preencha as chaves
pip install -r requirements.txt
uvicorn agente_direct.app:app --host 0.0.0.0 --port 8000 --workers 1
```

Ou com Docker: `docker build -t agente-direct . && docker run --env-file .env -p 8000:8000 -v $PWD/dados:/app/dados agente-direct`

> Use **um worker só** (`--workers 1`). O agrupamento das mensagens fica na memória do processo.

### 4. Webhook
No painel do app, em **Configurar webhooks**:
- **URL de callback:** `https://SEU-DOMINIO/webhook`
- **Token de verificação:** o mesmo texto que você colocou em `IG_VERIFY_TOKEN`
- Clique em **Verificar e salvar** e depois assine o campo **messages**.

### 5. Teste em modo desenvolvimento
Com o app em modo desenvolvimento, o agente só responde contas que têm função no app
(*Funções do app → Testadores do Instagram*). Coloque essas contas em `SANDBOX`, mande
uma DM e acompanhe o log. Para testar sem enviar nada de verdade, use `MODO_TESTE=1`.
Antes de abrir para todos, leia 10 conversas de teste e só libere se você assinaria
todas as respostas.

### 6. Liberar para todos os leads (App Review)
Para atender qualquer pessoa, a Meta exige:
1. **Verificação da empresa** (Business Manager);
2. **URL da política de privacidade** nas configurações do app;
3. **Análise do app** pedindo *acesso avançado* para `instagram_business_basic` e
   `instagram_business_manage_messages`, com um vídeo curto mostrando o agente
   respondendo uma DM;
4. Depois da aprovação, mudar o app para o modo **Ativo**.

A aprovação costuma levar de alguns dias a algumas semanas.

### 7. Renovar o token
O token vale 60 dias. Rode todo mês e atualize `IG_ACCESS_TOKEN`:
```bash
python -m agente_direct.renovar_token
```

## Testar o agente sem o Instagram

Converse com ele no terminal. Isso só precisa de `ANTHROPIC_API_KEY` no `.env`:
```bash
python -m agente_direct.simular
```
Faça o papel de leads diferentes, como um perito iniciante, um perito que fatura
R$ 15 mil por mês, um contador que quer escrever um livro ou alguém que só pergunta
o preço. Ajuste `conhecimento/` até o tom ficar do seu jeito.

## Consultar e controlar os leads

Todas as rotas pedem o cabeçalho `Authorization: Bearer <ADMIN_TOKEN>`.

| Rota | O que faz |
|---|---|
| `GET /leads` | Lista os leads com a ficha BANT e o produto recomendado |
| `GET /leads/{id}` | Mostra um lead com o histórico completo |
| `POST /leads/{id}/pausar?horas=N` | Tira o agente da conversa |
| `POST /leads/{id}/retomar` | Devolve a conversa ao agente depois de uma transferência |

## Regras da Meta que o agente já respeita
- Só responde dentro da **janela de 24 h** depois da última mensagem do lead. Ele
  responde sempre a uma mensagem recebida, então nunca inicia conversa.
- Cada mensagem tem até 1000 caracteres. As mais longas são quebradas automaticamente.
- Áudios, imagens e respostas a stories chegam como descrição, e o agente pede que a
  pessoa escreva o principal.

## Custo
Cada resposta é uma chamada ao Claude (`claude-opus-5-5`, esforço `medium`). O prompt
fixo fica em cache, então o custo fica em poucos centavos de dólar por resposta. Para
gastar menos, use `ESFORCO=low` ou `MODELO=claude-sonnet-5-5`.

## Desenvolvimento
```bash
pip install -r requirements.txt pytest
python -m pytest -q
```
