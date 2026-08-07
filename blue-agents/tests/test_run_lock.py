"""Uma corrida por vez, e a trava não pode prender o projeto.

Duas corridas escrevem nos mesmos `trainers/` e se sobrescrevem. Mas a máquina
mata processo por falta de memória sem rastro, então uma trava que sobrevive ao
dono morto trocaria um problema por outro.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

AGENTS_ROOT = str(Path(__file__).resolve().parents[1])
if AGENTS_ROOT not in sys.path:
    sys.path.append(AGENTS_ROOT)

from run_lock import RunLock, RunLockBusy


class RunLockTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "journey.lock"

    def escrever_trava(self, pid):
        self.path.write_text(
            json.dumps({"pid": pid, "started_at": 0, "label": "teste"}),
            encoding="utf-8",
        )

    def test_livre_por_padrao(self):
        self.assertIsNone(RunLock(self.path).owner())

    def test_tomar_registra_o_dono(self):
        RunLock(self.path, label="2 slots").acquire()
        dono = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(os.getpid(), dono["pid"])
        self.assertEqual("2 slots", dono["label"])

    def test_segunda_corrida_e_recusada_com_o_pid(self):
        RunLock(self.path).acquire()
        # Um PID que não é o nosso, mas que existe: o processo pai.
        self.escrever_trava(os.getppid())
        with self.assertRaises(RunLockBusy) as erro:
            RunLock(self.path).acquire()
        self.assertEqual(os.getppid(), erro.exception.pid)
        self.assertIn("kill", str(erro.exception))

    def test_trava_de_processo_morto_e_assumida(self):
        # SIGKILL por falta de memória não pode trancar o projeto até alguém
        # apagar um arquivo à mão.
        self.escrever_trava(pid=999_999)
        self.assertIsNone(RunLock(self.path).owner())
        RunLock(self.path).acquire()
        self.assertEqual(
            os.getpid(),
            json.loads(self.path.read_text(encoding="utf-8"))["pid"],
        )

    def test_trava_ilegivel_nao_trava_nada(self):
        self.path.write_text("{lixo", encoding="utf-8")
        self.assertIsNone(RunLock(self.path).owner())
        RunLock(self.path).acquire()

    def test_soltar_apaga(self):
        lock = RunLock(self.path).acquire()
        lock.release()
        self.assertFalse(self.path.exists())

    def test_nunca_solta_a_trava_de_outro(self):
        lock = RunLock(self.path).acquire()
        self.escrever_trava(os.getppid())
        lock.release()
        self.assertTrue(self.path.exists(), "a trava do outro continua de pé")

    def test_o_mesmo_processo_pode_retomar_a_propria_trava(self):
        RunLock(self.path).acquire()
        RunLock(self.path).acquire()

    def test_serve_como_context_manager(self):
        with RunLock(self.path):
            self.assertIsNotNone(RunLock(self.path).owner())
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
