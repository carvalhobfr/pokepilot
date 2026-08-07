"""Conhecimento compartilhado: não se apaga por cima, e não se inventa porta.

Dois problemas distintos moraram em `warps.json`.

O primeiro era de escrita: `HiveMind._save_json` abria com `'w'`, que trunca o
arquivo no instante em que abre. Nesta máquina de 8 GB a falta de memória mata
processo sem rastro, e um `SIGKILL` no meio dessa escrita esvaziava o arquivo.
E como o `HiveMind` guardava a cópia carregada na partida, o segundo agente a
gravar apagava as portas do primeiro.

O segundo era de conteúdo: `WarpMemory.record` gravava "o tile onde o bot
estava quando o mapa mudou". Num apagão o mapa muda sem que ninguém tenha
pisado em porta, e o chão vira porta para sempre — Mt. Moon 1F acumulou 62
portas, das quais o cartucho reconhece 5.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
AGENTS_ROOT = str(Path(__file__).resolve().parents[1])
for entry in (PROJECT_ROOT, AGENTS_ROOT):
    if entry not in sys.path:
        sys.path.append(entry)

from src.hive_mind import HiveMind
from src.warp_memory import DYNAMIC_DESTINATION, WarpMemory


# O que o cartucho diz de Mt. Moon 1F: cinco portas, nenhuma no meio do chão.
MT_MOON_REAL = {"14,35": -1, "15,35": -1, "5,5": 60, "17,11": 60, "25,15": 60}


class SharedWarpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "maps").mkdir()
        (self.root / "walkthrough").mkdir()
        self.warp_path = self.root / "maps" / "warps.json"

    def semear(self, doors):
        self.warp_path.write_text(json.dumps(doors), encoding="utf-8")

    def hive(self):
        return HiveMind(knowledge_root=self.root)

    def warps(self):
        if not self.warp_path.exists():
            return {}
        return json.loads(self.warp_path.read_text(encoding="utf-8"))

    # --- conteúdo: só o cartucho cria porta ------------------------------

    def test_chao_comum_nao_vira_porta(self):
        self.semear({"59": dict(MT_MOON_REAL)})
        self.hive().register_warp(59, 7, 24, 15)
        self.assertEqual(MT_MOON_REAL, self.warps()["59"])

    def test_porta_dinamica_recebe_o_destino_observado(self):
        self.semear({"59": dict(MT_MOON_REAL)})
        self.hive().register_warp(59, 14, 35, 15)
        self.assertEqual(15, self.warps()["59"]["14,35"])

    def test_destino_ja_conhecido_nao_e_reescrito(self):
        self.semear({"59": dict(MT_MOON_REAL)})
        self.hive().register_warp(59, 5, 5, 99)
        self.assertEqual(60, self.warps()["59"]["5,5"])

    def test_mapa_desconhecido_nao_ganha_porta(self):
        self.semear({"59": dict(MT_MOON_REAL)})
        self.hive().register_warp(200, 1, 1, 15)
        self.assertNotIn("200", self.warps())

    # --- escrita: ninguém apaga o do outro -------------------------------

    def test_o_segundo_agente_nao_apaga_o_do_primeiro(self):
        # Os dois carregam antes de qualquer descoberta, como acontece quando
        # dois agentes sobem no mesmo processo.
        self.semear({"59": {"14,35": -1, "15,35": -1}})
        primeiro = self.hive()
        segundo = self.hive()

        primeiro.register_warp(59, 14, 35, 15)
        segundo.register_warp(59, 15, 35, 15)

        self.assertEqual({"14,35": 15, "15,35": 15}, self.warps()["59"])

    def test_o_que_o_outro_achou_entra_na_copia_em_memoria(self):
        self.semear({"59": {"14,35": -1}, "3": {"19,18": -1}})
        primeiro = self.hive()
        segundo = self.hive()
        segundo.register_warp(3, 19, 18, 64)
        primeiro.register_warp(59, 14, 35, 15)
        self.assertEqual(64, primeiro.known_warps["3"]["19,18"])

    def test_a_gravacao_nao_deixa_arquivo_pela_metade(self):
        # Um `.tmp` sobrando é aceitável; um `warps.json` truncado não é.
        portas = {f"{x},5": DYNAMIC_DESTINATION for x in range(40)}
        self.semear({"59": portas})
        hive = self.hive()
        for x in range(40):
            hive.register_warp(59, x, 5, 15)
        conteudo = self.warp_path.read_text(encoding="utf-8")
        self.assertEqual(40, len(json.loads(conteudo)["59"]))

    def test_warp_memory_recusa_tile_que_nao_e_porta(self):
        memory = WarpMemory(self.warp_path)
        memory.doors["59"] = dict(MT_MOON_REAL)
        self.assertFalse(memory.record(59, 7, 24, 15))
        self.assertTrue(memory.record(59, 14, 35, 15))


if __name__ == "__main__":
    unittest.main()
