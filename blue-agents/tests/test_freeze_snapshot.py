"""O congelamento vira save e relatório sozinho, sem passar por mim.

Hoje esse mecanismo era eu, à mão: copiar o save, sondar, escrever o
checkpoint. Cada travamento novo tem de nascer checkpoint com a tela que o
causou anexada — é isso que faz `tools/replay_check.py` crescer sem depender
de alguém estar olhando o painel na hora certa.

O save vai para `states/replay/auto/`, e não para o `states/replay/` curado: o
manifesto é escrito à mão, com a regressão que cada trecho pega. O que sai
daqui é matéria bruta para virar trecho.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from hybrid_agent import HybridGymEnv
from src import screen
from src.life_watchdog import LifeWatchdog


class FakePyBoy:
    def save_state(self, handle):
        handle.write(b"estado do cartucho")


class FrozenCartridge:
    """Mapa 94, prancha do S.S. Anne: o passo não move, nada muda."""

    def __init__(self):
        self.values = {
            0xD35E: 94, 0xD362: 14, 0xD361: 1,
            0xD163: 1, 0xD16B: 153, 0xD16B + 33: 23, 0xD16B + 2: 59,
            0xD31D: 5, 0xD356: 1, 0xD057: 0,
            0xCFC4: 1, 0xFF4A: 0,
        }

    def read_byte(self, address):
        return self.values.get(address, 0)


class FreezeSnapshotTests(unittest.TestCase):
    def env(self, directory):
        env = HybridGymEnv.__new__(HybridGymEnv)
        cartridge = FrozenCartridge()
        env.read_m = cartridge.read_byte
        env.agent_name = "TESTE"
        env.current_task = "QUEST: VERMILION_GYM_QUEST"
        env.active_quest_id = "vermilion_gym_quest"
        env.pyboy = FakePyBoy()
        env.freeze_snapshot_dir = Path(directory)
        env.life_watchdog = LifeWatchdog(window=10, distinct_floor=3, cooldown=50)
        env.logged = []
        env._log_event = lambda kind, data: env.logged.append((kind, data))
        return env

    def test_uma_janela_parada_vira_save_e_relatorio(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.env(directory)
            for _ in range(10):
                env._watch_for_freeze()

            self.assertEqual(1, len(env.logged))
            kind, report = env.logged[0]
            self.assertEqual("congelado", kind)
            self.assertEqual(94, report["map_id"])
            self.assertEqual([14, 1], report["coords"])
            self.assertEqual("vermilion_gym_quest", report["quest_id"])
            self.assertEqual([[153, 23, 59]], report["party"])

            states = list(Path(directory).glob("*.state"))
            reports = list(Path(directory).glob("*.json"))
            self.assertEqual(1, len(states))
            self.assertEqual(1, len(reports))
            self.assertEqual(b"estado do cartucho", states[0].read_bytes())
            gravado = json.loads(reports[0].read_text())
            self.assertEqual(report["snapshot"], str(states[0]))
            self.assertEqual(94, gravado["map_id"])

    def test_o_relatorio_leva_a_tela_decodificada(self):
        # Sem a tela, o relatório diz "parado em (14,1)" e a próxima pessoa
        # ainda tem de descobrir o que estava desenhado — que foi o que
        # transformou um bug de dez minutos em oito horas paradas.
        with tempfile.TemporaryDirectory() as directory:
            env = self.env(directory)
            for _ in range(10):
                env._watch_for_freeze()

            report = env.logged[0][1]
            self.assertIn("tela", report)
            self.assertEqual(screen.TEXTO, report["tela"])
            self.assertIn("linhas", report)

    def test_bot_vivo_nao_escreve_nada(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.env(directory)
            for step in range(30):
                env.read_m.__self__.values[0xD362] = 14 + step
                env._watch_for_freeze()

            self.assertEqual([], env.logged)
            self.assertEqual([], list(Path(directory).glob("*")))

    def test_a_mesma_situacao_nao_vira_um_save_por_janela(self):
        # Medido na corrida do operador em 2026-08-17: três bots no mesmo tile
        # da Floresta escreveram 2.190 arquivos (179 MB) em duas horas para
        # **6 situações**. O teto por processo não segura: cada chunk é um
        # processo novo com o contador zerado.
        with tempfile.TemporaryDirectory() as directory:
            env = self.env(directory)
            env.life_watchdog = LifeWatchdog(window=10, distinct_floor=3,
                                             cooldown=0, max_reports=99)
            for _ in range(100):
                env._watch_for_freeze()

            self.assertEqual(1, len(list(Path(directory).glob("*.state"))))
            self.assertGreater(len(env.logged), 1)
            caminhos = {report["snapshot"] for _, report in env.logged}
            self.assertEqual(1, len(caminhos))

    def test_no_diretorio_cheio_o_mais_antigo_sai(self):
        # O teto recusava informação nova: o LARON travou dois minutos depois de
        # nascer e o relatório saiu com `snapshot: None`, porque o diretório
        # estava cheio de travamentos de outra corrida. Disco é limite de disco.
        with tempfile.TemporaryDirectory() as directory:
            antigos = []
            for index in range(40):
                caminho = Path(directory) / f"OUTRO-m{index}-0x0-1.state"
                caminho.write_bytes(b"x")
                antigos.append(caminho)
            env = self.env(directory)
            for _ in range(10):
                env._watch_for_freeze()

            self.assertEqual(1, len(env.logged))
            self.assertIsNotNone(env.logged[0][1]["snapshot"])
            self.assertFalse(antigos[0].exists(), "o mais antigo saiu")
            self.assertEqual(40, len(list(Path(directory).glob("*.state"))))

    def test_uma_leitura_que_falha_nao_derruba_o_passo(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.env(directory)

            def quebrado(address):
                raise RuntimeError("emulador fechando")

            env.read_m = quebrado
            env._watch_for_freeze()
            self.assertEqual([], env.logged)


if __name__ == "__main__":
    unittest.main()
