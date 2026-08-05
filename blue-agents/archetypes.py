"""Fixed playing styles, chosen per slot instead of rolled per run.

Personality used to be a base profile plus a ±10 roll every execution. That is
fine for flavour and terrible for comparing runs: CARON once rolled a collector
score below every capture threshold and finished the journey with a single
Pokémon, which looked like a bug in the capture policy and was really the dice.

An archetype is the same four traits with no roll, plus the one thing the
traits could never express: what the trainer does with a wild encounter it
could catch. Three trainers with the same map knowledge and different answers
to that question are the experiment worth watching.
"""

from __future__ import annotations

# Traits stay in the existing [meta, exploration, collector, mission_focus]
# order so the observation vector and the panel keep their meaning.
ARCHETYPES = {
    "completionist": {
        "label": "Completista",
        "traits": {
            "meta_score": 60,
            "exploration": 85,
            "collector": 95,
            "mission_focus": 40,
        },
        # Bulbasaur: Sleep Powder e Leech Seed deixam encontro longo barato,
        # que é exatamente o que um completista faz o tempo todo.
        "starter_preference": 0,
        "capture_stance": "every_new_species",
        "summary": (
            "Quer registrar tudo o que aparece. Captura qualquer espécie nova, "
            "mesmo com o time cheio — o excedente vai para o PC."
        ),
    },
    "speedrunner": {
        "label": "Rushador",
        "traits": {
            "meta_score": 55,
            "exploration": 35,
            "collector": 15,
            "mission_focus": 95,
        },
        # Bulbasaur de novo, e por outro motivo: Brock e Misty, os dois
        # primeiros freios da corrida, são fracos contra grama.
        "starter_preference": 0,
        "capture_stance": "only_when_needed",
        "summary": (
            "História acima de tudo, mas não com um time de iniciais: captura "
            "um reserva enquanto o time é pequeno e qualquer Pokémon forte o "
            "bastante para limpar objetivo mais rápido."
        ),
    },
    "team_builder": {
        "label": "Construtor de time",
        "traits": {
            "meta_score": 95,
            "exploration": 55,
            "collector": 65,
            "mission_focus": 70,
        },
        # Squirtle: a base defensiva mais sólida para montar time em volta.
        "starter_preference": 2,
        "capture_stance": "team_value_only",
        "summary": (
            "Quer um time completo e forte. Captura o que ocupa vaga ou "
            "melhora o time, e ignora o que não muda a linha de frente."
        ),
    },

    "fire_dragon": {
        "label": "Fogo e dragão",
        "traits": {
            "meta_score": 85,
            "exploration": 60,
            "collector": 55,
            "mission_focus": 65,
        },
        # Charmander: o time inteiro é construído em volta do Charizard.
        "starter_preference": 1,
        "capture_stance": "preferred_types",
        "preferred_types": ("fire", "dragon"),
        "summary": (
            "Só quer fogo e dragão no time. É a corrida mais difícil de Kanto: "
            "Brock e Misty são justamente os dois primeiros ginásios, e Dratini "
            "só aparece muito depois."
        ),
    },
}

DEFAULT_ARCHETYPE = "team_builder"

# Below this the party is not a team yet, it is a single point of failure. Even
# the speedrunner keeps a spare: a whiteout costs far more than a Poké Ball.
MINIMUM_BACKUP_PARTY = 2

# The speedrunner is focused, not stubborn. Skipping every catch ends the run
# with nothing but starters, and a gym that walls a lone starter costs far more
# turns than the catch would have. Above this strategic value the encounter is
# not a distraction — Abra, Gastly, Lapras, Snorlax and the like clear
# objectives faster than the story can be rushed without them.
RUSH_POWER_VALUE = 78


def archetype_names():
    return tuple(ARCHETYPES)


def get_archetype(name):
    """Return an archetype definition, falling back to the default by name."""
    return ARCHETYPES.get(str(name or "").strip().lower(), ARCHETYPES[DEFAULT_ARCHETYPE])


def archetype_for_slot(slot):
    """Archetype of a roster slot, spreading the three styles over the slots.

    A roster written before archetypes existed has none, so the slot index
    picks one and two trainers never end up playing the same way by accident.
    """
    declared = str(slot.get("archetype") or "").strip().lower()
    if declared in ARCHETYPES:
        return declared
    names = archetype_names()
    return names[int(slot.get("slot", 0)) % len(names)]
