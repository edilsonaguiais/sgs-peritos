# Roteiro para a próxima sessão (no computador do Edilson)

Você está numa sessão do Claude rodando no computador do Edilson. Diferente da sessão
anterior (na nuvem), aqui você tem acesso às credenciais dele e à VPS "edilson".

## Objetivo
Colocar no ar, na **VPS edilson**, o agente desta pasta (`agente-direct/`), atendendo o
direct do Instagram **@edilsonaguiais**, primeiro em fase de teste.

## O que já está pronto (não refazer)
- Código, testes (25 passando), instalador, Docker + Caddy: tudo nesta pasta, branch
  `claude/agente-direct-instagram` do repositório `edilsonaguiais/sgs-peritos`.
- Conhecimento do Edilson: `exemplos/edilson-aguiais/` (tom de voz, produtos com preços
  e links EduQ oficiais de 09–10/10/2026, método BANT). Use esse exemplo.
- Leia `README.md` e `GUIA-META.md` antes de começar.

## Regras
1. **Credenciais nunca aparecem no chat, em log ou em commit.** Procure, use e grave
   direto no `.env` da VPS (permissão 600). Ao relatar, mostre só os 4 últimos caracteres.
2. **Fase de teste:** `SANDBOX` com uma conta de teste do Edilson (pergunte qual @).
   O agente só responde a ela. **Não tire o SANDBOX sem o Edilson autorizar** depois de
   ler as conversas de teste.
3. Antes de qualquer coisa que mude a VPS (instalar Docker, abrir portas, mexer em
   Caddy/Nginx já existente), mostre o plano e espere o "ok".
4. Se a VPS já roda outra coisa nas portas 80/443 (Caddy, Nginx, Traefik), **não
   derrube**: use o proxy que já existe para encaminhar o subdomínio do agente para a
   porta do container, em vez do Caddy do `docker-compose.yml`.

## Passo a passo
1. **Achar as credenciais** no computador (sem imprimir):
   - Meta/Instagram: token de acesso da conta @edilsonaguiais e chave secreta do app
     do Instagram (32 caracteres hexadecimais). Se não existir app da Meta ainda, pare
     e guie o Edilson pelo `GUIA-META.md`.
   - Chave da API do Claude (`sk-ant-...`).
   - Opcional: token de bot do Telegram para os avisos.
   - Confira o token: `GET https://graph.instagram.com/v23.0/me?fields=user_id,username`
     tem que devolver `username = edilsonaguiais`.
2. **Acesso à VPS:** confirme como o Edilson entra na VPS edilson (alias no
   `~/.ssh/config`, IP, usuário). Teste com `ssh <vps> 'uname -a && docker --version'`.
   Veja o que já roda nas portas 80/443.
3. **Endereço:** pergunte qual subdomínio usar (sugestão: `direct.<domínio dele>`
   apontando para o IP da VPS). Sem domínio, use `<ip-com-hifens>.sslip.io`.
4. **Instalar:** na VPS, rode o instalador com terminal interativo:
   ```bash
   ssh -t <vps> 'curl -fsSL https://raw.githubusercontent.com/edilsonaguiais/sgs-peritos/claude/agente-direct-instagram/agente-direct/instalar.sh | sudo bash'
   ```
   No passo "Conhecimento", escolha o exemplo `edilson-aguiais`. Se preferir não usar
   o assistente interativo, copie a pasta para `/opt/agente-direct`, escreva o `.env`
   direto (campos em `agente_direct/__main__.py`, lista `ORDEM_ENV`), copie
   `exemplos/edilson-aguiais/*.md` para `conhecimento/` e rode
   `docker compose up -d --build`.
   No `.env`, inclua: `DONO_NOME=Edilson Aguiais` e `SANDBOX=<@ de teste>`.
5. **Painel da Meta:** o `agente-direct conectar` mostra a URL de callback e o token de
   verificação. Peça ao Edilson para colar em Instagram > Configuração da API com login
   do Instagram > Configurar webhooks, ativar `messages`, colocar
   `https://<endereço>/privacidade` como política de privacidade e publicar o app
   (modo Ativo). Depois rode o `conectar` de novo até a inscrição dar certo.
6. **Conferir:** `sudo agente-direct verificar` tem que dar tudo ✅.
7. **Teste real:** o Edilson manda uma DM da conta de teste para @edilsonaguiais.
   Acompanhe com `sudo agente-direct logs`. Teste: pergunta de preço do ONE, pedido de
   desconto (tem que pedir para aguardar e avisar), recusa, áudio.
8. **Relatório:** mostre as conversas de teste e pergunte se pode tirar o SANDBOX.

## Pendências que o Edilson pediu e ficaram para depois
- Criar o repositório público `edilsonaguiais/agente-instagram` e mover este kit para a
  raiz dele (o `instalar.sh` já aceita `AGENTE_SUBPASTA=""`); atualizar os links do
  README e do instalador para `.../agente-instagram/main/instalar.sh`. Perguntar qual
  licença usar (MIT ou nenhuma).
- Garantias da Águias e da AutorIA seguem bloqueadas até ele conferir os contratos
  (o agente pede para aguardar).
