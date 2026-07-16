from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from math import ceil
import re
from typing import Any

from catalog import CardCatalog


class Area(IntEnum):
    DECK = 1
    HAND = 2
    DISCARD = 3
    ACTIVE = 4
    BENCH = 5
    PRIZE = 6
    STADIUM = 7
    ENERGY = 8
    TOOL = 9
    PRE_EVOLUTION = 10
    PLAYER = 11
    LOOKING = 12


class EnergyType(IntEnum):
    COLORLESS = 0
    GRASS = 1
    FIRE = 2
    WATER = 3
    LIGHTNING = 4
    PSYCHIC = 5
    FIGHTING = 6
    DARKNESS = 7
    METAL = 8
    DRAGON = 9
    RAINBOW = 10
    TEAM_ROCKET = 11


class CardType(IntEnum):
    POKEMON = 0
    ITEM = 1
    TOOL = 2
    SUPPORTER = 3
    STADIUM = 4
    BASIC_ENERGY = 5
    SPECIAL_ENERGY = 6


class SpecialConditionType(IntEnum):
    POISON = 0
    BURN = 1
    SLEEP = 2
    PARALYZE = 3
    CONFUSE = 4


class SelectType(IntEnum):
    MAIN = 0
    CARD = 1
    ATTACHED_CARD = 2
    CARD_OR_ATTACHED_CARD = 3
    ENERGY = 4
    SKILL = 5
    ATTACK = 6
    EVOLVE = 7
    COUNT = 8
    YES_NO = 9
    SPECIAL_CONDITION = 10


class SelectContext(IntEnum):
    MAIN = 0
    SETUP_ACTIVE_POKEMON = 1
    SETUP_BENCH_POKEMON = 2
    SWITCH = 3
    TO_ACTIVE = 4
    TO_BENCH = 5
    TO_FIELD = 6
    TO_HAND = 7
    DISCARD = 8
    TO_DECK = 9
    TO_DECK_BOTTOM = 10
    TO_PRIZE = 11
    NOT_MOVE = 12
    DAMAGE_COUNTER = 13
    DAMAGE_COUNTER_ANY = 14
    DAMAGE = 15
    REMOVE_DAMAGE_COUNTER = 16
    HEAL = 17
    EVOLVES_FROM = 18
    EVOLVES_TO = 19
    DEVOLVE = 20
    ATTACH_FROM = 21
    ATTACH_TO = 22
    DETACH_FROM = 23
    LOOK = 24
    EFFECT_TARGET = 25
    DISCARD_ENERGY_CARD = 26
    DISCARD_TOOL_CARD = 27
    SWITCH_ENERGY_CARD = 28
    DISCARD_CARD_OR_ATTACHED_CARD = 29
    DISCARD_ENERGY = 30
    TO_HAND_ENERGY = 31
    TO_DECK_ENERGY = 32
    SWITCH_ENERGY = 33
    SKILL_ORDER = 34
    ATTACK = 35
    DISABLE_ATTACK = 36
    EVOLVE = 37
    DRAW_COUNT = 38
    DAMAGE_COUNTER_COUNT = 39
    REMOVE_DAMAGE_COUNTER_COUNT = 40
    IS_FIRST = 41
    MULLIGAN = 42
    ACTIVATE = 43
    FIRST_EFFECT = 44
    MORE_DEVOLVE = 45
    COIN_HEAD = 46
    AFFECT_SPECIAL_CONDITION = 47
    RECOVER_SPECIAL_CONDITION = 48


class OptionType(IntEnum):
    NUMBER = 0
    YES = 1
    NO = 2
    CARD = 3
    TOOL_CARD = 4
    ENERGY_CARD = 5
    ENERGY = 6
    PLAY = 7
    ATTACH = 8
    EVOLVE = 9
    ABILITY = 10
    DISCARD = 11
    RETREAT = 12
    ATTACK = 13
    END = 14
    SKILL = 15
    SPECIAL_CONDITION = 16


