"""Diário conta repetição em vez de repetir a linha.

Uma corrida do AARON gravou 14.275 eventos em 11,8 MB, e 2.093 deles eram o
mesmo ciclo dentro de Mt. Moon: encontrou Zubat, não capturou por falta de
bola, batalha terminou. Nenhum id duplicado — o bot repetia mesmo. Quem lê
precisa do total, não da rolagem.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from hybrid_agent import HybridGymEnv


class EventRepeatTests(unittest.TestCase):
    def make_env(self):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.written = []
        env._write_event = lambda kind, data, live=True: env.written.append(
            (kind, dict(data))
        )
        env._repeat_signature = None
        env._repeat_count = 0
        return env

    ZUBAT = {"battle": "wild", "enemy_species_id": 41, "enemy_level": 7}

    def test_a_primeira_sai_na_hora(self):
        env = self.make_env()
        env._log_event("battle_started", self.ZUBAT)
        self.assertEqual([("battle_started", self.ZUBAT)], env.written)

    def test_as_repetidas_nao_viram_linha(self):
        env = self.make_env()
        for _ in range(2093):
            env._log_event("battle_started", self.ZUBAT)
        self.assertEqual(1, len(env.written))

    def test_a_quebra_da_sequencia_fecha_com_o_total(self):
        env = self.make_env()
        for _ in range(1643):
            env._log_event("battle_started", self.ZUBAT)
        env._log_event("quest_advanced", {"to_quest_id": "bill_quest"})

        tipos = [kind for kind, _ in env.written]
        self.assertEqual(
            ["battle_started", "battle_started_repeated", "quest_advanced"],
            tipos,
        )
        self.assertEqual(1642, env.written[1][1]["repeated"])

    def test_dado_diferente_e_evento_diferente(self):
        env = self.make_env()
        env._log_event("battle_started", self.ZUBAT)
        env._log_event("battle_started", {**self.ZUBAT, "enemy_species_id": 74})
        self.assertEqual(2, len(env.written))

    def test_o_vaivem_entre_dois_mapas_colapsa_como_ciclo(self):
        # Ida e volta é ciclo de período 2, e é exatamente a assinatura de
        # travamento que o relatório procura. As primeiras voltas saem por
        # extenso; o resto vira uma linha com o total.
        env = self.make_env()
        for _ in range(60):
            env._log_event("map_changed", {"map": 59})
            env._log_event("map_changed", {"map": 15})
        env._flush_repeated_event()

        tipos = [kind for kind, _ in env.written]
        self.assertIn("ciclo_repetido", tipos)
        self.assertLess(len(env.written), 20, "120 eventos não viram 120 linhas")
        resumo = next(d for k, d in env.written if k == "ciclo_repetido")
        self.assertEqual(2, resumo["period"])

    def test_o_fim_da_sessao_nao_perde_a_contagem(self):
        env = self.make_env()
        for _ in range(30):
            env._log_event("battle_started", self.ZUBAT)
        env._flush_repeated_event()
        self.assertEqual("battle_started_repeated", env.written[-1][0])
        self.assertEqual(29, env.written[-1][1]["repeated"])


if __name__ == "__main__":
    unittest.main()
