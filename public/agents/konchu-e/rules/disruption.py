from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from math import comb
from typing import Iterable
from enum import Enum

from cards import CardId, DECK_COUNTS
from model import (
    Area,
    LegalOption,
    OptionType,
    PokemonRef,
    SelectContext,
    SelectType,
)
from proposals import Proposal, covers
from rules.attack import (
    _blocking_energy_cards,
    _has_public_field_effect_immunity,
    _has_self_effect_immunity,
    _is_hand_power_effect_immune,
    can_hand_power_ko,
)


class DisruptionMode(str, Enum):
    NONE = "none"
    UNFAIR_ONLY = "unfair_only"
    XEROSIC = "xerosic"


def disruption_mode(memory) -> DisruptionMode:
    profile = getattr(memory, "opponent_profile", None)
    if profile is None:
        return DisruptionMode.NONE
    if getattr(profile, "uses_xerosic", None) is True:
        return DisruptionMode.XEROSIC
    if (
        getattr(profile, "uses_unfair_stamp", None) is True
        and bool(getattr(memory, "unfair_stamp_possible", False))
    ):
        return DisruptionMode.UNFAIR_ONLY
    return DisruptionMode.NONE


def bench_survival_override(view, pokemon) -> bool:
    """公開ベンチ被害で次番に失われるポケモンは温存しない。"""
    return bool(
        pokemon is not None
        and int(getattr(pokemon, "area", -1)) == int(Area.BENCH)
        and view.public_bench_damage_risk(pokemon)
    )


def _is_draw_evolution(view, option) -> bool:
    return (
        option is not None
        and int(getattr(option, "type", -1)) == int(OptionType.EVOLVE)
        and int(getattr(option, "card_id", -1)) in {
            int(CardId.KADABRA), int(CardId.ALAKAZAM)
        }
    )


@covers("PLAYBOOK-DISRUPTION-HOLD")
def should_hold_evolution(view, memory, option) -> bool:
    """クセロシキ／アンフェアスタンプ対面で進化時ドローを温存するか。"""
    if not _is_draw_evolution(view, option):
        return False
    if not can_hand_power_ko(view, require_legal_option=False):
        return False
    target = getattr(option, "target", None)
    if bench_survival_override(view, target):
        return False
    if target is not None and int(getattr(target, "id", -1)) == int(CardId.DUNSPARCE):
        return False
    mode = disruption_mode(memory)
    if mode is DisruptionMode.XEROSIC:
        return useful_xerosic_keep_count(view, memory) < 3
    if mode is DisruptionMode.UNFAIR_ONLY:
        return bool(
            view.active is not None
            and int(view.active.id) == int(CardId.ALAKAZAM)
            and any(
                int(pokemon.id) == int(CardId.ALAKAZAM)
                for pokemon in view.bench
            )
            and target is not None
            and int(getattr(target, "id", -1))
            in {int(CardId.ABRA), int(CardId.KADABRA)}
        )
    return False


@covers("PLAYBOOK-DISRUPTION-HOLD")
def should_hold_dudunsparce_ability(view, memory, option) -> bool:
    if option is None or int(getattr(option, "card_id", -1)) != int(CardId.DUDUNSPARCE):
        return False
    if not can_hand_power_ko(view, require_legal_option=False):
        return False
    source = getattr(option, "source", None)
    return disruption_mode(memory) in {DisruptionMode.XEROSIC, DisruptionMode.UNFAIR_ONLY} and not bench_survival_override(view, source)


_ALAKAZAM_SEARCH_IDS = frozenset({
    int(CardId.POKE_PAD),
    int(CardId.HILDA),
    int(CardId.DAWN),
})
_ATTACK_PSYCHIC_IDS = frozenset({
    int(CardId.BASIC_PSYCHIC),
    int(CardId.TELEPATH_PSYCHIC_ENERGY),
})
_ATTACK_LINE_CARD_IDS = (
    int(CardId.ABRA),
    int(CardId.KADABRA),
    int(CardId.ALAKAZAM),
)
_UNKNOWN_CARD_ID = -1


@dataclass(frozen=True)
class RecoveryProjection:
    guaranteed_ko: bool
    can_attack: bool
    recovered_hand: int
    ko_probability: Fraction
    continuity_score: int
    route: str

    def key(self) -> tuple[int, int, int, Fraction, int, str]:
        return (
            int(self.guaranteed_ko),
            int(self.can_attack),
            self.recovered_hand if self.can_attack else -1,
            self.ko_probability,
            self.continuity_score,
            self.route,
        )


@dataclass(frozen=True)
class EnergyBudgetProjection:
    required_attacks: int
    secured_attacks: int

    @property
    def complete(self) -> bool:
        return self.secured_attacks >= self.required_attacks

    def key(self) -> tuple[int, int]:
        return (
            int(self.complete),
            min(self.secured_attacks, self.required_attacks),
        )


@dataclass(frozen=True)
class AttackLineBudgetProjection:
    required_attackers: int
    secured_attackers: int

    @property
    def complete(self) -> bool:
        return self.secured_attackers >= self.required_attackers

    def key(self) -> tuple[int, int]:
        return (
            int(self.complete),
            min(self.secured_attackers, self.required_attackers),
        )


@dataclass(frozen=True)
class SharedBudgetProjection:
    energy: EnergyBudgetProjection
    attack_line: AttackLineBudgetProjection

    @property
    def complete(self) -> bool:
        return self.energy.complete and self.attack_line.complete

    def key(self) -> tuple[int, int, int]:
        secured_energy = min(
            self.energy.secured_attacks,
            self.energy.required_attacks,
        )
        secured_attackers = min(
            self.attack_line.secured_attackers,
            self.attack_line.required_attackers,
        )
        return (
            int(self.complete),
            min(secured_energy, secured_attackers),
            secured_energy + secured_attackers,
        )


def is_exact_xerosic_contract(view) -> bool:
    """CABTのクセロシキ必須トラッシュ画面だけを識別する。"""
    effect = view.select.get("effect")
    discard_count = max(0, int(view.hand_size) - 3)
    return (
        isinstance(effect, dict)
        and effect.get("id") is not None
        and int(effect["id"]) == int(CardId.XEROSICS_MACHINATIONS)
        and (
            effect.get("playerIndex") is None
            or int(effect["playerIndex"]) != int(view.own_index)
        )
        and int(view.select.get("type", -1)) == int(SelectType.CARD)
        and int(view.select.get("context", -1)) == int(SelectContext.DISCARD)
        and int(view.select.get("minCount", -1)) == discard_count
        and int(view.select.get("maxCount", -1)) == discard_count
        and len(view.options) == int(view.hand_size)
        and all(
            int(option.raw.get("area", -1)) == int(Area.HAND)
            and int(option.raw.get("playerIndex", -1)) == int(view.own_index)
            for option in view.options
        )
    )


def _count(ids: Iterable[int], card_id: int | CardId) -> int:
    value = int(card_id)
    return sum(int(candidate) == value for candidate in ids)


def _has(ids: Iterable[int], card_id: int | CardId) -> bool:
    return _count(ids, card_id) > 0


def _possible_deck_stock(view, memory) -> Counter[int]:
    """確定山札、または公開領域を除いた山札＋未知サイドのカード別上限。"""
    known_absent = {
        int(card_id)
        for card_id in getattr(memory, "known_absent_deck_ids", ())
    }
    known_deck = getattr(memory, "known_deck", None)
    if known_deck is not None:
        return Counter({
            int(card_id): max(0, int(count))
            for card_id, count in known_deck.items()
            if int(count) > 0 and int(card_id) not in known_absent
        })

    public = Counter(int(card_id) for card_id in view.own_non_prize_card_ids)
    return Counter({
        int(card_id): max(0, int(count) - public[int(card_id)])
        for card_id, count in DECK_COUNTS.items()
        if (
            int(card_id) not in known_absent
            and int(count) > public[int(card_id)]
        )
    })


