"""ラムダから次番攻撃を固定できるかを公開情報だけで判定する。"""

from __future__ import annotations

from dataclasses import dataclass

from cards import CardId
from memory import AgentMemory, card_may_be_in_deck
from model import Area, GameView, PokemonRef
from rules.board_plan import (
    first_turn_active_survives,
    full_board_plan,
    next_turn_surviving_field,
)


_PSYCHIC_IDS = frozenset({
    int(CardId.BASIC_PSYCHIC),
    int(CardId.TELEPATH_PSYCHIC_ENERGY),
})
_RETREAT_ENERGY_IDS = frozenset({
    *_PSYCHIC_IDS,
    int(CardId.ENRICHING_ENERGY),
})
_ONE_RETREAT_IDS = frozenset({
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
    int(CardId.DUNSPARCE),
    int(CardId.FEZANDIPITI_EX),
})
_EVOLUTION_SEARCHER_IDS = frozenset({
    int(CardId.POKE_PAD),
    int(CardId.HILDA),
    int(CardId.DAWN),
})


@dataclass(frozen=True)
class PetrelCriticalPath:
    surviving_abra_count: int
    powered_surviving_abra_count: int
    target_serial: int | None
    alakazam_secured: bool
    attack_energy_secured: bool
    attack_position_secured: bool
    candy_in_hand: bool
    candy_may_be_in_deck: bool
    alternate_petrel_count: int
    candy_zero_slack: bool
    next_turn_candy_attack_locked: bool
    candy_status: str
    setup_trainer_id: int | None
    setup_status: str

    def metadata(self) -> tuple[tuple[str, int | str | bool], ...]:
        return (
            ("surviving_abra_count", int(self.surviving_abra_count)),
            (
                "powered_surviving_abra_count",
                int(self.powered_surviving_abra_count),
            ),
            (
                "critical_target_serial",
                -1 if self.target_serial is None else int(self.target_serial),
            ),
            ("alakazam_secured", bool(self.alakazam_secured)),
            ("attack_energy_secured", bool(self.attack_energy_secured)),
            ("attack_position_secured", bool(self.attack_position_secured)),
            ("candy_in_hand", bool(self.candy_in_hand)),
            ("candy_may_be_in_deck", bool(self.candy_may_be_in_deck)),
            ("alternate_petrel_count", int(self.alternate_petrel_count)),
            ("candy_zero_slack", bool(self.candy_zero_slack)),
            (
                "next_turn_candy_attack_locked",
                bool(self.next_turn_candy_attack_locked),
            ),
            ("candy_status", self.candy_status),
            (
                "setup_trainer_id",
                -1 if self.setup_trainer_id is None
                else int(self.setup_trainer_id),
            ),
            ("setup_status", self.setup_status),
        )


def _secured_evolution_card(
    view: GameView,
    memory: AgentMemory,
    target: CardId,
) -> bool:
    if int(target) in view.hand_ids:
        return True
    return (
        card_may_be_in_deck(view, memory, target)
        and any(
            searcher_id in view.hand_ids
            for searcher_id in _EVOLUTION_SEARCHER_IDS
        )
    )


def _pokemon_has_any_energy(pokemon: PokemonRef) -> bool:
    return bool(
        pokemon.energies
        or pokemon.energy_card_ids
        or pokemon.energy_cards
    )


def _movement_modes(
    view: GameView,
    pokemon: PokemonRef,
) -> tuple[str, ...]:
    """対象を次番の攻撃位置へ出す、公開情報上の移動候補を返す。"""

    if int(pokemon.area) == int(Area.ACTIVE):
        return ("already_active",)
    if not first_turn_active_survives(view):
        return ("forced_promotion",)
    active = view.active
    if active is None or int(active.id) == int(CardId.DUDUNSPARCE):
        return ("free_promotion",)

    modes: list[str] = []
    if int(active.id) == int(CardId.DUNSPARCE):
        modes.append("dudunsparce")
    if int(active.id) in _ONE_RETREAT_IDS:
        modes.append(
            "retreat_attached"
            if _pokemon_has_any_energy(active)
            else "retreat_attach"
        )
    return tuple(modes)


