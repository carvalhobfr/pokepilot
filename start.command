#!/bin/bash
# PokeAI 2026 — abre tudo com um clique duplo (macOS).
# Prepara o ambiente na primeira execução, sobe o dashboard e as jornadas,
# e abre o navegador. Ctrl+C encerra e salva o progresso dos bots.

set -u
cd "$(dirname "$0")"
ROOT="$(pwd)"

BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; OFF=$'\033[0m'
step() { printf "\n%s==> %s%s\n" "$BOLD" "$1" "$OFF"; }
fail() { printf "\n%s✗ %s%s\n\n" "$RED" "$1" "$OFF"; read -r -p "Enter para fechar..."; exit 1; }

printf "%s\n" "$BOLD"
printf "  PokeAI 2026 — dois bots jogando Pokémon Blue de verdade\n"
printf "%s\n" "$OFF"

# --- 1. ROM ---------------------------------------------------------------
step "Conferindo a ROM"
ROM="roms/PokemonBlue.gb"
EXPECTED="d7037c83e1ae5b39bde3c30787637ba1d4c48ce2"
if [ ! -f "$ROM" ]; then
  fail "ROM não encontrada em $ROOT/$ROM

Pokémon Blue é software comercial e não vem no repositório.
Coloque sua própria cópia legal nesse caminho e rode de novo.
SHA-1 esperado: $EXPECTED"
fi
ACTUAL="$(shasum "$ROM" | cut -d' ' -f1)"
if [ "$ACTUAL" != "$EXPECTED" ]; then
  fail "A ROM em $ROM não é a esperada.
  esperado: $EXPECTED
  recebido: $ACTUAL
O projeto exige Pokémon Blue (revisão original, não Red nem hack)."
fi
printf "%s✓ ROM válida%s\n" "$GREEN" "$OFF"

# --- 2. Python ------------------------------------------------------------
step "Preparando o ambiente Python"
command -v python3 >/dev/null || fail "python3 não encontrado. Instale o Python 3.11+."
if [ ! -x ".venv/bin/python" ]; then
  printf "%sPrimeira execução: criando .venv (demora alguns minutos)%s\n" "$YELLOW" "$OFF"
  python3 -m venv .venv || fail "Falha ao criar o ambiente virtual."
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements-local.txt || fail "Falha ao instalar dependências Python."
fi
.venv/bin/python -c "import pyboy" 2>/dev/null || {
  printf "%sInstalando dependências que faltavam%s\n" "$YELLOW" "$OFF"
  .venv/bin/pip install --quiet -r requirements-local.txt || fail "Falha ao instalar dependências Python."
}
printf "%s✓ Python pronto%s\n" "$GREEN" "$OFF"

# --- 3. Dashboard ---------------------------------------------------------
step "Preparando o dashboard"
command -v node >/dev/null || fail "Node.js não encontrado. Instale com: brew install node"
if [ ! -d "blue-agents/dashboard-react/node_modules" ]; then
  printf "%sPrimeira execução: instalando pacotes do dashboard%s\n" "$YELLOW" "$OFF"
  (cd blue-agents/dashboard-react && npm install --silent) || fail "Falha no npm install."
fi
printf "%s✓ Dashboard pronto%s\n" "$GREEN" "$OFF"

# --- 4. Subir -------------------------------------------------------------
step "Iniciando"
lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null
lsof -ti:3344 2>/dev/null | xargs kill -9 2>/dev/null

( sleep 8; open "http://localhost:5173" ) &

printf "\n  Dashboard: %shttp://localhost:5173%s\n" "$BOLD" "$OFF"
printf "  Ctrl+C encerra e salva o progresso.\n\n"
printf "  Na tela: arrastar move o mapa, roda/pinça dá zoom,\n"
printf "  clicar num bot trava a câmera nele.\n\n"

POKEAI_TORCH_THREADS=2 POKEAI_STREAM_INTERVAL=10 \
  ./blue-agents/run_all.sh --journeys --state-update-interval 50

read -r -p "Encerrado. Enter para fechar..."