class LogType(IntEnum):
    SHUFFLE = 0
    HAS_BASIC_POKEMON = 1
    TURN_START = 2
    TURN_END = 3
    DRAW = 4
    DRAW_REVERSE = 5
    MOVE_CARD = 6
    MOVE_CARD_REVERSE = 7
    SWITCH = 8
    CHANGE = 9
    PLAY = 10
    ATTACH = 11
    EVOLVE = 12
    DEVOLVE = 13
    MOVE_ATTACHED = 14
    ATTACK = 15
    HP_CHANGE = 16
    POISONED = 17
    BURNED = 18
    ASLEEP = 19
    PARALYZED = 20
    CONFUSED = 21
    COIN = 22
    RESULT = 23


# These aliases make the local names easy to map back to cg/api.py names.
AreaType = Area


@dataclass(frozen=True)
class CardRef:
    id: int
    serial: int | None
    player_index: int | None
    area: int | None
    index: int | None


@dataclass(frozen=True)
class PokemonRef(CardRef):
    hp: int
    max_hp: int
    appear_this_turn: bool
    energies: tuple[int, ...]
    energy_card_ids: tuple[int, ...]
    tool_ids: tuple[int, ...]
    pre_evolution_ids: tuple[int, ...]
    energy_cards: tuple[CardRef, ...] = ()

    @property
    def has_psychic_energy(self) -> bool:
        return (
            int(EnergyType.PSYCHIC) in self.energies
            or any(card_id in (5, 19) for card_id in self.energy_card_ids)
        )

    @property
    def energy_card_serials(self) -> tuple[int | None, ...]:
        return tuple(card.serial for card in self.energy_cards)


@dataclass(frozen=True)
class LegalOption:
    position: int
    type: int
    raw: dict[str, Any]
    card_id: int | None
    card_serial: int | None
    source: PokemonRef | None
    target: PokemonRef | None
    attack_id: int | None

    @property
    def energy_index(self) -> int | None:
        value = self.raw.get("energyIndex")
        return None if value is None else int(value)

    @property
    def count(self) -> int | None:
        value = self.raw.get("count")
        return None if value is None else int(value)

    @property
    def tool_index(self) -> int | None:
        value = self.raw.get("toolIndex")
        return None if value is None else int(value)


