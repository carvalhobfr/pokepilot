"""Uma conclusão só vale na retomada se algum checkpoint a contém.

Os três momentos de morte que importam: antes do feito, depois do feito e
antes do Centro, e depois do Centro. Só o terceiro deixa a conclusão de pé.
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
from quest_graph import QuestGraph, QuestNode


CERULEAN_BADGE_BIT = 1


class FakeState:
    """O que os predicados do QuestGraph leem da RAM."""

    def __init__(self, map_id=0, badges_mask=0):
        self.map_id = map_id
        self.badges_mask = badges_mask


def build_graph():
    return QuestGraph([
        QuestNode(
            id="mt_moon_nav",
            title="Atravessar Mt. Moon",
            executor="mt_moon_nav",
            success=({"type": "map_in", "values": [59]},),
        ),
        QuestNode(
            id="cerulean_gym_quest",
            title="Vencer Misty",
            executor="cerulean_gym_quest",
            success=({"type": "badge", "index": CERULEAN_BADGE_BIT},),
        ),
    ])


class CheckpointGenerationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.trainer_dir = Path(self.directory.name)
        self.logged = []

    def make_env(self, generation=0, completed=(), generations=None):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.agent_name = "AARON"
        env.quest_graph = build_graph()
        env.quest_completed_ids = set(completed)
        env.quest_generations = dict(generations or {})
        env.checkpoint_generation = generation
        env._checkpoint_loaded_from_disk = True
        env.trainer_dir = self.trainer_dir
        env.journey_memory_path = self.trainer_dir / "journey.json"
        env.decision_log_path = self.trainer_dir / "decisions.jsonl"
        env.visited_major_locations = set()
        env.announced_story_milestones = set()
        env.head_start_served = False
        env.delay_steps = 0
        env.death_cycle = 0
        env._log_event = lambda kind, data: self.logged.append((kind, data))
        return env

    # --- os três momentos -------------------------------------------------

    def test_morte_antes_do_feito_nao_inventa_progresso(self):
        env = self.make_env(generation=3)
        env._drop_progress_the_cartridge_denies(FakeState())
        self.assertEqual(env.quest_completed_ids, set())

    def test_morte_depois_do_feito_e_antes_do_centro_reavalia_na_ram(self):
        # Observada rodando na geração 3; nenhum checkpoint acima de 3 foi
        # escrito, então o save carregado não a contém. Quem responde é a RAM.
        env = self.make_env(
            generation=3,
            completed=("cerulean_gym_quest",),
            generations={"cerulean_gym_quest": 3},
        )
        env._drop_progress_the_cartridge_denies(FakeState(badges_mask=0))
        self.assertEqual(env.quest_completed_ids, set())
        self.assertEqual(self.logged[0][0], "progress_reset")

    def test_a_ram_pode_confirmar_uma_conclusao_nao_selada(self):
        env = self.make_env(
            generation=3,
            completed=("cerulean_gym_quest",),
            generations={"cerulean_gym_quest": 3},
        )
        env._drop_progress_the_cartridge_denies(
            FakeState(badges_mask=1 << CERULEAN_BADGE_BIT)
        )
        self.assertEqual(env.quest_completed_ids, {"cerulean_gym_quest"})

    def test_morte_depois_do_centro_mantem_a_conclusao(self):
        # Selada: observada na geração 3, e o Centro escreveu a 4.
        env = self.make_env(
            generation=4,
            completed=("cerulean_gym_quest",),
            generations={"cerulean_gym_quest": 3},
        )
        env._drop_progress_the_cartridge_denies(FakeState(badges_mask=0))
        self.assertEqual(env.quest_completed_ids, {"cerulean_gym_quest"})

    # --- o nó transiente, que era permanente por engano -------------------

    def test_travessia_selada_continua_de_pe_fora_do_mapa(self):
        env = self.make_env(
            generation=4,
            completed=("mt_moon_nav",),
            generations={"mt_moon_nav": 3},
        )
        env._drop_progress_the_cartridge_denies(FakeState(map_id=3))
        self.assertEqual(env.quest_completed_ids, {"mt_moon_nav"})

    def test_travessia_nao_selada_cai_num_save_rebobinado(self):
        # Era este o buraco: `map_in` nunca era rechecado, então uma travessia
        # lembrada pulava Mt. Moon com o treinador parado em Pewter.
        env = self.make_env(
            generation=3,
            completed=("mt_moon_nav",),
            generations={"mt_moon_nav": 3},
        )
        env._drop_progress_the_cartridge_denies(FakeState(map_id=3))
        self.assertEqual(env.quest_completed_ids, set())

    def test_journey_antigo_sem_carimbo_responde_a_ram(self):
        env = self.make_env(generation=9, completed=("mt_moon_nav",))
        env._drop_progress_the_cartridge_denies(FakeState(map_id=3))
        self.assertEqual(env.quest_completed_ids, set())

    # --- o laço que fechava cedo demais -----------------------------------

    def test_segunda_carga_no_mesmo_processo_tambem_e_verificada(self):
        env = self.make_env(
            generation=4,
            completed=("mt_moon_nav",),
            generations={"mt_moon_nav": 3},
        )
        env._drop_progress_the_cartridge_denies(FakeState(map_id=3))
        self.assertEqual(env.quest_completed_ids, {"mt_moon_nav"})

        # Rebobinou para um Centro sem manifesto: geração desconhecida, nada
        # está selado, e a verificação tem de rodar de novo.
        env.checkpoint_generation = 0
        env._checkpoint_loaded_from_disk = True
        env._drop_progress_the_cartridge_denies(FakeState(map_id=3))
        self.assertEqual(env.quest_completed_ids, set())

    def test_retomada_recusada_tambem_reconfere(self):
        # O caso perigoso, e o único que escapava: o resume falha, o emulador
        # fica com o estado de partida — o mais rebobinado que existe — e o
        # journey continua alegando a jornada inteira. CARON acordou no quarto
        # inicial com zero insígnias jurando ter atravessado Mt. Moon.
        env = self.make_env(
            generation=0,
            completed=("mt_moon_nav", "cerulean_gym_quest"),
            generations={"mt_moon_nav": 3, "cerulean_gym_quest": 3},
        )
        env._drop_progress_the_cartridge_denies(FakeState(map_id=38, badges_mask=0))
        self.assertEqual(set(), env.quest_completed_ids)

    def test_reset_sem_carga_de_disco_nao_mexe_no_progresso(self):
        # Um `reset` que só continua de onde estava não pode desfazer uma
        # travessia recém-feita só porque o bot já saiu do mapa.
        env = self.make_env(
            generation=3,
            completed=("mt_moon_nav",),
            generations={"mt_moon_nav": 3},
        )
        env._checkpoint_loaded_from_disk = False
        env._drop_progress_the_cartridge_denies(FakeState(map_id=3))
        self.assertEqual(env.quest_completed_ids, {"mt_moon_nav"})

    # --- ida e volta ao disco ---------------------------------------------

    def test_o_carimbo_sobrevive_ao_journey_json(self):
        env = self.make_env(
            generation=4,
            completed=("mt_moon_nav",),
            generations={"mt_moon_nav": 3},
        )
        env._persist_journey_memory()

        written = json.loads(env.journey_memory_path.read_text(encoding="utf-8"))
        self.assertEqual(written["completed_quests"], ["mt_moon_nav"])
        self.assertEqual(written["quest_generations"], {"mt_moon_nav": 3})
        self.assertEqual(written["checkpoint_generation"], 4)

        restored = self.make_env()
        restored._load_journey_memory()
        self.assertEqual(restored.quest_completed_ids, {"mt_moon_nav"})
        self.assertEqual(restored.quest_generations, {"mt_moon_nav": 3})


class CenterCheckpointTests(unittest.TestCase):
    """Estar no Centro basta. Cura não é mais condição.

    A regra antiga era: cura confirmada + time cheio → checkpoint. Com a cura
    automática cancelada, o time nunca mais fica cheio por vontade própria, e
    essa condição não deixaria sobrar nenhum ponto de retomada.
    """

    PEWTER_CENTER = 58

    def make_env(self, map_id, party, armed=True):
        env = HybridGymEnv.__new__(HybridGymEnv)
        env.agent_name = "AARON"
        env.in_battle = False
        env.scripted_agent = type("FakeScripted", (), {})()
        env.read_m = lambda address: map_id if address == 0xD35E else 0
        env.get_party_info = lambda: list(party)
        env.center_checkpoint_armed = armed
        env.saved = []
        env._save_checkpoint = lambda milestone: env.saved.append(milestone) or True
        return env

    def test_time_machucado_num_centro_grava_checkpoint(self):
        env = self.make_env(self.PEWTER_CENTER, [{"hp": 1, "max_hp": 59}])
        env._check_milestones()
        self.assertEqual(["center_58"], env.saved)

    def test_time_inteiro_num_centro_tambem_grava(self):
        # Vencer um ginásio sem levar dano e entrar no Centro a 100% não
        # gravava nada, porque não havia o que curar.
        env = self.make_env(self.PEWTER_CENTER, [{"hp": 59, "max_hp": 59}])
        env._check_milestones()
        self.assertEqual(["center_58"], env.saved)

    def test_nao_grava_de_novo_sem_sair(self):
        env = self.make_env(self.PEWTER_CENTER, [{"hp": 1, "max_hp": 59}])
        env._check_milestones()
        env._check_milestones()
        self.assertEqual(["center_58"], env.saved)

    def test_sair_rearma_para_a_proxima_visita(self):
        # Gravar uma vez por Centro por jornada congelava o ponto de retomada
        # na primeira visita, e todo progresso depois dela ficava sem rede.
        env = self.make_env(self.PEWTER_CENTER, [{"hp": 1, "max_hp": 59}])
        env._check_milestones()
        env.read_m = lambda address: 2 if address == 0xD35E else 0
        env._check_milestones()
        env.read_m = lambda address: self.PEWTER_CENTER if address == 0xD35E else 0
        env._check_milestones()
        self.assertEqual(["center_58", "center_58"], env.saved)

    def test_fora_de_centro_nao_grava(self):
        env = self.make_env(2, [{"hp": 1, "max_hp": 59}])
        env._check_milestones()
        self.assertEqual([], env.saved)

    def test_em_batalha_nao_grava(self):
        env = self.make_env(self.PEWTER_CENTER, [{"hp": 1, "max_hp": 59}])
        env.in_battle = True
        env._check_milestones()
        self.assertEqual([], env.saved)


if __name__ == "__main__":
    unittest.main()
