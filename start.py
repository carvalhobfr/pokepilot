#!/usr/bin/env python3
"""PokeAI 2026 — inicializador único para Windows, macOS e Linux.

Substitui os scripts .sh, que só funcionavam em Unix: valida a ROM, prepara o
ambiente na primeira execução, sobe o relay WebSocket, o dashboard e as
jornadas, e abre o navegador. Ctrl+C encerra e os bots salvam o progresso.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

ROOT = Path(__file__).resolve().parent
AGENTS = ROOT / "blue-agents"
DASHBOARD = AGENTS / "dashboard-react"
IS_WINDOWS = os.name == "nt"

ROM = ROOT / "roms" / "PokemonBlue.gb"
ROM_SHA1 = "d7037c83e1ae5b39bde3c30787637ba1d4c48ce2"
DASHBOARD_URL = "http://localhost:5173"


def say(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def fail(message: str) -> None:
    print(f"\n[ERRO] {message}\n", flush=True)
    if IS_WINDOWS:
        input("Enter para fechar...")
    raise SystemExit(1)


def venv_python() -> Path:
    """Interpreters live in different folders on Windows and Unix."""
    return ROOT / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / (
        "python.exe" if IS_WINDOWS else "python"
    )


def check_rom() -> None:
    say("Conferindo a ROM")
    if not ROM.is_file():
        fail(
            f"ROM não encontrada em {ROM}\n\n"
            "Pokémon Blue é software comercial e não vem no repositório.\n"
            "Coloque a sua cópia legal nesse caminho e rode de novo.\n"
            f"SHA-1 esperado: {ROM_SHA1}"
        )
    digest = hashlib.sha1(ROM.read_bytes()).hexdigest()
    if digest != ROM_SHA1:
        fail(
            f"A ROM em {ROM} não é a esperada.\n"
            f"  esperado: {ROM_SHA1}\n"
            f"  recebido: {digest}\n"
            "O projeto exige Pokémon Blue original — nem Red, nem hack."
        )
    print("ROM válida.")


def ensure_python_env() -> Path:
    say("Preparando o ambiente Python")
    python = venv_python()
    if not python.is_file():
        print("Primeira execução: criando .venv (demora alguns minutos)...")
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True)
        python = venv_python()
    probe = subprocess.run(
        [str(python), "-c", "import pyboy, stable_baselines3"],
        capture_output=True,
    )
    if probe.returncode != 0:
        print("Instalando dependências Python...")
        subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run(
            [str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements-local.txt")],
            check=True,
        )
    print("Python pronto.")
    return python


def ensure_dashboard() -> str:
    say("Preparando o dashboard")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        fail(
            "Node.js não encontrado.\n"
            "Windows: instale em https://nodejs.org (versão LTS).\n"
            "macOS:   brew install node"
        )
    if not (DASHBOARD / "node_modules").is_dir():
        print("Primeira execução: instalando pacotes do dashboard...")
        subprocess.run([npm, "install"], cwd=DASHBOARD, check=True)
    print("Dashboard pronto.")
    return npm


def free_port(port: int) -> None:
    """Best-effort: nobody should be holding the port from a previous run."""
    try:
        if IS_WINDOWS:
            output = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True
            ).stdout
            for line in output.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    pid = line.split()[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        else:
            pids = subprocess.run(
                ["lsof", "-ti", f":{port}"], capture_output=True, text=True
            ).stdout.split()
            for pid in pids:
                subprocess.run(["kill", "-9", pid], capture_output=True)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--slots", type=int, default=2,
                        help="Bots simultâneos (2 é o seguro para laptops sem ventoinha)")
    args = parser.parse_args()

    print("\n  PokeAI 2026 — bots jogando Pokémon Blue de verdade\n")

    check_rom()
    python = ensure_python_env()
    npm = ensure_dashboard()

    say("Iniciando")
    for port in (5173, 3344):
        free_port(port)

    environment = dict(os.environ)
    environment.setdefault("POKEAI_TORCH_THREADS", "2")
    environment.setdefault("POKEAI_STREAM_INTERVAL", "10")
    environment.setdefault("MPLCONFIGDIR", str(AGENTS / "tasks" / "matplotlib"))
    (AGENTS / "tasks" / "matplotlib").mkdir(parents=True, exist_ok=True)

    processes: list[subprocess.Popen] = []

    def spawn(command, cwd, name):
        try:
            process = subprocess.Popen(command, cwd=cwd, env=environment)
        except FileNotFoundError:
            fail(f"Não consegui iniciar {name}: comando não encontrado ({command[0]}).")
        processes.append(process)
        return process

    spawn(["node", "viz_server/ws_relay.js"], AGENTS, "relay WebSocket")
    time.sleep(1)
    spawn([npm, "run", "dev", "--", "--host", "127.0.0.1"], DASHBOARD, "dashboard")

    if not args.no_browser:
        threading.Timer(8.0, lambda: webbrowser.open(DASHBOARD_URL)).start()

    print(f"\n  Dashboard: {DASHBOARD_URL}")
    print("  Ctrl+C encerra e salva o progresso dos bots.")
    print("\n  Na tela: arrastar move o mapa, roda/pinça dá zoom,")
    print("  clicar num bot trava a câmera nele.\n")

    journeys = spawn(
        [str(python), "run_journeys.py",
         "--slots", str(args.slots),
         "--state-update-interval", "50"],
        AGENTS,
        "supervisor de jornadas",
    )

    # The relay pauses and saves by signalling this pid; without the file its
    # buttons fail silently.
    pid_file = AGENTS / "tasks" / "training.pid"
    pid_file.write_text(str(journeys.pid), encoding="utf-8")

    try:
        journeys.wait()
    except KeyboardInterrupt:
        print("\nEncerrando e salvando...")
        # The supervisor persists both slots when it receives a terminate.
        journeys.terminate()
        try:
            journeys.wait(timeout=45)
        except subprocess.TimeoutExpired:
            journeys.kill()
    finally:
        pid_file.unlink(missing_ok=True)
        for process in processes:
            if process.poll() is None:
                process.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
