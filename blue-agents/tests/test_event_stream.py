"""O diário colapsa ciclo, não só repetição idêntica.

AARON em Mt. Moon produziu `battle_started → capture_decision →
battle_decision → battle_end → capture_outcome → battle_escaped`, 2.093 voltas.
Nenhuma assinatura consecutiva se repetia, então um filtro de repetição simples
não via nada e deixava passar 12.558 linhas.
"""

import sys
import unittest
from pathlib import Path

AGENTS_ROOT = str(Path(__file__).resolve().parents[1])
if AGENTS_ROOT not in sys.path:
    sys.path.append(AGENTS_ROOT)

from event_stream import EventCollapser


class Corrente:
    """Roda assinaturas pelo colapsador e guarda o que sairia no diário."""

    def __init__(self, **kwargs):
        self.collapser = EventCollapser(**kwargs)
        self.emitidos = []
        self.resumos = []

    def feed(self, *signatures):
        for signature in signatures:
            action, summary = self.collapser.observe(signature)
            if summary is not None:
                self.resumos.append(summary)
            if action == "emit":
                self.emitidos.append(signature)
        return self

    def flush(self):
        summary = self.collapser.flush()
        if summary is not None:
            self.resumos.append(summary)
        return self


CICLO = ("battle_started", "capture_decision", "battle_decision",
         "battle_end", "capture_outcome", "battle_escaped")


class RepeticaoConsecutivaTests(unittest.TestCase):
    def test_identico_seguido_vira_contagem(self):
        c = Corrente().feed(*["zubat"] * 2093).flush()
        self.assertEqual(["zubat"], c.emitidos)
        self.assertEqual(1, len(c.resumos))
        self.assertEqual("repeat", c.resumos[0]["kind"])
        self.assertEqual(2092, c.resumos[0]["count"])

    def test_a_quebra_fecha_a_contagem_antes_do_proximo(self):
        c = Corrente().feed(*(["zubat"] * 10 + ["misty"]))
        self.assertEqual(["zubat", "misty"], c.emitidos)
        self.assertEqual(9, c.resumos[0]["count"])


class CicloTests(unittest.TestCase):
    def test_o_ciclo_de_mt_moon_para_de_encher_o_diario(self):
        c = Corrente().feed(*(CICLO * 2093)).flush()
        # As primeiras voltas saem por extenso para quem lê ver o padrão; o
        # resto vira uma linha.
        self.assertLess(len(c.emitidos), 40)
        ciclos = [r for r in c.resumos if r["kind"] == "cycle"]
        self.assertEqual(1, len(ciclos))
        self.assertEqual(6, ciclos[0]["period"])
        self.assertEqual(
            2093 * 6, len(c.emitidos) + ciclos[0]["count"],
            "nenhum evento pode sumir da contagem",
        )

    def test_duas_voltas_sozinhas_ainda_saem_inteiras(self):
        # Duas voltas não provam que o bot está preso.
        c = Corrente().feed(*(CICLO * 2)).flush()
        self.assertEqual(list(CICLO * 2), c.emitidos)
        self.assertEqual([], [r for r in c.resumos if r["kind"] == "cycle"])

    def test_sair_do_ciclo_fecha_com_o_total(self):
        c = Corrente().feed(*(CICLO * 100)).feed("quest_advanced")
        ciclos = [r for r in c.resumos if r["kind"] == "cycle"]
        self.assertEqual(1, len(ciclos))
        self.assertEqual("quest_advanced", c.emitidos[-1])

    def test_o_vaivem_entre_dois_mapas_e_ciclo_de_periodo_dois(self):
        # Exatamente o que o relatório de travamento procura.
        c = Corrente().feed(*(("mapa_59", "mapa_15") * 50)).flush()
        ciclos = [r for r in c.resumos if r["kind"] == "cycle"]
        self.assertEqual(1, len(ciclos))
        self.assertEqual(2, ciclos[0]["period"])

    def test_sequencia_sem_padrao_passa_inteira(self):
        eventos = [f"evento_{n}" for n in range(40)]
        c = Corrente().feed(*eventos).flush()
        self.assertEqual(eventos, c.emitidos)
        self.assertEqual([], c.resumos)

    def test_progresso_real_nunca_e_suprimido(self):
        # Uma quest que avança no meio de um ciclo tem de aparecer.
        c = Corrente().feed(*(CICLO * 50)).feed("quest_advanced").feed(*(CICLO * 50))
        self.assertIn("quest_advanced", c.emitidos)

    def test_ciclo_longo_demais_nao_conta_como_travamento(self):
        # Período acima do teto é comportamento de quest longa, não loop.
        longo = tuple(f"passo_{n}" for n in range(12))
        c = Corrente().feed(*(longo * 6)).flush()
        self.assertEqual([], [r for r in c.resumos if r["kind"] == "cycle"])


if __name__ == "__main__":
    unittest.main()
