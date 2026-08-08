"""Treinar até ter o golpe que o ginásio não resiste — não até um nível.

Medido em corrida: Bulbasaur nível 10, com Tackle, Growl e Leech Seed, perdeu
269 vezes seguidas para o Brock. Chegava curado do Centro todas as vezes — o
problema nunca foi HP. Tackle é Normal e Rocha resiste; Vine Whip é Grama e bate
4× no Geodude. O portão é o golpe, porque um número de nível eu posso errar de
cabeça e o cartucho não mente sobre o que está no slot.

Onde treinar era o que errou cinco vezes antes. Agora a grama e a posição de
cada treinador vêm de `static_maps.json`, extraído da ROM.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.map_memory import MapMemory
from src.move_data import MoveTable
from src.scripted_agent import (
    GYM_EFFECTIVE_TYPES,
    TRAINING_MAX_LEVEL,
    TRAINING_TRAINER_CLEARANCE,
    ScriptedAgent,
)

FLORESTA = 51
TACKLE, GROWL, LEECH_SEED, VINE_WHIP = 33, 45, 73, 22
ROM = Path(PROJECT_ROOT) / "roms" / "PokemonBlue.gb"


class MemoriaFalsa:
    """Só o suficiente do struct de party: nível no 33, golpes a partir do 8."""

    def __init__(self, party, pos=(17, 46)):
        self.party = party
        self.pos = pos

    def get_party_count(self):
        return len(self.party)

    def get_player_pos(self):
        return self.pos

    def read_byte(self, address):
        index, offset = divmod(address - 0xD16B, 44)
        if not 0 <= index < len(self.party):
            return 0
        nivel, golpes = self.party[index]
        if offset == 33:
            return nivel
        if 8 <= offset <= 11:
            slot = offset - 8
            return golpes[slot] if slot < len(golpes) else 0
        return 0


class PortaoDeTreinoTests(unittest.TestCase):
    def agente(self, party, pos=(17, 46)):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        memoria = MemoriaFalsa(party, pos)
        agent.emulator = type("FakeEmulator", (), {"memory": memoria})()
        agent.move_table = MoveTable.from_rom_file(ROM)
        agent.andou = []
        agent._follow_route = lambda route_id, waypoints: agent.andou.append(
            (route_id, waypoints)
        ) or "ANDANDO"
        agent._map_memory = lambda: MapMemory()
        return agent

    def test_o_time_do_aaron_precisa_treinar(self):
        # Exatamente o que perdeu 269 vezes.
        agent = self.agente([(10, [TACKLE, GROWL, LEECH_SEED])])
        self.assertTrue(agent._needs_training())

    def test_vine_whip_encerra_o_treino(self):
        agent = self.agente([(13, [TACKLE, GROWL, LEECH_SEED, VINE_WHIP])])
        self.assertFalse(agent._needs_training())

    def test_o_golpe_vale_mesmo_em_nivel_baixo(self):
        # O portão é o golpe, não o nível: quem já tem com o que bater, vai.
        agent = self.agente([(7, [VINE_WHIP])])
        self.assertFalse(agent._needs_training())

    def test_o_teto_de_nivel_impede_treinar_para_sempre(self):
        # Um time que nunca aprende o golpe certo não pode ficar preso na grama.
        agent = self.agente([(TRAINING_MAX_LEVEL, [TACKLE, GROWL])])
        self.assertFalse(agent._needs_training())

    def test_agua_e_luta_tambem_servem(self):
        # Squirtle com Bubble resolve o mesmo ginásio.
        self.assertIn("WATER", GYM_EFFECTIVE_TYPES)
        agent = self.agente([(10, [145])])   # Bubble
        self.assertFalse(agent._needs_training())

    def test_golpe_de_status_nao_conta(self):
        # Growl é Normal e potência zero; Leech Seed é Grama e potência zero.
        agent = self.agente([(10, [GROWL, LEECH_SEED])])
        self.assertTrue(agent._needs_training())


class OndeTreinarTests(unittest.TestCase):
    def agente(self, pos):
        agent = ScriptedAgent.__new__(ScriptedAgent)
        agent.emulator = type("FakeEmulator", (), {
            "memory": MemoriaFalsa([(10, [TACKLE])], pos)
        })()
        agent._map_memory = lambda: MapMemory()
        agent.andou = []
        agent._follow_route = lambda route_id, waypoints: agent.andou.append(
            (route_id, waypoints)
        ) or "ANDANDO"
        return agent

    def setUp(self):
        if not MapMemory().grass_cells(FLORESTA):
            self.skipTest("static_maps.json ausente")

    def test_escolhe_par_de_mato_longe_dos_bug_catchers(self):
        agent = self.agente((17, 46))
        par = agent._pick_training_pair(FLORESTA)
        self.assertIsNotNone(par)
        grass = MapMemory().grass_cells(FLORESTA)
        trainers = MapMemory().trainer_positions(FLORESTA)
        for cell in par:
            self.assertIn(cell, grass, "as duas células têm de ser mato")
            folga = min(abs(cell[0]-t[0]) + abs(cell[1]-t[1]) for t in trainers)
            self.assertGreaterEqual(folga, TRAINING_TRAINER_CLEARANCE)

    def test_o_par_e_vizinho(self):
        par = self.agente((17, 46))._pick_training_pair(FLORESTA)
        (ax, ay), (bx, by) = par
        self.assertEqual(1, abs(ax-bx) + abs(ay-by), "andar entre eles é um passo")

    def test_o_par_fica_perto_da_porta(self):
        # A caminhada até a grama não pode virar a viagem.
        par = self.agente((17, 46))._pick_training_pair(FLORESTA)
        self.assertLessEqual(
            min(abs(c[0]-17) + abs(c[1]-46) for c in par), 10
        )

    def test_o_par_e_fixado_e_nao_se_refaz(self):
        # "Pisar na grama mais próxima" parece local e não é: escolher sempre o
        # mesmo canto é um rumo fixo, e foi assim que uma versão subiu quatorze
        # casas pela coluna de mato até esbarrar no bug catcher.
        agent = self.agente((17, 46))
        agent._train_in_measured_grass(FLORESTA)
        primeiro = agent.training_pair
        agent.emulator.memory.pos = (18, 41)
        agent._train_in_measured_grass(FLORESTA)
        self.assertEqual(primeiro, agent.training_pair)

    def test_vai_e_volta_entre_as_duas(self):
        agent = self.agente((17, 46))
        agent.training_pair = ((18, 41), (18, 40))
        agent.emulator.memory.pos = (18, 41)
        agent._train_in_measured_grass(FLORESTA)
        self.assertEqual([(18, 40)], agent.andou[-1][1])
        agent.emulator.memory.pos = (18, 40)
        agent._train_in_measured_grass(FLORESTA)
        self.assertEqual([(18, 41)], agent.andou[-1][1])

    def test_mapa_sem_mato_nao_treina(self):
        agent = self.agente((3, 7))
        self.assertIsNone(agent._pick_training_pair(41))   # Centro de Viridian


if __name__ == "__main__":
    unittest.main()