def _route_supporters(
    view: GameView,
    pokemon: PokemonRef,
    memory: AgentMemory,
    *,
    movement_mode: str,
    require_alakazam: bool,
    require_attack_energy: bool,
    allow_supporter: bool = True,
) -> tuple[int | None, ...]:
    """同じ検索札・手貼り権を重複利用しない成立supporterを返す。"""

    evolution_requirements: list[CardId] = []
    if require_alakazam and int(CardId.ALAKAZAM) not in view.hand_ids:
        evolution_requirements.append(CardId.ALAKAZAM)
    if (
        movement_mode == "dudunsparce"
        and int(CardId.DUDUNSPARCE) not in view.hand_ids
    ):
        evolution_requirements.append(CardId.DUDUNSPARCE)
    if any(
        not card_may_be_in_deck(view, memory, card_id)
        for card_id in evolution_requirements
    ):
        return ()

    needs_attack_attach = (
        require_attack_energy
        and not view.has_psychic_energy(pokemon)
    )
    needs_retreat_attach = movement_mode == "retreat_attach"
    # 1ターンの手貼り権は1回だけ。前と攻撃役の両方へは貼れない。
    if needs_attack_attach and needs_retreat_attach:
        return ()

    required_energy_ids: frozenset[int] | None
    if needs_attack_attach:
        required_energy_ids = _PSYCHIC_IDS
    elif needs_retreat_attach:
        required_energy_ids = _RETREAT_ENERGY_IDS
    else:
        required_energy_ids = None

    energy_in_hand = (
        required_energy_ids is None
        or any(card_id in required_energy_ids for card_id in view.hand_ids)
    )
    energy_searchable = (
        required_energy_ids is not None
        and any(
            card_may_be_in_deck(view, memory, card_id)
            for card_id in required_energy_ids
        )
    )
    poke_pad_count = view.hand_ids.count(int(CardId.POKE_PAD))
    supporter_ids: tuple[int | None, ...] = (
        None,
        *(
            (int(CardId.HILDA),)
            if allow_supporter and int(CardId.HILDA) in view.hand_ids
            else ()
        ),
        *(
            (int(CardId.DAWN),)
            if allow_supporter and int(CardId.DAWN) in view.hand_ids
            else ()
        ),
    )

    secured: list[int | None] = []
    for supporter_id in supporter_ids:
        remaining = len(evolution_requirements)
        energy_secured = energy_in_hand
        if supporter_id == int(CardId.HILDA):
            energy_secured = energy_secured or energy_searchable
            # HILDAは進化札とエネルギーを別画面で各1枚取れる。
            remaining = max(0, remaining - 1)
        elif supporter_id == int(CardId.DAWN):
            # DAWNはstage1とstage2を別画面で各1枚取れる。
            remaining = 0
        if energy_secured and remaining <= poke_pad_count:
            secured.append(supporter_id)
    return tuple(secured)


def _joint_attack_route_secured(
    view: GameView,
    pokemon: PokemonRef,
    memory: AgentMemory,
) -> tuple[tuple[str, tuple[int | None, ...]], ...]:
    """同じ個体の進化・エネルギー・移動を同時に満たす経路を返す。"""

    return tuple(
        (movement_mode, supporters)
        for movement_mode in _movement_modes(view, pokemon)
        if (
            supporters := _route_supporters(
                view,
                pokemon,
                memory,
                movement_mode=movement_mode,
                require_alakazam=True,
                require_attack_energy=True,
            )
        )
    )


def _position_secured(
    view: GameView,
    pokemon: PokemonRef,
    memory: AgentMemory,
) -> bool:
    return any(
        _route_supporters(
            view,
            pokemon,
            memory,
            movement_mode=movement_mode,
            require_alakazam=False,
            require_attack_energy=False,
        )
        for movement_mode in _movement_modes(view, pokemon)
    )


def _powered_survivor_count(
    view: GameView,
    surviving: tuple[PokemonRef, ...],
    memory: AgentMemory,
) -> int:
    powered = sum(
        int(view.has_psychic_energy(pokemon))
        for pokemon in surviving
    )
    if powered >= len(surviving):
        return powered
    direct = any(card_id in _PSYCHIC_IDS for card_id in view.hand_ids)
    searchable = (
        int(CardId.HILDA) in view.hand_ids
        and any(
            card_may_be_in_deck(view, memory, card_id)
            for card_id in _PSYCHIC_IDS
        )
    )
    return powered + int(direct or searchable)