def _known_search_has_alakazam(memory) -> bool:
    return (
        memory.known_deck is not None
        and memory.known_deck.get(int(CardId.ALAKAZAM), 0) > 0
    )


def _known_deck_has(memory, card_id: int | CardId) -> bool:
    return (
        memory.known_deck is not None
        and memory.known_deck.get(int(card_id), 0) > 0
    )


def _projected_own_discard(view, kept: tuple[int, ...]) -> Counter[int]:
    """クセロシキ解決後の自分のトラッシュを投影する。"""
    projected = Counter(
        int(card.get("id", -1))
        for card in (view.own.get("discard") or ())
        if isinstance(card, dict) and card.get("id") is not None
    )
    discarded_from_hand = Counter(int(card_id) for card_id in view.hand_ids)
    discarded_from_hand.subtract(Counter(int(card_id) for card_id in kept))
    projected.update({
        card_id: count
        for card_id, count in discarded_from_hand.items()
        if count > 0
    })
    return projected


def _has_alakazam_source(kept: tuple[int, ...], memory) -> tuple[bool, str]:
    if _has(kept, CardId.ALAKAZAM):
        return True, "direct"
    if any(card_id in _ALAKAZAM_SEARCH_IDS for card_id in kept):
        if _known_search_has_alakazam(memory):
            return True, "search"
    return False, "missing"


@dataclass(frozen=True)
class _RecoveryRoute:
    name: str
    hand_delta: int
    uses_supporter: bool = False
    uses_attachment: bool = False


def _alakazam_source_routes(
    kept: tuple[int, ...],
    memory,
) -> tuple[_RecoveryRoute, ...]:
    routes: list[_RecoveryRoute] = []
    if _has(kept, CardId.ALAKAZAM):
        routes.append(_RecoveryRoute("direct", 2))
    if _known_search_has_alakazam(memory):
        if _has(kept, CardId.POKE_PAD):
            routes.append(_RecoveryRoute("search", 2))
        for supporter in (CardId.HILDA, CardId.DAWN):
            if _has(kept, supporter):
                routes.append(
                    _RecoveryRoute(
                        supporter.name.lower(),
                        2,
                        uses_supporter=True,
                    )
                )
        if (
            _has(kept, CardId.TEAM_ROCKETS_PETREL)
            and _known_deck_has(memory, CardId.POKE_PAD)
        ):
            routes.append(
                _RecoveryRoute(
                    "petrel_poke_pad",
                    2,
                    uses_supporter=True,
                )
            )
    return tuple(routes)


def _candy_routes(
    kept: tuple[int, ...],
    memory,
) -> tuple[_RecoveryRoute, ...]:
    routes: list[_RecoveryRoute] = []
    if _has(kept, CardId.RARE_CANDY):
        routes.append(_RecoveryRoute("rare_candy", -1))
    if (
        _has(kept, CardId.TEAM_ROCKETS_PETREL)
        and _known_deck_has(memory, CardId.RARE_CANDY)
    ):
        routes.append(
            _RecoveryRoute(
                "petrel_rare_candy",
                -1,
                uses_supporter=True,
            )
        )
    return tuple(routes)


def _psychic_energy_routes(
    view,
    kept: tuple[int, ...],
    memory,
    *,
    powered: bool,
) -> tuple[_RecoveryRoute, ...]:
    if powered:
        return (_RecoveryRoute("powered", 0),)

    routes: list[_RecoveryRoute] = []
    if any(_has(kept, card_id) for card_id in _ATTACK_PSYCHIC_IDS):
        routes.append(
            _RecoveryRoute(
                "attach_psychic",
                -1,
                uses_attachment=True,
            )
        )
    basic_in_discard = (
        _projected_own_discard(view, kept)[int(CardId.BASIC_PSYCHIC)] > 0
    )
    if basic_in_discard and _has(kept, CardId.NIGHT_STRETCHER):
        routes.append(
            _RecoveryRoute(
                "night_stretcher_psychic",
                -1,
                uses_attachment=True,
            )
        )
    if basic_in_discard and _has(kept, CardId.LANAS_AID):
        routes.append(
            _RecoveryRoute(
                "lanas_aid_psychic",
                -1,
                uses_supporter=True,
                uses_attachment=True,
            )
        )
    if (
        basic_in_discard
        and _has(kept, CardId.TEAM_ROCKETS_PETREL)
        and _known_deck_has(memory, CardId.NIGHT_STRETCHER)
    ):
        routes.append(
            _RecoveryRoute(
                "petrel_night_stretcher",
                -1,
                uses_supporter=True,
                uses_attachment=True,
            )
        )
    return tuple(routes)


def _enriching_route(view, kept: tuple[int, ...]) -> _RecoveryRoute | None:
    if not _has(kept, CardId.ENRICHING_ENERGY):
        return None
    if not any(
        int(pokemon.id) == int(CardId.DUNSPARCE)
        for pokemon in view.bench
    ):
        return None
    return _RecoveryRoute("enriching", 3, uses_attachment=True)


def _hammer_routes(
    view,
    kept: tuple[int, ...],
    memory,
) -> tuple[_RecoveryRoute, ...]:
    target = view.opponent_active
    if target is None:
        return ()
    blockers = _blocking_energy_cards(view, target)
    if (
        len(blockers) != 1
        or _has_self_effect_immunity(view, target)
        or _has_public_field_effect_immunity(view, target)
    ):
        return ()

    routes: list[_RecoveryRoute] = []
    if _has(kept, CardId.ENHANCED_HAMMER):
        routes.append(_RecoveryRoute("enhanced_hammer", -1))
    if (
        _has(kept, CardId.TEAM_ROCKETS_PETREL)
        and _known_deck_has(memory, CardId.ENHANCED_HAMMER)
    ):
        routes.append(
            _RecoveryRoute(
                "petrel_enhanced_hammer",
                -1,
                uses_supporter=True,
            )
        )
    return tuple(routes)


def _draw_probability(
    known_deck: Counter[int] | None,
    draw_count: int,
    required_groups: tuple[frozenset[int], ...],
) -> Fraction:
    """各カード群から1枚以上引く確率を包除原理で厳密計算する。"""
    groups = tuple(dict.fromkeys(group for group in required_groups if group))
    if not groups:
        return Fraction(1, 1)
    if known_deck is None or draw_count <= 0:
        return Fraction(0, 1)

    deck = Counter({int(card_id): max(0, int(count)) for card_id, count in known_deck.items()})
    total = sum(deck.values())
    draws = min(max(0, int(draw_count)), total)
    if total <= 0 or draws <= 0:
        return Fraction(0, 1)
    denominator = comb(total, draws)
    if denominator <= 0:
        return Fraction(0, 1)

    numerator = 0
    group_indices = tuple(range(len(groups)))
    for subset_size in range(len(groups) + 1):
        for subset in combinations(group_indices, subset_size):
            excluded_ids: set[int] = set()
            for index in subset:
                excluded_ids.update(groups[index])
            excluded_count = sum(deck[card_id] for card_id in excluded_ids)
            available = total - excluded_count
            ways = comb(available, draws) if available >= draws else 0
            numerator += (-1 if subset_size % 2 else 1) * ways
    return Fraction(max(0, numerator), denominator)


