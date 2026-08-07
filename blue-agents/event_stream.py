"""Colapsar o que o diário repete, sem perder o que ele conta.

Duas formas de repetição aparecem numa corrida travada, e só a primeira é
óbvia:

1. **consecutiva** — o mesmo evento, idêntico, N vezes seguidas;
2. **cíclica** — um punhado de eventos *diferentes* que se repetem em ordem.
   Foi o caso de AARON em Mt. Moon: `battle_started → capture_decision →
   battle_decision → battle_end → capture_outcome → battle_escaped`, 2.093
   voltas. Nenhuma assinatura consecutiva se repetia, então um filtro de
   repetição simples não via nada e deixava passar 12.558 linhas.

O que sai do outro lado: as primeiras voltas por extenso, para quem lê
entender o padrão, e depois uma linha só dizendo quantas foram.
"""

from __future__ import annotations

from collections import deque

# Ciclos maiores que isso deixam de ser "o bot está preso" e viram
# comportamento normal de uma quest longa.
MAX_CYCLE_PERIOD = 8
# Voltas completas que ainda saem por extenso antes de o resumo assumir. Duas
# porque uma volta sozinha não prova ciclo nenhum.
CYCLE_GRACE_TURNS = 2


class EventCollapser:
    """Decide se um evento vira linha, ou vira contagem.

    Não escreve nada: responde `emit`, `suppress` ou `summary`, e quem chama
    faz a escrita. Assim isto é testável sem emulador, sem disco e sem env.
    """

    def __init__(self, max_period=MAX_CYCLE_PERIOD, grace=CYCLE_GRACE_TURNS):
        self.max_period = int(max_period)
        self.grace = int(grace)
        self.history = deque(maxlen=self.max_period * 2)
        self.repeat_signature = None
        self.repeat_count = 0
        self.cycle_period = 0
        self.cycle_turns = 0
        self.cycle_suppressed = 0

    # -- repetição consecutiva --------------------------------------------

    def _take_repeat_summary(self):
        """A contagem em aberto, se houver — e ela zera ao ser lida.

        Tem de ser lida **antes** de trocar a assinatura corrente, senão o
        total da sequência que acabou de terminar some junto com ela.
        """
        count = self.repeat_count
        signature = self.repeat_signature
        self.repeat_count = 0
        if not count or signature is None:
            return None
        return {"kind": "repeat", "signature": signature, "count": count}

    # -- repetição cíclica -------------------------------------------------

    def _period_ending_here(self):
        """Menor período p cujas duas últimas voltas são idênticas."""
        entries = list(self.history)
        for period in range(2, self.max_period + 1):
            if len(entries) < period * 2:
                break
            if entries[-period:] == entries[-period * 2:-period]:
                return period
        return 0

    def _take_cycle_summary(self):
        suppressed = self.cycle_suppressed
        period = self.cycle_period
        self.cycle_period = 0
        self.cycle_turns = 0
        self.cycle_suppressed = 0
        if not suppressed:
            return None
        return {
            "kind": "cycle",
            "period": period,
            "count": suppressed,
            "turns": suppressed // period if period else 0,
        }

    # -- decisão -----------------------------------------------------------

    def observe(self, signature):
        """O que fazer com este evento.

        Devolve `(acao, resumo)`. `acao` é ``"emit"`` ou ``"suppress"``, e
        `resumo` — quando existe — é a linha de fechamento de uma sequência
        que acabou de terminar e precisa sair **antes** deste evento.
        """
        if signature == self.repeat_signature:
            self.repeat_count += 1
            return "suppress", None

        pending = self._take_repeat_summary()
        self.repeat_signature = signature
        self.history.append(signature)
        period = self._period_ending_here()

        if period:
            if period != self.cycle_period:
                # Ciclo novo: o anterior, se havia, fecha agora.
                pending = pending or self._take_cycle_summary()
                self.cycle_period = period
                self.cycle_turns = 0
                self.cycle_suppressed = 0
            self.cycle_turns += 1
            if self.cycle_turns > period * self.grace:
                self.cycle_suppressed += 1
                return "suppress", pending
            return "emit", pending

        pending = pending or self._take_cycle_summary()
        return "emit", pending

    def flush(self):
        """Fechar o que estiver em aberto — fim de sessão, por exemplo."""
        return self._take_repeat_summary() or self._take_cycle_summary()
