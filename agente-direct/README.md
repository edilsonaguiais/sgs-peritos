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
- **Transferência para humano.** Quando o lead está pronto para fechar, pede desconto,
  quer falar com você, é aluno com problema, ou pergunta algo que não está em
  `produtos.md`, o agente faz a ponte, para de responder e avisa em `NOTIFICAR_URL`
  (Make, Zapier, n8n ou Slack).
- **Ficha do lead.** A cada resposta o agente grava a situação de Budget, Authority,
  Need e Timing, o perfil, o produto recomendado, o estágio e um resumo para o time.
  Consulte em `GET /leads`.
- **Honestidade.** Se perguntarem se é robô, ele não nega: diz que é o assistente do
  Edilson e oferece chamar alguém.

## Antes de ligar: complete `conhecimento/produtos.md`

Tirei preço, público e formato da Águias e da AutorIA 10X dos documentos do seu Drive.
Ficaram marcados com **[PREENCHER]**:

- **Águias One**: não há nenhum documento sobre ela no Drive. Falta tudo: promessa,
  público, formato, preço e link.
- **AutorIA 10X**: falta o preço e o link de compra.
- **Águias da Perícia**: falta o link de aplicação ou de pagamento.

Enquanto um dado estiver como [PREENCHER], o agente não o cita e transfere para o time.

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
(*Funções do app → Testadores do Instagram*). Mande uma DM de uma conta testadora e
acompanhe o log. Para testar sem enviar nada de verdade, use `MODO_TESTE=1`.

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