def _recovery_draws(
    view,
    kept: tuple[int, ...],
    *,
    fezandipiti_waiting: bool = False,
) -> tuple[int, int]:
    """通常ドロー以外の確定回復量と、手札から使う進化札枚数を返す。"""
    ready_dudunsparce = sum(
        pokemon.id == int(CardId.DUDUNSPARCE) for pokemon in view.bench
    )
    dunsparce = sum(
        pokemon.id == int(CardId.DUNSPARCE) for pokemon in view.bench
    )
    evolved_dudunsparce = min(dunsparce, _count(kept, CardId.DUDUNSPARCE))

    # 既に場にいるノココッチは手札を使わず3枚、進化させる場合は
    # ノココッチ1枚を手札から使ってから3枚引く。
    draws = (ready_dudunsparce + evolved_dudunsparce) * 3
    spent = evolved_dudunsparce

    # 現在のバトル場は次の相手番に倒される前提。ベンチが満員でも
    # 1体がバトル場へ昇格して枠が空くため、保持したキチキギスexを
    # 次の自分の番に出して「さかてにとる」を起動できる。
    if (
        view.active is not None
        and (
            fezandipiti_waiting
            or _has(kept, CardId.FEZANDIPITI_EX)
            or any(
                int(pokemon.id) == int(CardId.FEZANDIPITI_EX)
                for pokemon in view.bench
            )
        )
    ):
        draws += 3
    return draws, spent


def _continuity_score(view, kept: tuple[int, ...], route: str) -> int:
    dunsparce_count = sum(
        pokemon.id == int(CardId.DUNSPARCE) for pokemon in view.bench
    )
    has_powered_abra = any(
        pokemon.id == int(CardId.ABRA) and pokemon.has_psychic_energy
        for pokemon in view.bench
    )
    has_powered_kadabra = any(
        pokemon.id == int(CardId.KADABRA) and pokemon.has_psychic_energy
        for pokemon in view.bench
    )
    score = 0
    weights = {
        int(CardId.FEZANDIPITI_EX): 34,
        int(CardId.POKE_PAD): 30,
        int(CardId.HILDA): 27,
        int(CardId.DAWN): 27,
        int(CardId.ALAKAZAM): 26 if (has_powered_abra or has_powered_kadabra) else 6,
        int(CardId.RARE_CANDY): 25 if has_powered_abra else 5,
        int(CardId.KADABRA): 16 if has_powered_abra else 5,
        int(CardId.BASIC_PSYCHIC): 10,
        int(CardId.TELEPATH_PSYCHIC_ENERGY): 10,
        int(CardId.AIR_BALLOON): 9,
        int(CardId.BOSSES_ORDERS): 4,
        int(CardId.ENHANCED_HAMMER): 3,
    }
    for card_id in kept:
        score += weights.get(int(card_id), 0)
    score += 36 * min(
        dunsparce_count,
        _count(kept, CardId.DUDUNSPARCE),
    )

    # ケーシィから同じ番に攻撃する経路では、山札検索を一段挟むより
    # 手元のフーディンを直接使える組合せを優先する。
    if route == "rare_candy_direct":
        score += 12
    return score


def _attached_basic_psychic_count(pokemon) -> int:
    return sum(
        int(card_id) == int(CardId.BASIC_PSYCHIC)
        for card_id in getattr(pokemon, "energy_card_ids", ())
    )


def _xerosic_required_attacks(view, kept: tuple[int, ...]) -> int:
    """勝利か相手のサイド取り切りまでに残る自分の攻撃番を返す。"""
    attacks_to_win = max(0, int(view.own_prize_count))
    if attacks_to_win <= 0 or view.active is None:
        return attacks_to_win

    opponent_prizes = len(view.opponent.get("prize") or ())
    if opponent_prizes <= 0:
        return attacks_to_win
    remaining = max(
        0,
        opponent_prizes - max(1, _public_prize_value(view, view.active)),
    )
    if remaining <= 0:
        return 0

    liabilities = [
        max(1, _public_prize_value(view, pokemon))
        for pokemon in view.bench
    ]
    fez_on_field = any(
        int(pokemon.id) == int(CardId.FEZANDIPITI_EX)
        for pokemon in view.field
    )
    if _has(kept, CardId.FEZANDIPITI_EX) and not fez_on_field:
        meta = view.catalog.card(int(CardId.FEZANDIPITI_EX))
        liabilities.append(2 if meta is None else max(1, int(meta.prize_value)))
    liabilities.sort(reverse=True)

    available_attacks = 0
    while remaining > 0 and available_attacks < attacks_to_win:
        prize_value = (
            liabilities[available_attacks]
            if available_attacks < len(liabilities)
            else 1
        )
        remaining -= prize_value
        available_attacks += 1
    return min(attacks_to_win, available_attacks)


def _xerosic_energy_budget_inputs(
    view,
    memory,
    kept: tuple[int, ...],
    *,
    deck_stock: Counter[int] | None = None,
    include_hilda_searches: bool = True,
) -> tuple[int, int, int]:
    """回収前の攻撃回数と、再利用できる実在基本超の枚数を返す。"""
    required_attacks = _xerosic_required_attacks(view, kept)
    attack_line_ids = set(_ATTACK_LINE_CARD_IDS)

    # バトル場は次の相手番に倒される前提とし、ベンチで次番以降も
    # 残る攻撃系統に付いた超だけを直接の攻撃回数へ数える。
    powered_bench = sum(
        int(pokemon.id) in attack_line_ids and pokemon.has_psychic_energy
        for pokemon in view.bench
    )
    kept_basic = _count(kept, CardId.BASIC_PSYCHIC)
    kept_telepath = _count(kept, CardId.TELEPATH_PSYCHIC_ENERGY)

    known_deck = (
        deck_stock
        if deck_stock is not None
        else getattr(memory, "known_deck", None)
    )
    known_basic = 0 if known_deck is None else max(
        0,
        int(known_deck.get(int(CardId.BASIC_PSYCHIC), 0)),
    )
    known_telepath = 0 if known_deck is None else max(
        0,
        int(known_deck.get(int(CardId.TELEPATH_PSYCHIC_ENERGY), 0)),
    )
    hilda_searches = 0
    if include_hilda_searches:
        hilda_searches = min(
            _count(kept, CardId.HILDA),
            known_basic + known_telepath,
        )
    searched_basic = min(hilda_searches, known_basic)
    secured_attacks = (
        powered_bench
        + kept_basic
        + kept_telepath
        + hilda_searches
    )

    projected_discard = _projected_own_discard(view, kept)
    field_basic = sum(
        _attached_basic_psychic_count(pokemon)
        for pokemon in view.field
    )
    accessible_basic = (
        projected_discard[int(CardId.BASIC_PSYCHIC)]
        + field_basic
        + kept_basic
        + searched_basic
    )
    return required_attacks, secured_attacks, accessible_basic


def project_xerosic_energy_budget(
    view,
    memory,
    kept_card_ids: Iterable[int],
) -> EnergyBudgetProjection:
    """残りサイドを取り切るまでの確実な超エネルギー使用回数を数える。"""
    kept = tuple(int(card_id) for card_id in kept_card_ids)
    required_attacks, secured_attacks, accessible_basic = (
        _xerosic_energy_budget_inputs(view, memory, kept)
    )
    recovery_capacity = (
        _count(kept, CardId.NIGHT_STRETCHER)
        + 3 * _count(kept, CardId.LANAS_AID)
    )
    if (
        _has(kept, CardId.TEAM_ROCKETS_PETREL)
        and _known_deck_has(memory, CardId.NIGHT_STRETCHER)
        and not _has(kept, CardId.NIGHT_STRETCHER)
    ):
        recovery_capacity += 1
    secured_attacks += min(accessible_basic, recovery_capacity)

    return EnergyBudgetProjection(
        required_attacks=required_attacks,
        secured_attacks=secured_attacks,
    )


