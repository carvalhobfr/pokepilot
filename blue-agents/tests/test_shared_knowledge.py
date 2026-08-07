"""Conhecimento compartilhado não pode ser apagado por quem chega depois.

`warps.json` tinha dois escritores com garantias diferentes: `WarpMemory` relê,
funde e troca atomicamente; `HiveMind` guardava a cópia carregada na partida e
regravava tudo por cima, com `open(path, 'w')`, que trunca no instante em que
abre. Nesta máquina de 8 GB a falta de memória mata processo sem rastro, e um
`SIGKILL` no meio dessa escrita deixava o arquivo vazio.
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


class SharedWarpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "maps").mkdir()
        (self.root / "walkthrough").mkdir()

    def hive(self):
        return HiveMind(knowledge_root=self.root)

    def warps(self):
        path = self.root / "maps" / "warps.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def test_uma_porta_descoberta_vai_para_o_disco(self):
        self.hive().register_warp(59, 5, 5, 15)
        self.assertEqual({"59": {"5,5": 15}}, self.warps())

    def test_o_segundo_agente_nao_apaga_o_do_primeiro(self):
        # Os dois carregam antes de qualquer descoberta, como acontece quando
        # dois agentes sobem no mesmo processo. Era aqui que o segundo a
        # gravar levava as portas do primeiro junto.
        primeiro = self.hive()
        segundo = self.hive()

        primeiro.register_warp(59, 5, 5, 15)
        segundo.register_warp(59, 14, 35, 4)

        self.assertEqual({"59": {"5,5": 15, "14,35": 4}}, self.warps())

    def test_o_que_o_outro_achou_entra_na_copia_em_memoria(self):
        primeiro = self.hive()
        segundo = self.hive()
        segundo.register_warp(3, 19, 18, 64)
        primeiro.register_warp(59, 5, 5, 15)
        self.assertIn("3", primeiro.known_warps)

    def test_mapas_diferentes_convivem(self):
        hive = self.hive()
        hive.register_warp(59, 5, 5, 15)
        hive.register_warp(15, 11, 5, 68)
        self.assertEqual({"59": {"5,5": 15}, "15": {"11,5": 68}}, self.warps())

    def test_a_gravacao_nao_deixa_arquivo_pela_metade(self):
        # Um `.tmp` sobrando é aceitável; um `warps.json` truncado não é. O que
        # o teste garante é que o arquivo final sempre é JSON inteiro.
        hive = self.hive()
        for tile in range(40):
            hive.register_warp(59, tile, 5, 15)
        conteudo = (self.root / "maps" / "warps.json").read_text(encoding="utf-8")
        self.assertEqual(40, len(json.loads(conteudo)["59"]))

    def test_registrar_a_mesma_porta_duas_vezes_nao_muda_nada(self):
        hive = self.hive()
        hive.register_warp(59, 5, 5, 15)
        antes = self.warps()
        hive.register_warp(59, 5, 5, 15)
        self.assertEqual(antes, self.warps())


if __name__ == "__main__":
    unittest.main()
