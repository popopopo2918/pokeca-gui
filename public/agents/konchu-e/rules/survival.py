"""相手の公開済み攻撃から、進化・退避による取得サイド減少を判定する。"""

from __future__ import annotations

from itertools import combinations

from cards import CardId
from model import Area, OptionType


def _public_prize_value(view, pokemon) -> int:
    meta = view.catalog.card(pokemon.id)
    return 1 if meta is None else int(meta.prize_value)


def max_public_bench_pressure(
    view,
    pokemon,
    *,
    excluded_attacker_serials: frozenset[int] = frozenset(),
) -> int:
    """1つの公開済み使用可能ワザが対象へ与えられる最大固定打点。"""
    if (
        pokemon is None
        or pokemon.player_index != view.own_index
        or int(pokemon.area or -1) != int(Area.BENCH)
    ):
        return 0
    return view.max_public_bench_pressure(
        pokemon,
        excluded_attacker_serials=excluded_attacker_serials,
    )


def projected_prize_loss(view, *, active, bench) -> int:
    """相手が公開済みの1つのワザを使った時に失う最大サイド枚数。"""
    if active is None:
        return 0
    bench = tuple(bench)
    projection_by_target = {
        pokemon.serial: {
            (projection.attacker_serial, projection.attack_id):
                projection
            for projection in view.public_attack_projections(pokemon)
        }
        for pokemon in bench
    }
    losses = []
    for projection in view.public_attack_projections():
        loss = (
            _public_prize_value(view, active)
            if int(projection.active_damage) >= int(active.hp)
            else 0
        )
        key = (projection.attacker_serial, projection.attack_id)
        target_limit = (
            len(bench)
            if projection.bench_target_limit is None
            else max(0, int(projection.bench_target_limit))
        )
        if projection.bench_damage_distributable:
            candidates = tuple(
                pokemon
                for pokemon in bench
                if int(
                    getattr(
                        projection_by_target[pokemon.serial].get(key),
                        "fixed_bench_damage",
                        0,
                    )
                ) >= int(pokemon.hp)
            )
            distributed_loss = 0
            for count in range(1, min(target_limit, len(candidates)) + 1):
                for selected in combinations(candidates, count):
                    if sum(int(pokemon.hp) for pokemon in selected) > int(
                        projection.bench_damage_budget
                    ):
                        continue
                    distributed_loss = max(
                        distributed_loss,
                        sum(_public_prize_value(view, pokemon) for pokemon in selected),
                    )
            loss += distributed_loss
        else:
            bench_losses = sorted(
                (
                    _public_prize_value(view, pokemon)
                    for pokemon in bench
                    if int(
                        getattr(
                            projection_by_target[pokemon.serial].get(key),
                            "fixed_bench_damage",
                            0,
                        )
                    ) >= int(pokemon.hp)
                ),
                reverse=True,
            )
            loss += sum(bench_losses[:target_limit])
        losses.append(loss)
    return max(losses, default=0)


def survival_evolution_preserves_attack_plan(view, memory, option) -> bool:
    """生存進化が唯一の攻撃完成札・予約進化札を消費しないか判定する。"""
    if option is None or option.card_id is None:
        return True
    card_id = int(option.card_id)
    if sum(int(value) == card_id for value in view.hand_ids) != 1:
        return True
    reserved_serial = getattr(memory, "reserved_attacker_serial", None)
    energy_available = (
        not bool(view.current.get("energyAttached"))
        and any(
            int(value)
            in (
                int(CardId.BASIC_PSYCHIC),
                int(CardId.TELEPATH_PSYCHIC_ENERGY),
            )
            for value in view.hand_ids
        )
    )

    def attack_plan_requires(target) -> bool:
        if target is None:
            return False
        powers_attack_line = view.has_psychic_energy(target) or energy_available
        return bool(
            (
                target.area == int(Area.ACTIVE)
                and powers_attack_line
            )
            or (
                int(view.own_turn_number) in (2, 3)
                and int(view.own_prize_count) == 6
                and powers_attack_line
            )
            or (
                reserved_serial is not None
                and target.serial == int(reserved_serial)
            )
        )

    for candidate in view.options:
        target = candidate.target
        if (
            candidate.type != int(OptionType.EVOLVE)
            or candidate.card_id != card_id
            or target is None
            or option.target is None
            or target.serial == option.target.serial
        ):
            continue
        if attack_plan_requires(target):
            return False

    candy_is_legal = (
        card_id == int(CardId.ALAKAZAM)
        and int(CardId.RARE_CANDY) in view.hand_ids
        and any(
            candidate.type == int(OptionType.PLAY)
            and candidate.card_id == int(CardId.RARE_CANDY)
            for candidate in view.options
        )
    )
    if candy_is_legal:
        survival_target_serial = (
            None if option.target is None else option.target.serial
        )
        for abra in view.eligible_abras:
            if abra.serial == survival_target_serial:
                continue
            if attack_plan_requires(abra):
                return False
    return True