_DeckSearchState = tuple[
    Counter[int],
    Counter[int],
    int,
    Counter[int],
    int | None,
    int,
]


def _single_pokemon_search_routes(
    states: list[_DeckSearchState],
    candidates: tuple[int, ...],
) -> list[_DeckSearchState]:
    routes: list[_DeckSearchState] = []
    for state in states:
        (
            stock,
            deck,
            recovery_capacity,
            energy_stock,
            deck_capacity,
            supporter_uses,
        ) = state
        routes.append(state)
        if deck_capacity is not None and deck_capacity <= 0:
            continue
        available = tuple(card_id for card_id in candidates if deck[card_id] > 0)
        for card_id in available:
            searched = stock.copy()
            remaining = deck.copy()
            searched[card_id] += 1
            remaining[card_id] -= 1
            routes.append((
                searched,
                remaining,
                recovery_capacity,
                energy_stock,
                None if deck_capacity is None else deck_capacity - 1,
                supporter_uses,
            ))
    return routes


def _single_energy_search_routes(
    states: list[_DeckSearchState],
) -> list[_DeckSearchState]:
    routes: list[_DeckSearchState] = []
    for state in states:
        (
            stock,
            deck,
            recovery_capacity,
            energy_stock,
            deck_capacity,
            supporter_uses,
        ) = state
        routes.append(state)
        if deck_capacity is not None and deck_capacity <= 0:
            continue
        for card_id in _ATTACK_PSYCHIC_IDS:
            if deck[card_id] <= 0:
                continue
            searched_energy = energy_stock.copy()
            remaining = deck.copy()
            searched_energy[card_id] += 1
            remaining[card_id] -= 1
            routes.append((
                stock,
                remaining,
                recovery_capacity,
                searched_energy,
                None if deck_capacity is None else deck_capacity - 1,
                supporter_uses,
            ))
    return routes


def _known_attack_line_stock_routes(
    kept: tuple[int, ...],
    memory,
    *,
    deck_stock: Counter[int] | None = None,
    deck_capacity: int | None = None,
    supporter_uses: int | None = None,
) -> tuple[tuple[Counter[int], int, Counter[int], int], ...]:
    """保持した確定検索札ごとに、山札在庫を重複なく手元へ投影する。"""
    known_deck = (
        deck_stock
        if deck_stock is not None
        else getattr(memory, "known_deck", None)
    )
    if known_deck is None:
        remaining_supporters = (
            sum(
                _count(kept, card_id)
                for card_id in (
                    CardId.TEAM_ROCKETS_PETREL,
                    CardId.DAWN,
                    CardId.HILDA,
                )
            )
            if supporter_uses is None
            else max(0, int(supporter_uses))
        )
        return ((Counter(), 0, Counter(), remaining_supporters),)

    relevant_ids = (
        *_ATTACK_LINE_CARD_IDS,
        *_ATTACK_PSYCHIC_IDS,
        int(CardId.RARE_CANDY),
        int(CardId.NIGHT_STRETCHER),
        int(CardId.POKE_PAD),
        int(CardId.BUDDY_BUDDY_POFFIN),
    )
    deck = Counter({
        card_id: max(0, int(known_deck.get(card_id, 0)))
        for card_id in relevant_ids
    })
    states: list[_DeckSearchState] = [
        (
            Counter(),
            deck,
            0,
            Counter(),
            None if deck_capacity is None else max(0, int(deck_capacity)),
            (
                sum(
                    _count(kept, card_id)
                    for card_id in (
                        CardId.TEAM_ROCKETS_PETREL,
                        CardId.DAWN,
                        CardId.HILDA,
                    )
                )
                if supporter_uses is None
                else max(0, int(supporter_uses))
            ),
        )
    ]

    # ラムダは1枚につき1経路だけを選ぶ。アメ、夜のタンカ、
    # ポケパッド経由のポケモンを同じラムダから同時には数えない。
    for _ in range(_count(kept, CardId.TEAM_ROCKETS_PETREL)):
        routes: list[_DeckSearchState] = []
        for state in states:
            (
                stock,
                remaining,
                recovery_capacity,
                energy_stock,
                capacity,
                remaining_supporters,
            ) = state
            routes.append(state)
            if remaining_supporters <= 0:
                continue
            if (
                remaining[int(CardId.RARE_CANDY)] > 0
                and (capacity is None or capacity >= 1)
            ):
                searched = stock.copy()
                next_deck = remaining.copy()
                searched[int(CardId.RARE_CANDY)] += 1
                next_deck[int(CardId.RARE_CANDY)] -= 1
                routes.append((
                    searched,
                    next_deck,
                    recovery_capacity,
                    energy_stock,
                    None if capacity is None else capacity - 1,
                    remaining_supporters - 1,
                ))
            if (
                remaining[int(CardId.NIGHT_STRETCHER)] > 0
                and (capacity is None or capacity >= 1)
            ):
                next_deck = remaining.copy()
                next_deck[int(CardId.NIGHT_STRETCHER)] -= 1
                routes.append((
                    stock,
                    next_deck,
                    recovery_capacity + 1,
                    energy_stock,
                    None if capacity is None else capacity - 1,
                    remaining_supporters - 1,
                ))
            if (
                remaining[int(CardId.POKE_PAD)] > 0
                and (capacity is None or capacity >= 2)
            ):
                for card_id in _ATTACK_LINE_CARD_IDS:
                    if remaining[card_id] <= 0:
                        continue
                    searched = stock.copy()
                    next_deck = remaining.copy()
                    searched[card_id] += 1
                    next_deck[int(CardId.POKE_PAD)] -= 1
                    next_deck[card_id] -= 1
                    routes.append((
                        searched,
                        next_deck,
                        recovery_capacity,
                        energy_stock,
                        None if capacity is None else capacity - 2,
                        remaining_supporters - 1,
                    ))
            max_abra = min(2, remaining[int(CardId.ABRA)])
            if capacity is not None:
                max_abra = min(max_abra, max(0, capacity - 1))
            if remaining[int(CardId.BUDDY_BUDDY_POFFIN)] > 0:
                for abra_count in range(1, max_abra + 1):
                    searched = stock.copy()
                    next_deck = remaining.copy()
                    searched[int(CardId.ABRA)] += abra_count
                    next_deck[int(CardId.BUDDY_BUDDY_POFFIN)] -= 1
                    next_deck[int(CardId.ABRA)] -= abra_count
                    routes.append((
                        searched,
                        next_deck,
                        recovery_capacity,
                        energy_stock,
                        None if capacity is None else capacity - 1 - abra_count,
                        remaining_supporters - 1,
                    ))
        states = routes

    # ヒカリは各段階を0～1枚ずつ取れる。未知山札では各部分集合を
    # 列挙し、カード別上限とは別に現在の山札総数も消費する。
    for _ in range(_count(kept, CardId.DAWN)):
        routes = []
        for state in states:
            (
                stock,
                remaining,
                recovery_capacity,
                energy_stock,
                capacity,
                remaining_supporters,
            ) = state
            routes.append(state)
            if remaining_supporters <= 0:
                continue
            dawn_routes = [(
                stock,
                remaining,
                recovery_capacity,
                energy_stock,
                capacity,
                remaining_supporters - 1,
            )]
            for card_id in _ATTACK_LINE_CARD_IDS:
                next_routes: list[_DeckSearchState] = []
                for route in dawn_routes:
                    (
                        stock,
                        remaining,
                        recovery_capacity,
                        energy_stock,
                        capacity,
                        route_supporters,
                    ) = route
                    next_routes.append(route)
                    if (
                        remaining[card_id] <= 0
                        or (capacity is not None and capacity <= 0)
                    ):
                        continue
                    searched = stock.copy()
                    next_deck = remaining.copy()
                    searched[card_id] += 1
                    next_deck[card_id] -= 1
                    next_routes.append((
                        searched,
                        next_deck,
                        recovery_capacity,
                        energy_stock,
                        None if capacity is None else capacity - 1,
                        route_supporters,
                    ))
                dawn_routes = next_routes
            routes.extend(dawn_routes)
        states = routes

    # なかよしポフィンは確定しているケーシィを2枚まで取れる。
    for _ in range(_count(kept, CardId.BUDDY_BUDDY_POFFIN)):
        routes = []
        for state in states:
            (
                stock,
                remaining,
                recovery_capacity,
                energy_stock,
                capacity,
                remaining_supporters,
            ) = state
            max_count = min(2, remaining[int(CardId.ABRA)])
            if capacity is not None:
                max_count = min(max_count, capacity)
            for count in range(max_count + 1):
                if count <= 0:
                    routes.append(state)
                    continue
                searched = stock.copy()
                next_deck = remaining.copy()
                searched[int(CardId.ABRA)] += count
                next_deck[int(CardId.ABRA)] -= count
                routes.append((
                    searched,
                    next_deck,
                    recovery_capacity,
                    energy_stock,
                    None if capacity is None else capacity - count,
                    remaining_supporters,
                ))
        states = routes

    # トウコは進化ポケモンとエネルギーを各1枚まで、ポケパッドは
    # 任意のポケモン1枚を検索する。いずれも同じ山札残量を使う。
    for _ in range(_count(kept, CardId.HILDA)):
        routes = []
        for state in states:
            routes.append(state)
            if state[5] <= 0:
                continue
            played_hilda = (*state[:5], state[5] - 1)
            hilda_routes = _single_pokemon_search_routes(
                [played_hilda],
                (int(CardId.KADABRA), int(CardId.ALAKAZAM)),
            )
            routes.extend(_single_energy_search_routes(hilda_routes))
        states = routes
    for _ in range(_count(kept, CardId.POKE_PAD)):
        states = _single_pokemon_search_routes(states, _ATTACK_LINE_CARD_IDS)

    return tuple(
        (stock, recovery_capacity, energy_stock, remaining_supporters)
        for (
            stock,
            _,
            recovery_capacity,
            energy_stock,
            _,
            remaining_supporters,
        ) in states
    )


