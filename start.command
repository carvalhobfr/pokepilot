#!/bin/bash
# PokeAI 2026 — clique duplo para rodar no macOS.
cd "$(dirname "$0")"
command -v python3 >/dev/null || {
  echo "[ERRO] python3 não encontrado. Instale o Python 3.11+."
  read -r -p "Enter para fechar..."; exit 1
}
python3 start.py "$@"
read -r -p "Encerrado. Enter para fechar..."
