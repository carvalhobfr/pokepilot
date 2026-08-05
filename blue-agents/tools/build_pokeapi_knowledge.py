#!/usr/bin/env python3
"""Build the map knowledge the archetypes need, from PokéAPI.

Two tables the project never had:

* ``knowledge/maps/encounters.json`` — which species can be met in each area of
  Pokémon Blue, so "faltam 3 nesta área" is a fact and not a guess. The
  completionist is meaningless without it.
* ``knowledge/gyms.json`` — each gym's type, its leader and what beats it, so a
  trainer can ask "do I have an answer for Brock?" before walking in.

Run it when the tables need refreshing; the journey never calls the network.
PokéAPI rejects the default urllib User-Agent with 403, hence the explicit one.

    ./blue-agents/tools/build_pokeapi_knowledge.py --areas viridian-forest-area
    ./blue-agents/tools/build_pokeapi_knowledge.py            # tudo
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://pokeapi.co/api/v2"
USER_AGENT = "poke-ai-2026/1.0 (knowledge builder)"
VERSION = "blue"

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"

# Kanto gyms in badge order. The leader and the city are stable facts; the type
# chart comes from the API so the "what beats this" list is never hand-guessed.
GYMS = [
    {"order": 1, "city": "Pewter City", "map_id": 54, "leader": "Brock", "type": "rock"},
    {"order": 2, "city": "Cerulean City", "map_id": 65, "leader": "Misty", "type": "water"},
    {"order": 3, "city": "Vermilion City", "map_id": 92, "leader": "Lt. Surge", "type": "electric"},
    {"order": 4, "city": "Celadon City", "map_id": 134, "leader": "Erika", "type": "grass"},
    {"order": 5, "city": "Fuchsia City", "map_id": 157, "leader": "Koga", "type": "poison"},
    {"order": 6, "city": "Saffron City", "map_id": 178, "leader": "Sabrina", "type": "psychic"},
    {"order": 7, "city": "Cinnabar Island", "map_id": 166, "leader": "Blaine", "type": "fire"},
    {"order": 8, "city": "Viridian City", "map_id": 45, "leader": "Giovanni", "type": "ground"},
]


def fetch(url, retries=3, pause=1.0):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(pause * (attempt + 1))
    raise RuntimeError("unreachable")


def blue_encounters(area_name):
    """Species reachable in one area in Pokémon Blue, with their level range."""
    area = fetch(f"{API}/location-area/{area_name}/")
    species = {}
    for encounter in area["pokemon_encounters"]:
        details = [
            detail for detail in encounter["version_details"]
            if detail["version"]["name"] == VERSION
        ]
        if not details:
            continue
        levels = [
            entry["min_level"]
            for detail in details for entry in detail["encounter_details"]
        ] + [
            entry["max_level"]
            for detail in details for entry in detail["encounter_details"]
        ]
        name = encounter["pokemon"]["name"]
        species[name] = {
            "species_id": int(encounter["pokemon"]["url"].rstrip("/").split("/")[-1]),
            "min_level": min(levels) if levels else None,
            "max_level": max(levels) if levels else None,
        }
    return dict(sorted(species.items()))


def kanto_area_names():
    """Every location area of the Kanto region, in API order."""
    region = fetch(f"{API}/region/kanto/")
    names = []
    for location in region["locations"]:
        detail = fetch(location["url"])
        for area in detail["areas"]:
            names.append(area["name"])
    return names


def type_answers(type_name):
    """Types that hit this one hard, and the ones it resists."""
    payload = fetch(f"{API}/type/{type_name}/")
    relations = payload["damage_relations"]
    return {
        "weak_to": sorted(entry["name"] for entry in relations["double_damage_from"]),
        "resists": sorted(entry["name"] for entry in relations["half_damage_from"]),
        "immune_to": sorted(entry["name"] for entry in relations["no_damage_from"]),
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--areas", nargs="*",
        help="Location areas to fetch; default is the whole Kanto region",
    )
    parser.add_argument("--skip-gyms", action="store_true")
    parser.add_argument("--skip-encounters", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    if not args.skip_gyms:
        gyms = []
        for gym in GYMS:
            gyms.append({**gym, "counters": type_answers(gym["type"])})
            print(f"ginásio {gym['order']} {gym['leader']}: {gym['type']}")
        write_json(KNOWLEDGE_DIR / "gyms.json", {"version": VERSION, "gyms": gyms})

    if not args.skip_encounters:
        area_names = args.areas or kanto_area_names()
        areas = {}
        for name in area_names:
            try:
                species = blue_encounters(name)
            except urllib.error.HTTPError as error:
                print(f"pulando {name}: HTTP {error.code}")
                continue
            if not species:
                continue
            areas[name] = species
            print(f"{name}: {len(species)} espécies")
        write_json(
            KNOWLEDGE_DIR / "maps" / "encounters.json",
            {"version": VERSION, "source": "pokeapi.co", "areas": areas},
        )


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    temporary.replace(path)
    print(f"escrito {path.relative_to(KNOWLEDGE_DIR.parent)}")


if __name__ == "__main__":
    main()