def _recovered_attack_line_stock_routes(
    projected_discard: Counter[int],
    capacity: int,
) -> tuple[Counter[int], ...]:
    """回収上限と実在枚数の双方を満たすポケモン在庫候補を返す。"""
    limit = max(0, int(capacity))
    abra_limit = min(limit, projected_discard[int(CardId.ABRA)])
    routes: list[Counter[int]] = []
    for abra_count in range(abra_limit + 1):
        kadabra_limit = min(
            limit - abra_count,
            projected_discard[int(CardId.KADABRA)],
        )
        for kadabra_count in range(kadabra_limit + 1):
            alakazam_limit = min(
                limit - abra_count - kadabra_count,
                projected_discard[int(CardId.ALAKAZAM)],
            )
            for alakazam_count in range(alakazam_limit + 1):
                routes.append(Counter({
                    int(CardId.ABRA): abra_count,
                    int(CardId.KADABRA): kadabra_count,
                    int(CardId.ALAKAZAM): alakazam_count,
                }))
    return tuple(routes)


def _complete_attack_line_count(view, stock: Counter[int]) -> int:
    """バトル場喪失後に完成できる独立したフーディン系統を数える。"""
    field = Counter(
        int(pokemon.id)
        for pokemon in view.bench
        if int(pokemon.id) in _ATTACK_LINE_CARD_IDS
    )
    secured = field[int(CardId.ALAKAZAM)]
    remaining_alakazam = stock[int(CardId.ALAKAZAM)]

    completed_kadabra = min(
        field[int(CardId.KADABRA)],
        remaining_alakazam,
    )
    secured += completed_kadabra
    remaining_alakazam -= completed_kadabra

    basic_lines = field[int(CardId.ABRA)] + stock[int(CardId.ABRA)]
    maturity_cards = (
        stock[int(CardId.KADABRA)]
        + stock[int(CardId.RARE_CANDY)]
    )
    secured += min(basic_lines, remaining_alakazam, maturity_cards)
    return secured


def project_xerosic_attack_line_budget(
    view,
    memory,
    kept_card_ids: Iterable[int],
) -> AttackLineBudgetProjection:
    """クセロシキ後の残り各攻撃番に必要な独立攻撃系統を数える。"""
    kept = tuple(int(card_id) for card_id in kept_card_ids)
    required_attackers = _xerosic_required_attacks(view, kept)
    projected_discard = _projected_own_discard(view, kept)
    direct_stock = Counter(
        card_id
        for card_id in kept
        if card_id in (*_ATTACK_LINE_CARD_IDS, int(CardId.RARE_CANDY))
    )
    fixed_item_recovery_capacity = (
        _count(kept, CardId.NIGHT_STRETCHER)
        + 5 * _count(kept, CardId.SACRED_ASH)
    )

    secured_attackers = 0
    for (
        searched_stock,
        searched_recovery_capacity,
        _,
        remaining_supporters,
    ) in (
        _known_attack_line_stock_routes(
            kept,
            memory,
            deck_capacity=max(0, int(view.own.get("deckCount", 0))),
            supporter_uses=required_attackers,
        )
    ):
        recovery_capacity = (
            fixed_item_recovery_capacity
            + searched_recovery_capacity
            + 3 * min(
                _count(kept, CardId.LANAS_AID),
                remaining_supporters,
            )
        )
        for recovered_stock in _recovered_attack_line_stock_routes(
            projected_discard,
            recovery_capacity,
        ):
            stock = direct_stock + searched_stock + recovered_stock
            secured_attackers = max(
                secured_attackers,
                _complete_attack_line_count(view, stock),
            )

    return AttackLineBudgetProjection(
        required_attackers=required_attackers,
        secured_attackers=secured_attackers,
    )


_SHARED_RECOVERY_CARD_IDS = (
    *_ATTACK_LINE_CARD_IDS,
    int(CardId.BASIC_PSYCHIC),
)


def _recovery_selections(
    available: Counter[int],
    card_ids: tuple[int, ...],
    limit: int,
) -> tuple[Counter[int], ...]:
    """実在枚数と効果上限を超えない回収対象の組合せを列挙する。"""
    selections: list[Counter[int]] = []

    def visit(
        index: int,
        remaining_capacity: int,
        selected: Counter[int],
    ) -> None:
        if index >= len(card_ids):
            selections.append(selected.copy())
            return
        card_id = card_ids[index]
        max_count = min(
            remaining_capacity,
            max(0, int(available[card_id])),
        )
        for count in range(max_count + 1):
            if count:
                selected[card_id] = count
            else:
                selected.pop(card_id, None)
            visit(index + 1, remaining_capacity - count, selected)
        selected.pop(card_id, None)

    visit(0, max(0, int(limit)), Counter())
    return tuple(selections)


