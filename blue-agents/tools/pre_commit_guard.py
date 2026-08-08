#!/usr/bin/env python3
"""Barra o commit que varre o que não devia, e diz em que branch você está.

Dois erros reais de 2026-08-08, os dois evitáveis por um aviso:

1. Um `git add -A` levou junto trabalho de outra pessoa que estava sem
   versionar — e dentro dele uma ROM de 1 MB, contra a regra 1 do AGENTS.md.
   Só apareceu porque alguém leu o `git show --stat` depois.
2. Uma sessão inteira de commits foi para `feat/rom-fast-blue` em vez do
   `master`, porque ninguém conferiu a branch antes de commitar.

O guarda não decide nada sozinho: bloqueia o que é quase sempre engano e
imprime, alto, o que está prestes a acontecer.

Instalar:

    ../.venv/bin/python tools/pre_commit_guard.py --install

Pular uma vez, quando o commit é mesmo intencional:

    POKEAI_ALLOW_BIG=1 git commit ...

Desinstalar:

    rm .git/hooks/pre-commit
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = PROJECT_ROOT / ".git" / "hooks" / "pre-commit"
OVERRIDE = "POKEAI_ALLOW_BIG"

# Acima disto é quase sempre binário entrando sem querer. A ROM tem 1 MB.
BIG_FILE_BYTES = 512 * 1024
# Extensões que nunca entram por acidente sem alguém reparar depois.
GUARDED_SUFFIXES = {".gb", ".gbc", ".state", ".sav", ".zip", ".png", ".mp4"}

HOOK_SOURCE = """#!/bin/sh
# Instalado por blue-agents/tools/pre_commit_guard.py
exec "{python}" "{guard}" --check
"""


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True
    ).stdout.strip()


def staged_files():
    saida = _git("diff", "--cached", "--name-only", "--diff-filter=ACM")
    return [linha for linha in saida.splitlines() if linha]


def check():
    """0 se o commit pode seguir, 1 se deve parar."""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "?"
    arquivos = staged_files()
    if not arquivos:
        return 0

    print(f"\n  branch: {branch}   ({len(arquivos)} arquivo(s) no commit)")

    if os.getenv(OVERRIDE) == "1":
        print(f"  {OVERRIDE}=1 — guarda desligado para este commit\n")
        return 0

    suspeitos = []
    for nome in arquivos:
        caminho = PROJECT_ROOT / nome
        try:
            tamanho = caminho.stat().st_size
        except OSError:
            continue
        grande = tamanho >= BIG_FILE_BYTES
        guardado = caminho.suffix.lower() in GUARDED_SUFFIXES
        if grande or guardado:
            suspeitos.append((nome, tamanho, grande, guardado))

    if not suspeitos:
        print()
        return 0

    print("\n  COMMIT BARRADO — arquivos que raramente entram de propósito:\n")
    for nome, tamanho, grande, guardado in suspeitos:
        motivos = []
        if grande:
            motivos.append(f"{tamanho/1024:.0f} KB")
        if guardado:
            motivos.append(f"extensão {Path(nome).suffix}")
        print(f"    {nome}  ({', '.join(motivos)})")
    print(
        "\n  Se for intencional:\n"
        f"    {OVERRIDE}=1 git commit ...\n"
        "\n  Se não for, provavelmente foi `git add -A`. Prefira caminhos\n"
        "  explícitos: git add <arquivo> <arquivo>\n"
    )
    return 1


def install():
    if not (PROJECT_ROOT / ".git").is_dir():
        print("Não é um repositório git.", file=sys.stderr)
        return 1
    HOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOOK_PATH.write_text(
        HOOK_SOURCE.format(python=sys.executable, guard=Path(__file__).resolve()),
        encoding="utf-8",
    )
    HOOK_PATH.chmod(0o755)
    print(f"instalado em {HOOK_PATH.relative_to(PROJECT_ROOT)}")
    print("desinstalar: rm .git/hooks/pre-commit")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.install:
        return install()
    if args.check:
        return check()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
