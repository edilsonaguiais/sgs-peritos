#!/usr/bin/env bash
# Instala o Agente Direct numa VPS Linux (Ubuntu ou Debian) com um comando:
#
#   curl -fsSL https://raw.githubusercontent.com/edilsonaguiais/sgs-peritos/claude/agente-direct-instagram/agente-direct/instalar.sh | sudo bash
#
# Para atualizar depois:   agente-direct atualizar
set -euo pipefail

REPO="${AGENTE_REPO:-edilsonaguiais/sgs-peritos}"
RAMO="${AGENTE_RAMO:-claude/agente-direct-instagram}"
SUBPASTA="${AGENTE_SUBPASTA:-agente-direct}"
PASTA="${AGENTE_PASTA:-/opt/agente-direct}"
URL_INSTALADOR="https://raw.githubusercontent.com/$REPO/$RAMO/$SUBPASTA/instalar.sh"
ATUALIZAR=0
[ "${1:-}" = "--atualizar" ] && ATUALIZAR=1

passo() { printf '\n\033[1m▶ %s\033[0m\n' "$1"; }
falha() { printf '\n\033[31m✖ %s\033[0m\n' "$1" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || falha "Rode como administrador: curl -fsSL $URL_INSTALADOR | sudo bash"
[ "$(uname -s)" = "Linux" ] || falha "Este instalador é para servidores Linux (Ubuntu ou Debian)."

passo "1/5 Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || falha "O Docker Compose não está disponível. Instale o pacote docker-compose-plugin."
echo "Docker pronto."

passo "2/5 Baixando o agente"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/$RAMO" | tar -xz -C "$tmp"
origem="$(find "$tmp" -mindepth 2 -maxdepth 2 -type d -name "$SUBPASTA" | head -n1)"
[ -n "$origem" ] || falha "Não achei a pasta $SUBPASTA no repositório $REPO ($RAMO)."
mkdir -p "$PASTA"
# .env, conhecimento/ e dados/ não vêm do repositório: suas configurações ficam intactas.
cp -a "$origem/." "$PASTA/"
cd "$PASTA"
touch .env && chmod 600 .env
mkdir -p dados conhecimento
echo "Arquivos em $PASTA."

passo "3/5 Comando agente-direct"
cat > /usr/local/bin/agente-direct <<WRAPPER
#!/usr/bin/env bash
# Atalho para controlar o Agente Direct instalado em $PASTA.
set -e
cd "$PASTA"
rodando() { [ -n "\$(docker compose ps -q --status running agente 2>/dev/null)" ]; }
python_no_agente() {
  if rodando; then docker compose exec agente python -m agente_direct "\$@"
  else docker compose run --rm agente python -m agente_direct "\$@"; fi
}
case "\${1:-ajuda}" in
  logs)       docker compose logs -f --tail 100 agente ;;
  reiniciar)  docker compose up -d --force-recreate ;;
  parar)      docker compose down ;;
  atualizar)  curl -fsSL "$URL_INSTALADOR" | sudo bash -s -- --atualizar ;;
  editar)     \${EDITOR:-nano} "conhecimento/\${2:-produtos.md}" && docker compose restart agente && echo "Agente reiniciado com o conhecimento novo." ;;
  configurar) python_no_agente configurar && docker compose up -d --force-recreate ;;
  ajuda|-h|--help)
    cat <<'AJUDA'
agente-direct configurar      pergunta e confere as chaves (Claude, Instagram, Telegram)
agente-direct conectar        liga o webhook da Meta à sua conta
agente-direct verificar       checklist do que está funcionando
agente-direct testar          conversa com o agente no terminal
agente-direct editar [arq]    edita conhecimento/produtos.md (ou tom_de_voz.md, metodo_bant.md)
agente-direct gerar-tom ARQ   rascunho do tom de voz a partir de conhecimento/ARQ
agente-direct logs            acompanha as conversas em tempo real
agente-direct reiniciar | parar | atualizar
AJUDA
    ;;
  *) python_no_agente "\$@" ;;
esac
WRAPPER
chmod +x /usr/local/bin/agente-direct
echo "Pronto: digite agente-direct para ver os comandos."

passo "4/5 Montando o agente"
docker compose build -q
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null && echo "Firewall: portas 80 e 443 liberadas."
fi

if [ "$ATUALIZAR" = 1 ]; then
  docker compose up -d --force-recreate
  printf '\n✅ Atualizado. Suas configurações e conversas foram mantidas.\n'
  exit 0
fi

passo "5/5 Configuração"
agente-direct configurar </dev/tty
docker compose up -d

dominio="$(grep -E '^DOMINIO=' .env | cut -d= -f2-)"
if [ -n "$dominio" ]; then
  printf 'Esperando o certificado HTTPS de %s ' "$dominio"
  for _ in $(seq 1 45); do
    curl -fsS -o /dev/null "https://$dominio/saude" 2>/dev/null && { echo " ok"; break; }
    printf '.'; sleep 2
  done
  echo
fi

agente-direct conectar </dev/tty || true

cat <<FIM

✅ Instalação concluída.

Agora:
  1. Escreva seu conhecimento:   agente-direct editar tom_de_voz.md
                                 agente-direct editar produtos.md
                                 agente-direct editar metodo_bant.md
  2. Converse com o agente:      agente-direct testar
  3. Confira tudo:               agente-direct verificar
  4. Acompanhe as conversas:     agente-direct logs
FIM