def _apply_recovery_resource(
    states: tuple[tuple[Counter[int], Counter[int]], ...],
    card_ids: tuple[int, ...],
    limit: int,
) -> tuple[tuple[Counter[int], Counter[int]], ...]:
    routes: list[tuple[Counter[int], Counter[int]]] = []
    for recovered, available in states:
        for selected in _recovery_selections(available, card_ids, limit):
            routes.append((recovered + selected, available - selected))
    return tuple(routes)


def _shared_recovery_states(
    available: Counter[int],
    *,
    night_stretcher_count: int,
    lanas_aid_count: int,
    sacred_ash_count: int,
) -> tuple[tuple[Counter[int], Counter[int]], ...]:
    """各回収札と各実札を一度だけ使う共有回収状態を返す。"""
    states = ((Counter(), available.copy()),)
    for _ in range(max(0, int(night_stretcher_count))):
        states = _apply_recovery_resource(
            states,
            _SHARED_RECOVERY_CARD_IDS,
            1,
        )
    for _ in range(max(0, int(lanas_aid_count))):
        states = _apply_recovery_resource(
            states,
            _SHARED_RECOVERY_CARD_IDS,
            3,
        )
    for _ in range(max(0, int(sacred_ash_count))):
        states = _apply_recovery_resource(
            states,
            _ATTACK_LINE_CARD_IDS,
            5,
        )
    return states


def project_xerosic_shared_budget(
    view,
    memory,
    kept_card_ids: Iterable[int],
    *,
    deck_stock: Counter[int] | None = None,
) -> SharedBudgetProjection:
    """共有回収資源を一つの状態へ割り当てて両予算を投影する。"""
    kept = tuple(int(card_id) for card_id in kept_card_ids)
    required_attacks, base_secured_attacks, accessible_basic = (
        _xerosic_energy_budget_inputs(
            view,
            memory,
            kept,
            deck_stock=deck_stock,
            include_hilda_searches=False,
        )
    )
    required_attackers = required_attacks
    projected_discard = _projected_own_discard(view, kept)
    direct_stock = Counter(
        card_id
        for card_id in kept
        if card_id in (*_ATTACK_LINE_CARD_IDS, int(CardId.RARE_CANDY))
    )
    recoverable = Counter({
        card_id: projected_discard[card_id]
        for card_id in _ATTACK_LINE_CARD_IDS
    })
    recoverable[int(CardId.BASIC_PSYCHIC)] = accessible_basic

    best: SharedBudgetProjection | None = None
    for (
        searched_stock,
        searched_night_stretcher_count,
        searched_energy,
        remaining_supporters,
    ) in (
        _known_attack_line_stock_routes(
            kept,
            memory,
            deck_stock=deck_stock,
            deck_capacity=max(0, int(view.own.get("deckCount", 0))),
            supporter_uses=required_attacks,
        )
    ):
        route_recoverable = recoverable.copy()
        route_recoverable[int(CardId.BASIC_PSYCHIC)] += searched_energy[
            int(CardId.BASIC_PSYCHIC)
        ]
        states = _shared_recovery_states(
            route_recoverable,
            night_stretcher_count=(
                _count(kept, CardId.NIGHT_STRETCHER)
                + searched_night_stretcher_count
            ),
            lanas_aid_count=min(
                _count(kept, CardId.LANAS_AID),
                remaining_supporters,
            ),
            sacred_ash_count=_count(kept, CardId.SACRED_ASH),
        )
        for recovered, _ in states:
            energy = EnergyBudgetProjection(
                required_attacks=required_attacks,
                secured_attacks=(
                    base_secured_attacks
                    + sum(searched_energy.values())
                    + recovered[int(CardId.BASIC_PSYCHIC)]
                ),
            )
            recovered_stock = Counter({
                card_id: recovered[card_id]
                for card_id in _ATTACK_LINE_CARD_IDS
            })
            attack_line = AttackLineBudgetProjection(
                required_attackers=required_attackers,
                secured_attackers=_complete_attack_line_count(
                    view,
                    direct_stock + searched_stock + recovered_stock,
                ),
            )
            candidate = SharedBudgetProjection(energy, attack_line)
            if best is None or candidate.key() > best.key():
                best = candidate

    if best is not None:
        return best
    return SharedBudgetProjection(
        EnergyBudgetProjection(required_attacks, base_secured_attacks),
        AttackLineBudgetProjection(required_attackers, 0),
    )


def _projection(
    *,
    view,
    kept: tuple[int, ...],
    route: str,
    deterministic_attack: bool,
    attack_probability: Fraction,
    recovered_hand: int,
    required_hand_for_ko: int | None = None,
) -> RecoveryProjection:
    required = (
        view.required_hand_for_active_ko
        if required_hand_for_ko is None
        else max(0, int(required_hand_for_ko))
    )
    can_ko_if_attacking = required is not None and recovered_hand >= int(required)
    guaranteed_ko = deterministic_attack and can_ko_if_attacking
    ko_probability = (
        Fraction(1, 1)
        if guaranteed_ko
        else attack_probability if can_ko_if_attacking else Fraction(0, 1)
    )
    can_attack = deterministic_attack or attack_probability > 0
    return RecoveryProjection(
        guaranteed_ko=guaranteed_ko,
        can_attack=can_attack,
        recovered_hand=recovered_hand,
        ko_probability=ko_probability,
        continuity_score=_continuity_score(view, kept, route),
        route=route,
    )