def _setup_route(
    view: GameView,
    memory: AgentMemory,
) -> tuple[int | None, str]:
    plan = full_board_plan(view)
    bench_max = int(view.own.get("benchMax", 5))
    if plan.complete or plan.open_slots <= 0 or len(view.bench) >= bench_max:
        return None, "board_full"
    target_ids = tuple(
        card_id
        for card_id in sorted(plan.target_basic_ids)
        if card_id in {int(CardId.ABRA), int(CardId.DUNSPARCE)}
        and card_may_be_in_deck(view, memory, card_id)
    )
    if not target_ids:
        return None, "no_target_basic"
    if card_may_be_in_deck(view, memory, CardId.BUDDY_BUDDY_POFFIN):
        return int(CardId.BUDDY_BUDDY_POFFIN), "poffin"
    if card_may_be_in_deck(view, memory, CardId.POKE_PAD):
        return int(CardId.POKE_PAD), "poke_pad"
    return None, "no_setup_trainer"


def evaluate_petrel_critical_path(
    view: GameView,
    memory: AgentMemory,
) -> PetrelCriticalPath:
    surviving = tuple(
        pokemon
        for pokemon in next_turn_surviving_field(view)
        if int(pokemon.id) == int(CardId.ABRA)
    )
    powered_count = _powered_survivor_count(view, surviving, memory)
    position_secured = any(
        _position_secured(view, pokemon, memory)
        for pokemon in surviving
    )
    attack_routes = tuple(
        (pokemon, movement_mode, supporters)
        for pokemon in surviving
        for movement_mode, supporters in _joint_attack_route_secured(
            view,
            pokemon,
            memory,
        )
    )
    alakazam_secured = _secured_evolution_card(
        view,
        memory,
        CardId.ALAKAZAM,
    )
    candy_in_hand = int(CardId.RARE_CANDY) in view.hand_ids
    candy_may_be_in_deck = card_may_be_in_deck(
        view,
        memory,
        CardId.RARE_CANDY,
    )
    alternate_petrel_count = max(
        0,
        view.hand_ids.count(int(CardId.TEAM_ROCKETS_PETREL)) - 1,
    )
    supporter_free_routes = tuple(
        route
        for route in attack_routes
        if None in route[2]
    )
    alternate_petrel_can_supply_candy = bool(
        alternate_petrel_count and supporter_free_routes
    )
    target_routes = (
        supporter_free_routes
        if alternate_petrel_can_supply_candy
        else attack_routes
    )
    target = min(
        (route[0] for route in target_routes),
        key=lambda pokemon: (
            0 if int(pokemon.area) == int(Area.ACTIVE) else 1,
            10**18 if pokemon.serial is None else int(pokemon.serial),
        ),
        default=None,
    )
    candy_zero_slack = (
        not candy_in_hand
        and candy_may_be_in_deck
        and bool(attack_routes)
        and not alternate_petrel_can_supply_candy
    )

    if candy_in_hand:
        candy_status = "candy_already_in_hand"
    elif not candy_may_be_in_deck:
        candy_status = "candy_publicly_unavailable"
    elif not surviving:
        candy_status = "no_surviving_abra"
    elif not alakazam_secured:
        candy_status = "no_alakazam_route"
    elif not powered_count:
        candy_status = "no_attack_energy"
    elif not position_secured:
        candy_status = "no_attack_position"
    elif not attack_routes:
        candy_status = "resource_conflict"
    elif alternate_petrel_can_supply_candy:
        candy_status = "alternate_petrel_available"
    else:
        candy_status = "locked"

    setup_trainer_id, setup_status = _setup_route(view, memory)
    return PetrelCriticalPath(
        surviving_abra_count=len(surviving),
        powered_surviving_abra_count=powered_count,
        target_serial=None if target is None else target.serial,
        alakazam_secured=alakazam_secured,
        attack_energy_secured=bool(powered_count),
        attack_position_secured=position_secured,
        candy_in_hand=candy_in_hand,
        candy_may_be_in_deck=candy_may_be_in_deck,
        alternate_petrel_count=alternate_petrel_count,
        candy_zero_slack=candy_zero_slack,
        next_turn_candy_attack_locked=candy_status == "locked",
        candy_status=candy_status,
        setup_trainer_id=setup_trainer_id,
        setup_status=setup_status,
    )
