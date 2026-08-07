"""Uma corrida por vez, imposta pelo disco em vez de lembrada.

Duas corridas ao mesmo tempo não competem só por CPU: as duas escrevem em
`trainers/<AGENTE>/` e em `knowledge/`, e uma sobrescreve o save da outra. Em
2026-08-06 isso aconteceu três vezes, e o operador ainda matou a corrida certa
duas vezes achando que era processo órfão — o problema nunca foi quem digitou o
comando, era corrida invisível.

A trava guarda o PID. Se o dono morreu, ela é considerada abandonada e a nova
corrida assume: um `SIGKILL` por falta de memória não pode deixar o projeto
trancado até alguém apagar um arquivo à mão.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import time


class RunLockBusy(RuntimeError):
    """Já existe uma corrida viva. Traz o PID para o operador poder matá-la."""

    def __init__(self, pid, started_at, path):
        self.pid = pid
        self.started_at = started_at
        self.path = path
        idade = ""
        if started_at:
            minutos = max(int((time.time() - started_at) // 60), 0)
            idade = f", viva há {minutos} min"
        super().__init__(
            f"Já há uma corrida rodando (PID {pid}{idade}).\n"
            f"  trava: {path}\n"
            f"  para encerrar: kill {pid}\n"
            "Duas corridas escrevem nos mesmos trainers/ e se sobrescrevem."
        )


def _process_alive(pid):
    """O dono da trava ainda existe?

    `os.kill(pid, 0)` não envia sinal nenhum: só pergunta. `ESRCH` é "não
    existe"; `EPERM` é "existe e é de outro usuário", que para o nosso caso
    conta como vivo.
    """
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (ValueError, TypeError, OSError):
        return False
    return True


class RunLock:
    """Trava de corrida com dono identificado e liberação automática."""

    def __init__(self, path, label=""):
        self.path = Path(path)
        self.label = str(label)
        self.acquired = False

    def _read(self):
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def owner(self):
        """Quem tem a trava agora, ou ``None`` se está livre ou abandonada."""
        payload = self._read()
        if not isinstance(payload, dict):
            return None
        pid = payload.get("pid")
        if pid is None or not _process_alive(pid):
            return None
        return payload

    def acquire(self):
        """Tomar a trava, ou levantar ``RunLockBusy`` dizendo quem a tem."""
        current = self.owner()
        if current is not None and int(current.get("pid", -1)) != os.getpid():
            raise RunLockBusy(
                current.get("pid"), current.get("started_at"), self.path
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump({
                "pid": os.getpid(),
                "started_at": time.time(),
                "label": self.label,
            }, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
        self.acquired = True
        return self

    def release(self):
        """Soltar, mas só se ainda for nossa — nunca a trava de outro."""
        if not self.acquired:
            return
        payload = self._read()
        if isinstance(payload, dict) and int(payload.get("pid", -1)) != os.getpid():
            self.acquired = False
            return
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass
        self.acquired = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_exception):
        self.release()
        return False