def project_xerosic_recovery(
    view,
    memory,
    kept_card_ids: Iterable[int],
    *,
    fezandipiti_waiting: bool = False,
    required_hand_for_ko: int | None = None,
) -> RecoveryProjection:
    """残す3枚から、次の番の攻撃・KO・後続維持を投影する。"""
    kept = tuple(int(card_id) for card_id in kept_card_ids)
    recovery_draws, recovery_spent = _recovery_draws(
        view,
        kept,
        fezandipiti_waiting=fezandipiti_waiting,
    )
    draw_count = min(
        max(0, int(view.own.get("deckCount", 0))),
        1 + recovery_draws,
    )
    base_hand = len(kept) + draw_count - recovery_spent
    candidates: list[RecoveryProjection] = []

    target = view.opponent_active
    attack_blocked = bool(
        target is not None
        and (
            _blocking_energy_cards(view, target)
            or _has_self_effect_immunity(view, target)
            or _has_public_field_effect_immunity(view, target)
        )
    )
    hammer_routes = _hammer_routes(view, kept, memory) if attack_blocked else ()
    enriching = _enriching_route(view, kept)

    def compatible(routes: tuple[_RecoveryRoute, ...]) -> bool:
        return (
            sum(route.uses_supporter for route in routes) <= 1
            and sum(route.uses_attachment for route in routes) <= 1
        )

    def append_attack(
        route_name: str,
        routes: tuple[_RecoveryRoute, ...],
    ) -> None:
        variants: list[tuple[_RecoveryRoute, ...]] = [routes]
        if enriching is not None and compatible((*routes, enriching)):
            variants.append((*routes, enriching))
        if attack_blocked:
            variants = [
                (*variant, hammer)
                for variant in variants
                for hammer in hammer_routes
                if compatible((*variant, hammer))
            ]
        for variant in variants:
            if not compatible(variant):
                continue
            suffixes = tuple(
                route.name for route in variant[len(routes):]
            )
            final_name = "_".join((route_name, *suffixes))
            candidates.append(
                _projection(
                    view=view,
                    kept=kept,
                    route=final_name,
                    deterministic_attack=True,
                    attack_probability=Fraction(1, 1),
                    recovered_hand=(
                        base_hand + sum(route.hand_delta for route in variant)
                    ),
                    required_hand_for_ko=required_hand_for_ko,
                )
            )

    bench_alakazam = tuple(
        pokemon
        for pokemon in view.bench
        if int(pokemon.id) == int(CardId.ALAKAZAM)
    )
    if bench_alakazam:
        powered = any(pokemon.has_psychic_energy for pokemon in bench_alakazam)
        for energy in _psychic_energy_routes(
            view,
            kept,
            memory,
            powered=powered,
        ):
            append_attack(
                "powered_alakazam" if powered else f"{energy.name}_alakazam",
                (energy,),
            )

    bench_kadabra = tuple(
        pokemon
        for pokemon in view.bench
        if int(pokemon.id) == int(CardId.KADABRA)
    )
    kadabra_energy_routes: tuple[_RecoveryRoute, ...] = ()
    if bench_kadabra:
        powered_kadabra = any(
            pokemon.has_psychic_energy for pokemon in bench_kadabra
        )
        kadabra_energy_routes = _psychic_energy_routes(
            view,
            kept,
            memory,
            powered=powered_kadabra,
        )
        source_routes = _alakazam_source_routes(kept, memory)
        if (
            not powered_kadabra
            and _has(kept, CardId.HILDA)
            and _known_deck_has(memory, CardId.ALAKAZAM)
            and any(
                _known_deck_has(memory, card_id)
                for card_id in _ATTACK_PSYCHIC_IDS
            )
        ):
            append_attack(
                "hilda_kadabra",
                (
                    _RecoveryRoute(
                        "hilda",
                        1,
                        uses_supporter=True,
                        uses_attachment=True,
                    ),
                ),
            )
        for energy in kadabra_energy_routes:
            for source in source_routes:
                if not compatible((energy, source)):
                    continue
                prefix = (
                    "powered_kadabra"
                    if energy.name == "powered"
                    else f"{energy.name}_kadabra"
                )
                append_attack(f"{prefix}_{source.name}", (energy, source))

        if not source_routes and kadabra_energy_routes and not attack_blocked:
            draw_targets = {int(CardId.ALAKAZAM)}
            if _known_search_has_alakazam(memory):
                draw_targets.update(_ALAKAZAM_SEARCH_IDS)
            probability = _draw_probability(
                memory.known_deck,
                draw_count,
                (frozenset(draw_targets),),
            )
            best_energy = max(
                kadabra_energy_routes,
                key=lambda route: route.hand_delta,
            )
            candidates.append(
                _projection(
                    view=view,
                    kept=kept,
                    route="powered_kadabra_draw",
                    deterministic_attack=False,
                    attack_probability=probability,
                    recovered_hand=base_hand + best_energy.hand_delta + 2,
                    required_hand_for_ko=required_hand_for_ko,
                )
            )

    bench_abra = tuple(
        pokemon
        for pokemon in view.bench
        if int(pokemon.id) == int(CardId.ABRA)
    )
    abra_energy_routes: tuple[_RecoveryRoute, ...] = ()
    if bench_abra:
        powered_abra = any(pokemon.has_psychic_energy for pokemon in bench_abra)
        abra_energy_routes = _psychic_energy_routes(
            view,
            kept,
            memory,
            powered=powered_abra,
        )
        candy_routes = _candy_routes(kept, memory)
        source_routes = _alakazam_source_routes(kept, memory)
        for energy in abra_energy_routes:
            for candy in candy_routes:
                for source in source_routes:
                    routes = (energy, candy, source)
                    if not compatible(routes):
                        continue
                    prefix = "" if energy.name == "powered" else f"{energy.name}_"
                    append_attack(
                        f"{prefix}{candy.name}_{source.name}",
                        routes,
                    )

        source_ready, _ = _has_alakazam_source(kept, memory)
        has_candy = _has(kept, CardId.RARE_CANDY)
        if (
            abra_energy_routes
            and not (candy_routes and source_routes)
            and not attack_blocked
        ):
            missing_groups: list[frozenset[int]] = []
            if not has_candy:
                missing_groups.append(frozenset({int(CardId.RARE_CANDY)}))
            if not source_ready:
                source_targets = {int(CardId.ALAKAZAM)}
                if _known_search_has_alakazam(memory):
                    source_targets.update(_ALAKAZAM_SEARCH_IDS)
                missing_groups.append(frozenset(source_targets))
            probability = _draw_probability(
                memory.known_deck,
                draw_count,
                tuple(missing_groups),
            )
            best_energy = max(
                abra_energy_routes,
                key=lambda route: route.hand_delta,
            )
            candidates.append(
                _projection(
                    view=view,
                    kept=kept,
                    route="rare_candy_draw",
                    deterministic_attack=False,
                    attack_probability=probability,
                    recovered_hand=base_hand + best_energy.hand_delta + 1,
                    required_hand_for_ko=required_hand_for_ko,
                )
            )

        if _has(kept, CardId.KADABRA):
            candidates.append(
                _projection(
                    view=view,
                    kept=kept,
                    route="kadabra_draw",
                    deterministic_attack=False,
                    attack_probability=Fraction(0, 1),
                    recovered_hand=base_hand + 1,
                    required_hand_for_ko=required_hand_for_ko,
                )
            )

    if not candidates:
        candidates.append(
            _projection(
                view=view,
                kept=kept,
                route="recovery_only",
                deterministic_attack=False,
                attack_probability=Fraction(0, 1),
                recovered_hand=base_hand,
                required_hand_for_ko=required_hand_for_ko,
            )
        )
    return max(candidates, key=RecoveryProjection.key)


def _xerosic_keep_key(
    view,
    memory,
    kept: tuple[int, ...],
    *,
    fezandipiti_waiting: bool = False,
    required_hand_for_ko: int | None = None,
    include_route: bool = True,
) -> tuple:
    projection = project_xerosic_recovery(
        view,
        memory,
        kept,
        fezandipiti_waiting=fezandipiti_waiting,
        required_hand_for_ko=required_hand_for_ko,
    )
    shared_budget = project_xerosic_shared_budget(view, memory, kept)
    # 未知サイド込みの上限は候補比較だけに使う。確定KO・ドロー確率を
    # 作るRecoveryProjectionへ渡さず、公開情報との確実性を混同しない。
    possible_budget = project_xerosic_shared_budget(
        view,
        memory,
        kept,
        deck_stock=_possible_deck_stock(view, memory),
    )
    key = (
        int(projection.guaranteed_ko),
        int(projection.can_attack),
        *possible_budget.key(),
        projection.recovered_hand if projection.can_attack else -1,
        projection.ko_probability,
        projection.continuity_score,
        *shared_budget.key(),
    )
    return (*key, projection.route) if include_route else key


def _public_prize_value(view, pokemon) -> int:
    meta = view.catalog.card(pokemon.id)
    return 1 if meta is None else int(meta.prize_value)


def _hand_after_playing_option(view, option: LegalOption) -> tuple[int, ...]:
    hand = [int(card["id"]) for card in (view.own.get("hand") or ())]
    raw_index = option.raw.get("index")
    if raw_index is not None:
        index = int(raw_index)
        if (
            0 <= index < len(hand)
            and hand[index] == int(CardId.FEZANDIPITI_EX)
        ):
            del hand[index]
            return tuple(hand)
    try:
        hand.remove(int(CardId.FEZANDIPITI_EX))
    except ValueError:
        return ()
    return tuple(hand)


def _prospective_fezandipiti(view) -> PokemonRef:
    meta = view.catalog.card(int(CardId.FEZANDIPITI_EX))
    hp = 210 if meta is None else int(meta.hp)
    return PokemonRef(
        id=int(CardId.FEZANDIPITI_EX),
        serial=None,
        player_index=int(view.own_index),
        area=int(Area.BENCH),
        index=len(view.bench),
        hp=hp,
        max_hp=hp,
        appear_this_turn=True,
        energies=(),
        energy_card_ids=(),
        tool_ids=(),
        pre_evolution_ids=(),
    )