@dataclass(frozen=True)
class GameView:
    raw: dict[str, Any]
    select: dict[str, Any]
    current: dict[str, Any]
    own_index: int
    own: dict[str, Any]
    opponent: dict[str, Any]
    options: tuple[LegalOption, ...]
    catalog: CardCatalog

    @classmethod
    def from_observation(
        cls, raw: dict[str, Any], catalog: CardCatalog | None = None
    ) -> "GameView":
        current = raw["current"]
        own_index = int(current["yourIndex"])
        select = raw.get("select") or {}
        catalog = catalog or CardCatalog.empty()
        players = current["players"]
        shell = cls(
            raw, select, current, own_index, players[own_index],
            players[1 - own_index], (), catalog,
        )
        options = tuple(
            shell._resolve_option(position, option)
            for position, option in enumerate(select.get("option") or [])
        )
        return cls(
            raw, select, current, own_index, players[own_index],
            players[1 - own_index], options, catalog,
        )

    @property
    def turn_player_index(self) -> int | None:
        turn = int(self.current.get("turn", 0))
        first = int(self.current.get("firstPlayer", -1))
        if turn <= 0 or first not in (0, 1):
            return None
        return first if turn % 2 == 1 else 1 - first

    @property
    def is_own_turn(self) -> bool:
        return self.turn_player_index == self.own_index

    @property
    def own_turn_number(self) -> int:
        turn = int(self.current.get("turn", 0))
        first = int(self.current.get("firstPlayer", -1))
        if turn <= 0 or first not in (0, 1):
            return 0
        first_own_turn = 1 if self.own_index == first else 2
        if turn < first_own_turn:
            return 0
        return ((turn - first_own_turn) // 2) + 1

    @property
    def active(self) -> PokemonRef | None:
        return self._pokemon_for_area(Area.ACTIVE, 0, self.own_index)

    @property
    def bench(self) -> tuple[PokemonRef, ...]:
        return self._pokemon_list(Area.BENCH, self.own_index)

    @property
    def field(self) -> tuple[PokemonRef, ...]:
        return self._field_for_player(self.own_index)

    @property
    def own_active(self) -> PokemonRef | None:
        return self.active

    @property
    def own_bench(self) -> tuple[PokemonRef, ...]:
        return self.bench

    @property
    def own_field(self) -> tuple[PokemonRef, ...]:
        return self.field

    @property
    def opponent_active(self) -> PokemonRef | None:
        return self._pokemon_for_area(Area.ACTIVE, 0, 1 - self.own_index)

    @property
    def opponent_bench(self) -> tuple[PokemonRef, ...]:
        return self._pokemon_list(Area.BENCH, 1 - self.own_index)

    @property
    def opponent_field(self) -> tuple[PokemonRef, ...]:
        return self._field_for_player(1 - self.own_index)

    @property
    def hand_ids(self) -> tuple[int, ...]:
        return tuple(int(card["id"]) for card in (self.own.get("hand") or []))

    @property
    def hand_size(self) -> int:
        return int(self.own.get("handCount", len(self.hand_ids)))

    @property
    def looking(self) -> tuple[CardRef, ...]:
        return tuple(
            self._card_ref(card, Area.LOOKING, self.own_index, index)
            for index, card in enumerate(self.current.get("looking") or [])
            if card is not None
        )

    @property
    def looking_ids(self) -> tuple[int, ...]:
        return tuple(card.id for card in self.looking)

    @property
    def required_hand_for_active_ko(self) -> int | None:
        active = self.opponent_active
        return None if active is None else ceil(active.hp / 20)

    @property
    def eligible_abras(self) -> tuple[PokemonRef, ...]:
        return tuple(
            pokemon for pokemon in self.field
            if pokemon.id == 741 and not pokemon.appear_this_turn
        )

    def field_count_after_return(self, serial: int | None) -> int:
        count = len(self.field)
        return max(0, count - 1) if any(p.serial == serial for p in self.field) else count

    def has_psychic_energy(self, pokemon: PokemonRef | None = None) -> bool:
        if pokemon is not None:
            return pokemon.has_psychic_energy
        return any(p.has_psychic_energy for p in self.field)

    @property
    def has_immediate_draw_option(self) -> bool:
        for option in self.options:
            if option.type not in (OptionType.ABILITY, OptionType.SKILL, OptionType.ATTACH):
                continue
            if option.card_id == 140:
                return True
            if (
                option.type == OptionType.ABILITY
                and option.card_id == 66
                and option.source is not None
                and self.field_count_after_return(option.source.serial) >= 2
            ):
                return True
            if (
                option.type == OptionType.ATTACH
                and option.card_id == 13
                and option.target is not None
                and option.target.id == 305
                and not option.target.appear_this_turn
                and 66 in self.hand_ids
                and any(
                    pokemon.id in (741, 742, 743)
                    and pokemon.has_psychic_energy
                    for pokemon in self.field
                )
            ):
                return True
        return False

    @property
    def complete_known_deck_ids(self) -> tuple[int, ...] | None:
        deck = self.select.get("deck")
        if deck is None or len(deck) != int(self.own.get("deckCount", 0)):
            return None
        return tuple(int(card["id"]) for card in deck if card is not None)

    @property
    def own_non_prize_card_ids(self) -> tuple[int, ...]:
        return self._visible_card_ids(self.own, self.own_index)

    @property
    def own_prize_count(self) -> int:
        return len(self.own.get("prize") or [])

    @property
    def opponent_public_card_ids(self) -> set[int]:
        field_ids = {
            card_id for pokemon in self.opponent_field
            for card_id in self._pokemon_card_ids(pokemon)
        }
        return field_ids | self.opponent_public_stadium_ids

    @property
    def opponent_public_stadium_ids(self) -> set[int]:
        opponent_index = 1 - self.own_index
        return {
            int(card["id"])
            for card in (self.current.get("stadium") or [])
            if card is not None
            and int(card.get("playerIndex", -1)) == opponent_index
        }

    @property
    def opponent_discard_ids(self) -> set[int]:
        return {int(card["id"]) for card in (self.opponent.get("discard") or [])}

    @property
    def opponent_public_ace_spec_ids(self) -> set[int]:
        visible = self.opponent_public_card_ids | self.opponent_discard_ids
        return {
            card_id for card_id in visible
            if (meta := self.catalog.card(card_id)) is not None and meta.ace_spec
        }

    @property
    def opponent_has_public_bench_damage_attack(self) -> bool:
        """Whether Flower Curtain can protect a rule-boxless Bench from an attack."""
        return any(
            self._is_bench_damage_text(text)
            for text in self._opponent_attack_texts()
        )

    @property
    def opponent_has_public_bench_counter_effect(self) -> bool:
        return any(
            self._is_bench_counter_text(text)
            for text in self._opponent_attack_texts() + self._opponent_skill_texts()
        )

    @property
    def opponent_has_public_self_ko_ability(self) -> bool:
        return any(
            self._is_self_ko_text(text)
            for text in self._opponent_skill_texts()
        )

    def _resolve_option(self, position: int, option: dict[str, Any]) -> LegalOption:
        option_type = int(option["type"])
        owner = int(option.get("playerIndex", self.own_index))
        source = self._pokemon_for_area(option.get("area"), option.get("index"), owner)
        raw_card = self._raw_card_for_option(option, source)
        card_id = None
        card_serial = None
        if raw_card is not None:
            card_id = int(raw_card["id"])
            card_serial = raw_card.get("serial")
        elif option.get("cardId") is not None:
            card_id = int(option["cardId"])
            card_serial = option.get("serial")

        target = None
        if option.get("inPlayArea") is not None:
            # CABT has no inPlayPlayerIndex: ATTACH/EVOLVE targets are ours.
            target = self._pokemon_for_area(
                option.get("inPlayArea"), option.get("inPlayIndex"), self.own_index
            )
        attack_id = option.get("attackId")
        return LegalOption(
            position=position,
            type=option_type,
            raw=option,
            card_id=card_id,
            card_serial=None if card_serial is None else int(card_serial),
            source=source,
            target=target,
            attack_id=None if attack_id is None else int(attack_id),
        )

    def _raw_card_for_option(
        self, option: dict[str, Any], source: PokemonRef | None
    ) -> dict[str, Any] | None:
        option_type = int(option["type"])
        if option_type == int(OptionType.PLAY):
            return self._item_at(self.own.get("hand"), option.get("index"))
        if option_type in (int(OptionType.ENERGY_CARD), int(OptionType.ENERGY)) and source is not None:
            raw_pokemon = self._raw_pokemon_for_area(
                option.get("area"), option.get("index"),
                int(option.get("playerIndex", self.own_index)),
            )
            return self._item_at(raw_pokemon.get("energyCards") if raw_pokemon else None,
                                 option.get("energyIndex"))
        if option_type == int(OptionType.TOOL_CARD) and source is not None:
            raw_pokemon = self._raw_pokemon_for_area(
                option.get("area"), option.get("index"),
                int(option.get("playerIndex", self.own_index)),
            )
            return self._item_at(raw_pokemon.get("tools") if raw_pokemon else None,
                                 option.get("toolIndex"))
        if option_type == int(OptionType.CARD) and source is not None:
            return {"id": source.id, "serial": source.serial}
        if option_type in (int(OptionType.ABILITY), int(OptionType.DISCARD)) and source is not None:
            return {"id": source.id, "serial": source.serial}
        return self._card_at_area(
            option.get("area"), option.get("index"),
            int(option.get("playerIndex", self.own_index)),
        )

    def _card_at_area(self, area: int | None, index: int | None, player: int) -> dict[str, Any] | None:
        if area is None or index is None:
            return None
        area_value = int(area)
        if area_value == int(Area.DECK):
            return self._item_at(self.select.get("deck"), index)
        if area_value == int(Area.HAND):
            players_hand = self.current["players"][player].get("hand")
            return self._item_at(players_hand, index)
        if area_value == int(Area.DISCARD):
            return self._item_at(self.current["players"][player].get("discard"), index)
        if area_value == int(Area.PRIZE):
            return self._item_at(self.current["players"][player].get("prize"), index)
        if area_value == int(Area.LOOKING):
            return self._item_at(self.current.get("looking"), index)
        if area_value == int(Area.STADIUM):
            return self._item_at(self.current.get("stadium"), index)
        return None

    def _raw_pokemon_for_area(
        self, area: int | None, index: int | None, player: int
    ) -> dict[str, Any] | None:
        if area is None or index is None or player not in (0, 1):
            return None
        player_state = self.current["players"][player]
        cards: list[Any]
        if int(area) == int(Area.ACTIVE):
            cards = player_state.get("active") or []
        elif int(area) == int(Area.BENCH):
            cards = player_state.get("bench") or []
        else:
            return None
        item = self._item_at(cards, index)
        return item if isinstance(item, dict) else None

    def _pokemon_for_area(
        self, area: int | None, index: int | None, player: int
    ) -> PokemonRef | None:
        raw_pokemon = self._raw_pokemon_for_area(area, index, player)
        if raw_pokemon is None:
            return None
        return self._pokemon_ref(raw_pokemon, int(area), int(index))

    def _pokemon_list(self, area: Area, player: int) -> tuple[PokemonRef, ...]:
        raw_list = self.current["players"][player].get("bench") or []
        return tuple(
            self._pokemon_ref(pokemon, int(area), index)
            for index, pokemon in enumerate(raw_list)
            if pokemon is not None
        )

    def _field_for_player(self, player: int) -> tuple[PokemonRef, ...]:
        active = self._pokemon_for_area(Area.ACTIVE, 0, player)
        bench = self._pokemon_list(Area.BENCH, player)
        return (() if active is None else (active,)) + bench

    def _pokemon_ref(self, pokemon: dict[str, Any], area: int, index: int) -> PokemonRef:
        player = (
            self.own_index
            if pokemon.get("playerIndex") is None
            else int(pokemon["playerIndex"])
        )
        energy_cards = tuple(
            self._card_ref(card, Area.ENERGY, player, energy_index)
            for energy_index, card in enumerate(pokemon.get("energyCards") or [])
            if card is not None
        )
        return PokemonRef(
            id=int(pokemon["id"]),
            serial=None if pokemon.get("serial") is None else int(pokemon["serial"]),
            player_index=None if pokemon.get("playerIndex") is None
            else int(pokemon["playerIndex"]),
            area=area,
            index=index,
            hp=int(pokemon.get("hp", 0)),
            max_hp=int(pokemon.get("maxHp", pokemon.get("hp", 0))),
            appear_this_turn=bool(pokemon.get("appearThisTurn", False)),
            energies=tuple(int(energy) for energy in (pokemon.get("energies") or [])),
            energy_card_ids=tuple(card.id for card in energy_cards),
            tool_ids=tuple(
                int(card["id"]) for card in (pokemon.get("tools") or [])
                if card is not None
            ),
            pre_evolution_ids=tuple(
                int(card["id"]) for card in (pokemon.get("preEvolution") or [])
                if card is not None
            ),
            energy_cards=energy_cards,
        )

    @staticmethod
    def _item_at(items: Any, index: int | None) -> dict[str, Any] | None:
        if items is None or index is None:
            return None
        try:
            item = items[int(index)]
        except (IndexError, TypeError, ValueError):
            return None
        return item if isinstance(item, dict) else None

    @staticmethod
    def _card_ref(card: dict[str, Any], area: Area, player: int, index: int) -> CardRef:
        return CardRef(
            id=int(card["id"]),
            serial=None if card.get("serial") is None else int(card["serial"]),
            player_index=player if card.get("playerIndex") is None else int(card["playerIndex"]),
            area=int(area),
            index=index,
        )

    def _visible_card_ids(self, player_state: dict[str, Any], player: int) -> tuple[int, ...]:
        ids: list[int] = []
        ids.extend(
            int(card["id"])
            for card in (player_state.get("hand") or [])
            if card is not None
        )
        ids.extend(
            int(card["id"])
            for card in (player_state.get("discard") or [])
            if card is not None
        )
        for pokemon in self._field_for_player(player):
            ids.append(pokemon.id)
            ids.extend(pokemon.pre_evolution_ids)
            ids.extend(pokemon.energy_card_ids)
            ids.extend(pokemon.tool_ids)
        ids.extend(
            int(card["id"])
            for card in (self.current.get("stadium") or [])
            if card is not None and int(card.get("playerIndex", -1)) == player
        )
        return tuple(ids)

    @staticmethod
    def _pokemon_card_ids(pokemon: PokemonRef) -> set[int]:
        return {
            pokemon.id,
            *pokemon.energy_card_ids,
            *pokemon.tool_ids,
            *pokemon.pre_evolution_ids,
        }

    def _opponent_attack_texts(self) -> tuple[str, ...]:
        return tuple(
            text
            for pokemon in self.opponent_field
            for attack_id in (self.catalog.card(pokemon.id).attacks
                              if self.catalog.card(pokemon.id) is not None else ())
            if (text := self.catalog.attack_text.get(int(attack_id))) is not None
        )

    def _opponent_skill_texts(self) -> tuple[str, ...]:
        return tuple(
            text
            for pokemon in self.opponent_field
            for text in self._skill_texts(pokemon.id)
        )

    def _skill_texts(self, card_id: int) -> tuple[str, ...]:
        meta = self.catalog.card(card_id)
        return () if meta is None else meta.skill_texts

    @staticmethod
    def _is_bench_damage_text(text: str) -> bool:
        lower = text.lower().replace("’", "'")
        match = re.search(r"\bdamage to\s+([^.]+)", lower)
        if match is None:
            return False
        target = match.group(1)
        if re.search(r"\{(?:ex|v)\}", target):
            return False
        return (
            GameView._is_opponent_bench_target(target)
            or GameView._is_contextual_opponent_target(
                target, lower[:match.start()])
        )

    @staticmethod
    def _is_bench_counter_text(text: str) -> bool:
        lower = text.lower().replace("’", "'")
        match = re.search(
            r"\b(?:put|place|move|double)\b[^.]*?\bdamage counters?\b"
            r"[^.]*?\b(?:on|to)\b\s+([^.]+)",
            lower,
        )
        if match is None:
            return False
        target = match.group(1)
        return (
            GameView._is_opponent_bench_target(target)
            or GameView._is_contextual_opponent_target(
                target, lower[:match.start()])
        )

    @staticmethod
    def _is_opponent_bench_target(target: str) -> bool:
        lower = target.lower().replace("’", "'")
        return (
            "opponent's benched" in lower
            or "opponent's pokemon" in lower
            or "opponent's pokémon" in lower
            or ("benched" in lower and "both yours and your opponent's" in lower)
        )

    @staticmethod
    def _is_contextual_opponent_target(target: str, context: str) -> bool:
        target_lower = target.lower().replace("’", "'")
        context_lower = context.lower().replace("’", "'")
        return bool(
            re.match(
                r"(?:it|that (?:pokemon|pokémon)|each of them)\b",
                target_lower,
            )
            and re.search(
                r"\b(?:choose \d+ of|for each of) your opponent's "
                r"(?:pokemon|pokémon)\b",
                context_lower,
            )
        )

    @staticmethod
    def _is_self_ko_text(text: str) -> bool:
        lower = text.lower()
        return bool(re.search(
            r"\b(?:knock out this (?:pokemon|pokémon)|"
            r"if you use this ability,\s*this (?:pokemon|pokémon) "
            r"is knocked out)\b",
            lower,
        ))
