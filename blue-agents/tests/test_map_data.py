"""O mapa lido do cartucho tem de bater com o que o bot pisou de verdade.

Este projeto aprendia geometria esbarrando, e essa regra se envenena sozinha:
NPC parado vira parede, batalha na tela faz todo tile ler como parede, e o
handoff registra 4067 paredes que nunca existiram.

A validação forte é de mão única e não depende de nada aprendido estar certo:
todo tile onde o bot **realmente andou** tem de ser andável na ROM. O contrário
não vale — ele nunca visitou a maior parte do mundo.
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_ROOT = str(PROJECT_ROOT / "blue-agents")
for entry in (str(PROJECT_ROOT), AGENTS_ROOT, str(PROJECT_ROOT / "blue-agents" / "tools")):
    if entry not in sys.path:
        sys.path.append(entry)

from extract_map_data import Cartridge, build

ROM = PROJECT_ROOT / "roms" / "PokemonBlue.gb"
TERRENO_APRENDIDO = PROJECT_ROOT / "blue-agents" / "knowledge" / "maps" / "terrain.json"

FLORESTA = 51
GINASIO_PEWTER = 54
CENTRO_VIRIDIAN = 41


class MapaDoCartuchoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cart = Cartridge(ROM.read_bytes())

    def test_a_floresta_tem_o_tamanho_do_jogo(self):
        head = self.cart.header(FLORESTA)
        self.assertEqual(3, head["tileset"])
        self.assertEqual((17, 24), (head["width"], head["height"]))

    def test_o_mato_da_floresta_existe_e_o_do_centro_nao(self):
        _, mato_floresta = self.cart.terrain(FLORESTA)
        _, mato_centro = self.cart.terrain(CENTRO_VIRIDIAN)
        self.assertGreater(len(mato_floresta), 300)
        self.assertEqual(set(), mato_centro, "não há grama dentro de um Centro")

    def test_os_tres_bug_catchers_da_floresta(self):
        _, gente = self.cart.objects(FLORESTA)
        treinadores = [o for o in gente if o["kind"] == "trainer"]
        self.assertEqual(3, len(treinadores))
        self.assertEqual({202}, {t["trainer_class"] for t in treinadores})
        self.assertEqual(
            {(30, 33), (30, 19), (2, 18)},
            {(t["x"], t["y"]) for t in treinadores},
        )

    def test_brock_esta_onde_a_rota_o_procura(self):
        # A rota `brock-approach` termina em (4,2), uma casa abaixo dele.
        _, gente = self.cart.objects(GINASIO_PEWTER)
        treinadores = [o for o in gente if o["kind"] == "trainer"]
        self.assertEqual(2, len(treinadores))
        lider = [t for t in treinadores if (t["x"], t["y"]) == (4, 1)]
        self.assertTrue(lider, "o líder fica em (4,1)")
        # O outro é quem estava matando o bot 1.047 vezes, entre a porta e ele.
        self.assertIn((3, 6), {(t["x"], t["y"]) for t in treinadores})

    def test_a_porta_do_ginasio_e_a_que_o_grafo_ja_conhecia(self):
        warps, _ = self.cart.objects(GINASIO_PEWTER)
        self.assertIn((4, 13), {(w["x"], w["y"]) for w in warps})

    def test_concorda_com_o_terreno_aprendido_na_floresta(self):
        """Onde o bot mais andou, os dois têm de contar a mesma coisa.

        O `terrain.json` **não** é prova de onde o bot pisou: ele é preenchido
        com a grade lida da tela, que é a leitura que já falhou antes — uma
        batalha na tela faz todo tile virar parede. Serve como testemunha
        aproximada, não como verdade, e é por isso que a comparação aceita
        divergência em vez de exigir zero.

        A Floresta é onde a amostra é maior e mais andada, e ali a diferença é
        de um tile em setecentos.
        """
        if not TERRENO_APRENDIDO.is_file():
            self.skipTest("terrain.json é ignorado pelo git e não está aqui")
        aprendido = json.loads(TERRENO_APRENDIDO.read_text(encoding="utf-8"))
        tiles = (aprendido.get("walkable") or {}).get(str(FLORESTA))
        if not tiles:
            self.skipTest("a Floresta ainda não foi visitada nesta cópia")
        andavel, _ = self.cart.terrain(FLORESTA)
        dentro = set()
        largura = max(c[0] for c in andavel) + 1
        altura = max(c[1] for c in andavel) + 1
        for tile in tiles:
            x, y = (int(p) for p in tile.split(","))
            if 0 <= x < largura and 0 <= y < altura:
                dentro.add((x, y))
        divergentes = dentro - andavel
        self.assertGreater(len(dentro), 500, "amostra pequena demais para valer")
        self.assertLessEqual(
            len(divergentes) / len(dentro), 0.01,
            f"{len(divergentes)} de {len(dentro)} divergem — acima de 1% "
            "não é ruído de leitura de tela, é erro de extração",
        )


class ExtracaoCompletaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maps = build()

    def test_cobre_o_mundo_inteiro(self):
        # O conhecimento aprendido esbarrando tinha 21 mapas depois de dias.
        self.assertGreater(len(self.maps), 200)

    def test_cada_mapa_traz_as_quatro_camadas(self):
        floresta = self.maps[str(FLORESTA)]
        for chave in ("walkable", "grass", "warps", "objects"):
            self.assertIn(chave, floresta)

    def test_coordenadas_saem_como_o_jogo_as_conta(self):
        floresta = self.maps[str(FLORESTA)]
        self.assertIn("17,46", floresta["walkable"])


if __name__ == "__main__":
    unittest.main()