def _best_terminal_xerosic_recovery(
    view,
    memory,
    hand_ids: tuple[int, ...],
    *,
    required_hand_for_ko: int,
) -> RecoveryProjection:
    keep_count = min(3, len(hand_ids))
    keeps = tuple(combinations(hand_ids, keep_count))
    if not keeps:
        keeps = ((),)
    best_kept = max(
        keeps,
        key=lambda kept: _xerosic_keep_key(
            view,
            memory,
            kept,
            fezandipiti_waiting=True,
            required_hand_for_ko=required_hand_for_ko,
        ),
    )
    return project_xerosic_recovery(
        view,
        memory,
        best_kept,
        fezandipiti_waiting=True,
        required_hand_for_ko=required_hand_for_ko,
    )


def next_attack_is_secured_without_fezandipiti_draw(view, memory) -> bool:
    """現在のキチキギス3枚を使わなくても次番KOが確定しているか返す。"""
    future_targets = tuple(view.opponent_bench)
    if not future_targets:
        return True
    if any(_is_hand_power_effect_immune(view, pokemon) for pokemon in future_targets):
        return False
    required_next_hand = max(
        (max(0, int(pokemon.hp)) + 19) // 20
        for pokemon in future_targets
    )
    # キチキギス本体は打点用の手札1枚として残すが、さかてにとる3枚は
    # 数えないため未知札へ置き換える。
    hand_without_fez_draw = tuple(
        _UNKNOWN_CARD_ID
        if int(card_id) == int(CardId.FEZANDIPITI_EX)
        else int(card_id)
        for card_id in view.hand_ids
    )
    return project_xerosic_recovery(
        view,
        memory,
        hand_without_fez_draw,
        required_hand_for_ko=required_next_hand,
    ).guaranteed_ko


@covers("PLAYBOOK-FEZANDIPITI-TERMINAL")
def propose_proactive_fezandipiti(view, memory) -> Proposal | None:
    """終盤だけ、ボスとクセロシキの二択を作るため先にベンチへ出す。"""
    if (
        not view.is_own_turn
        or disruption_mode(memory) is not DisruptionMode.XEROSIC
        or len(view.bench) >= int(view.own.get("benchMax", 5))
    ):
        return None
    option = min(
        (
            candidate
            for candidate in view.options
            if int(candidate.type) == int(OptionType.PLAY)
            and candidate.card_id == int(CardId.FEZANDIPITI_EX)
        ),
        key=lambda candidate: (
            10**18
            if candidate.raw.get("index") is None
            else int(candidate.raw["index"]),
            candidate.position,
        ),
        default=None,
    )
    if option is None:
        return None

    # 先置きで1枚減っても、今のKOを絶対に失わない。
    if not can_hand_power_ko(
        view,
        hand_size=max(0, int(view.hand_size) - 1),
    ):
        return None
    if len(view.opponent.get("prize") or ()) <= 2:
        return None

    current_target = view.opponent_active
    future_targets = tuple(view.opponent_bench)
    if current_target is None or not future_targets:
        return None
    current_prizes = _public_prize_value(view, current_target)
    if int(view.own_prize_count) <= current_prizes:
        return None
    # 相手が最小サイドのポケモンを前へ出しても、次のKOで取り切れる局面だけ。
    guaranteed_next_prizes = min(
        _public_prize_value(view, pokemon)
        for pokemon in future_targets
    )
    if int(view.own_prize_count) > current_prizes + guaranteed_next_prizes:
        return None

    # 次に前へ出得る全個体をハンドパワーで倒せる公開経路が必要。
    if any(_is_hand_power_effect_immune(view, pokemon) for pokemon in future_targets):
        return None
    required_next_hand = max(
        (max(0, int(pokemon.hp)) + 19) // 20
        for pokemon in future_targets
    )
    remaining_hand = _hand_after_playing_option(view, option)
    if not remaining_hand and int(view.hand_size) > 1:
        return None
    recovery = _best_terminal_xerosic_recovery(
        view,
        memory,
        remaining_hand,
        required_hand_for_ko=required_next_hand,
    )
    if not recovery.guaranteed_ko:
        return None

    excluded = (
        frozenset({int(current_target.serial)})
        if current_target.serial is not None
        else frozenset()
    )
    if view.public_bench_damage_risk(
        _prospective_fezandipiti(view),
        excluded_attacker_serials=excluded,
    ):
        return None

    return Proposal(
        (option.position,),
        1125,
        "終盤の2回のKOで勝ち切れるためキチキギスexを先置きし、"
        "ボスとクセロシキの二択を作る",
        (
            "PLAYBOOK-FEZANDIPITI",
            "PLAYBOOK-FEZANDIPITI-TERMINAL",
            "PLAYBOOK-XEROSIC-KEEP",
        ),
    )


def useful_xerosic_keep_count(view, memory) -> int:
    """最善の3枚のうち、復帰投影へ実際に寄与する枚数を返す。"""
    hand_ids = tuple(int(card_id) for card_id in view.hand_ids)
    keep_count = min(3, len(hand_ids))
    if keep_count <= 0:
        return 0

    indexed_keeps = tuple(combinations(range(len(hand_ids)), keep_count))
    best_indices = max(
        indexed_keeps,
        key=lambda indices: _xerosic_keep_key(
            view,
            memory,
            tuple(hand_ids[index] for index in indices),
        ),
    )
    best_kept = tuple(hand_ids[index] for index in best_indices)
    best_key = _xerosic_keep_key(
        view,
        memory,
        best_kept,
        include_route=False,
    )
    useful = 0
    for index in range(len(best_kept)):
        replaced = list(best_kept)
        replaced[index] = _UNKNOWN_CARD_ID
        replacement_key = _xerosic_keep_key(
            view,
            memory,
            tuple(replaced),
            include_route=False,
        )
        if best_key > replacement_key:
            useful += 1
    return useful


def _stable_keep_key(options: tuple[LegalOption, ...]) -> tuple[tuple[int, int], ...]:
    identities = []
    for option in options:
        if option.card_serial is not None:
            identities.append((0, int(option.card_serial)))
        else:
            raw_index = option.raw.get("index")
            identities.append((1, 10**18 if raw_index is None else int(raw_index)))
    return tuple((-kind, -value) for kind, value in sorted(identities))


@covers("PLAYBOOK-XEROSIC-KEEP")
def choose_xerosic_discard(view, memory) -> Proposal | None:
    if not is_exact_xerosic_contract(view):
        return None
    options = tuple(view.options)
    keep_count = min(3, len(options))
    kept_candidates = tuple(combinations(options, keep_count))
    if not kept_candidates:
        kept_candidates = ((),)
    best = max(
        kept_candidates,
        key=lambda kept: (
            _xerosic_keep_key(
                view,
                memory,
                tuple(
                    _UNKNOWN_CARD_ID if option.card_id is None else int(option.card_id)
                    for option in kept
                ),
            ),
            _stable_keep_key(tuple(kept)),
        ),
    )
    kept_positions = {option.position for option in best}
    discarded = tuple(
        option.position
        for option in sorted(options, key=lambda candidate: candidate.position)
        if option.position not in kept_positions
    )
    return Proposal(
        discarded,
        1200,
        "クセロシキ後の次ターンKOと残り攻撃回数を最大化する3枚を残す",
        ("PLAYBOOK-XEROSIC-KEEP",),
    )