def evolution_prevents_public_bench_ko(view, option) -> bool:
    """合法な進化で、公開固定ベンチ打点によるKOを回避できるか。"""
    target = option.target
    if (
        target is None
        or target.area != int(Area.BENCH)
        or option.card_id is None
    ):
        return False
    pressure = max_public_bench_pressure(view, target)
    if pressure < int(target.hp):
        return False
    evolved = view.catalog.card(option.card_id)
    if evolved is None:
        return False
    damage_taken = max(0, int(target.max_hp) - int(target.hp))
    evolved_remaining_hp = max(0, int(evolved.hp) - damage_taken)
    return evolved_remaining_hp > pressure


def best_survival_retreat_target(view):
    """退避前より公開攻撃で失うサイドを減らす交代先を返す。"""
    active = view.active
    if active is None or active.serial is None:
        return None
    before = projected_prize_loss(view, active=active, bench=view.bench)
    if before <= 0:
        return None

    candidates = []
    for candidate in view.bench:
        if candidate.serial is None:
            continue
        after_bench = (
            active,
            *(
                pokemon
                for pokemon in view.bench
                if pokemon.serial != candidate.serial
            ),
        )
        after = projected_prize_loss(
            view,
            active=candidate,
            bench=after_bench,
        )
        candidates.append((after, candidate))

    exception = _setup_preservation_wall_candidates(view, active, before, candidates)
    if exception:
        return min(
            exception,
            key=lambda candidate: (_wall_role_rank(candidate), int(candidate.serial)),
        )
    strict_candidates = tuple(
        (after, candidate)
        for after, candidate in candidates
        if after < before
    )
    best = min(
        strict_candidates,
        key=lambda item: _survival_candidate_key(view, item[1], item[0]),
        default=None,
    )
    return None if best is None else best[1]


def _setup_preservation_wall_candidates(view, active, before, candidates):
    if (
        int(active.id) not in (int(CardId.ABRA), int(CardId.KADABRA))
        or active.appear_this_turn
        or active.energy_cards
        or any(
            int(pokemon.id) == int(CardId.ALAKAZAM)
            and view.has_psychic_energy(pokemon)
            for pokemon in view.field
        )
    ):
        return ()
    if any(
        after < before and int(candidate.id) != int(CardId.FEZANDIPITI_EX)
        for after, candidate in candidates
    ):
        return ()
    if not any(
        after < before and int(candidate.id) == int(CardId.FEZANDIPITI_EX)
        for after, candidate in candidates
    ):
        return ()
    return tuple(
        candidate
        for after, candidate in candidates
        if (
            after == before
            and int(candidate.id) in (int(CardId.DUNSPARCE), int(CardId.DUDUNSPARCE))
        )
    )


def _survival_candidate_key(view, candidate, after):
    return (
        after,
        0
        if (
            int(candidate.id) == int(CardId.ALAKAZAM)
            and view.has_psychic_energy(candidate)
        )
        else 1,
        _public_prize_value(view, candidate),
        _wall_role_rank(candidate),
        int(candidate.serial),
    )


def _wall_role_rank(pokemon) -> int:
    return {
        int(CardId.DUNSPARCE): 0,
        int(CardId.DUDUNSPARCE): 1,
        int(CardId.ABRA): 2,
        int(CardId.KADABRA): 3,
        int(CardId.ALAKAZAM): 4,
        int(CardId.FEZANDIPITI_EX): 9,
    }.get(int(pokemon.id), 5)
