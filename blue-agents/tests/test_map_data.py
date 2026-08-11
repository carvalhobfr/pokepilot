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

class NavegacaoPeloCartuchoTests(unittest.TestCase):
    """Os quatro travamentos desta sessão, com o mapa da ROM ligado."""

    @classmethod
    def setUpClass(cls):
        from src.map_memory import MapMemory
        cls.memoria = MapMemory()
        if not cls.memoria.static:
            raise unittest.SkipTest("static_maps.json ausente")

    def test_carrega_o_mundo_inteiro(self):
        self.assertGreater(len(self.memoria.static), 200)

    def test_o_alvo_que_o_aaron_nao_alcancava(self):
        # `path_to_target: None` por 1.500 passos, com o terreno lido da tela.
        caminho = self.memoria.find_path(FLORESTA, (8, 30), (7, 22))
        self.assertIsNotNone(caminho, "a ROM conhece a volta")
        self.assertGreater(len(caminho), 50, "é volta longa, e é por isso que existe")

    def test_da_porta_do_ginasio_ao_brock_sao_onze_passos(self):
        # O bot passou horas entrando e saindo deste mapa.
        caminho = self.memoria.find_path(GINASIO_PEWTER, (4, 13), (4, 2))
        self.assertEqual(11, len(caminho))
        self.assertEqual(set("U"), set(caminho), "é reto para cima")

    def test_da_porta_da_floresta_ao_mato_do_corredor(self):
        caminho = self.memoria.find_path(FLORESTA, (17, 46), (18, 41))
        self.assertIsNotNone(caminho)
        self.assertLessEqual(len(caminho), 8)

    def test_parede_do_cartucho_e_parede_de_verdade(self):
        # (3,3) em Viridian: o quadrante inteiro é o tile 0x11, que o tileset
        # não lista como passável. O terreno aprendido dizia que dava.
        self.assertTrue(self.memoria.is_solid(1, (3, 3)))

    def test_objetos_do_b2f_incluem_os_fosseis_e_o_treinador(self):
        # (12,6)/(13,6) são os fósseis DOME/HELIX (SPRITE_FOSSIL no bloco de
        # objetos), (12,8) é o Super Nerd e (25,21)/(29,5) são item balls.
        # Nenhum anda; o plano normal deve contorná-los.
        objetos = self.memoria.object_positions(61)
        for tile in ((12, 6), (13, 6), (12, 8), (25, 21), (29, 5)):
            self.assertIn(tile, objetos)

    def test_sala_dos_fosseis_so_e_alcancavel_atraves_dos_objetos(self):
        # O portão da travessia do B2F: com treinador e fósseis bloqueados,
        # o planejador normal não acha caminho da sala central para a sala dos
        # fósseis — a interação (batalha/pickup) é obrigatória. O fallback
        # otimista continua devolvendo um caminho (cruza o tile que abre).
        bloqueados = self.memoria.object_positions(61)
        self.assertIsNone(
            self.memoria.find_path(61, (13, 8), (3, 4), blocked=bloqueados)
        )
        self.assertIsNotNone(
            self.memoria.find_path(
                61, (13, 8), (3, 4), blocked=bloqueados, ignore_solid=True
            )
        )

    def test_rota_do_mt_moon_continua_conectada_com_objetos_bloqueados(self):
        # As pernas reais das rotas 59/60/61 seguem válidas com treinadores,
        # fósseis e item balls bloqueados no planejador; a única exceção é o
        # portão do fóssil, coberto pelo fallback.
        bloqueados = self.memoria.object_positions(61)
        pernas_61 = [
            ((21, 17), (26, 31)), ((26, 31), (10, 26)), ((10, 26), (13, 8)),
            ((3, 4), (7, 4)), ((7, 4), (11, 4)), ((11, 4), (16, 4)),
            ((16, 4), (5, 7)),
        ]
        for origem, destino in pernas_61:
            self.assertIsNotNone(
                self.memoria.find_path(61, origem, destino, blocked=bloqueados),
                f"{origem} -> {destino} deveria seguir conectada",
            )
        for origem, destino in [
            ((13, 8), (3, 4)),  # o portão dos fósseis, deliberadamente excluído
        ]:
            self.assertIsNone(
                self.memoria.find_path(61, origem, destino, blocked=bloqueados)
            )

    def test_a_tela_nao_reescreve_o_que_veio_do_cartucho(self):
        # Em batalha o mapa de tiles guarda a arena e todo tile lê como parede.
        antes = set(self.memoria.static[FLORESTA])
        self.memoria.observe(FLORESTA, (17, 46), {(0, 0): False, (0, -1): False})
        self.assertEqual(antes, self.memoria.static[FLORESTA])
        self.assertFalse(self.memoria.is_solid(FLORESTA, (17, 46)))

if __name__ == "__main__":
    unittest.main()
