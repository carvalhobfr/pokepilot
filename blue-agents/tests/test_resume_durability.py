"""Matar o processo no meio da gravação não pode custar a jornada.

A ordem antiga era: renomeia `current.state`, depois renomeia o manifesto.
Morrer **entre os dois** deixava o estado novo com o manifesto velho, o sha256
não batia, a retomada era recusada, e o emulador caía no estado de partida.
CARON perdeu a jornada assim duas vezes num dia.

Agora o estado vai para um arquivo cujo nome vem do próprio conteúdo, e o
manifesto é o único ponto de commit: enquanto ele não troca, o par antigo
continua inteiro.
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

AGENTS_ROOT = str(Path(__file__).resolve().parents[1])
if AGENTS_ROOT not in sys.path:
    sys.path.append(AGENTS_ROOT)

from hybrid_agent import CURRENT_STATE_MANIFEST, HybridGymEnv


class ResumeDurabilityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.trainer = Path(self.directory.name)

    def env(self, generation=1):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.agent_name = "AARON"
        env.trainer_dir = self.trainer
        env.checkpoint_generation = generation
        env.checkpoint_dir = self.trainer / "checkpoints"
        env.checkpoint_dir.mkdir(exist_ok=True)
        return env

    def manifesto(self):
        return json.loads(
            (self.trainer / CURRENT_STATE_MANIFEST).read_text(encoding="utf-8")
        )

    def test_o_manifesto_nomeia_um_arquivo_pelo_conteudo(self):
        env = self.env()
        env._commit_resume_state("session_end", b"jornada-A")
        manifesto = self.manifesto()
        self.assertTrue(manifesto["state"].startswith("resume-"))
        self.assertEqual(hashlib.sha256(b"jornada-A").hexdigest(), manifesto["sha256"])
        self.assertTrue((self.trainer / manifesto["state"]).exists())

    def test_o_par_antigo_sobrevive_ate_o_manifesto_trocar(self):
        # O cenário real: o estado novo já está em disco e o processo morre
        # antes do manifesto. O antigo tem de continuar carregável.
        env = self.env()
        env._commit_resume_state("primeiro", b"jornada-A")
        antigo = self.manifesto()

        # Simula a morte: o estado novo entra, o manifesto não.
        novo = self.trainer / "resume-{}.state".format(
            hashlib.sha256(b"jornada-B").hexdigest()[:16]
        )
        novo.write_bytes(b"jornada-B")

        atual = self.manifesto()
        self.assertEqual(antigo, atual, "o manifesto não mudou")
        conteudo = (self.trainer / atual["state"]).read_bytes()
        self.assertEqual(b"jornada-A", conteudo)
        self.assertEqual(
            atual["sha256"], hashlib.sha256(conteudo).hexdigest(),
            "o par continua coerente",
        )

    def test_a_geracao_viaja_no_manifesto(self):
        env = self.env(generation=17)
        env._commit_resume_state("session_end", b"x")
        self.assertEqual(17, self.manifesto()["generation"])

    def test_current_state_continua_existindo_para_ferramentas(self):
        env = self.env()
        env._commit_resume_state("session_end", b"jornada-A")
        self.assertEqual(b"jornada-A", (self.trainer / "current.state").read_bytes())

    def test_estados_antigos_sao_podados(self):
        env = self.env()
        for n in range(8):
            env._commit_resume_state("session_end", f"jornada-{n}".encode())
        sobraram = list(self.trainer.glob("resume-*.state"))
        self.assertLessEqual(len(sobraram), 4, "não acumula um save por chunk")
        # O vigente nunca é podado.
        self.assertIn(
            self.manifesto()["state"], [p.name for p in sobraram]
        )

    def test_gravar_o_mesmo_estado_duas_vezes_nao_duplica(self):
        env = self.env()
        env._commit_resume_state("a", b"igual")
        env._commit_resume_state("b", b"igual")
        self.assertEqual(1, len(list(self.trainer.glob("resume-*.state"))))


if __name__ == "__main__":
    unittest.main()
