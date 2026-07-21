from __future__ import annotations

from collections.abc import Sequence
from copy import copy
from dataclasses import replace
import json
import os
from typing import Callable

from cards import CardId
from catalog import CardCatalog
from memory import AgentMemory, update_known_deck_and_prizes
from model import Area, GameView, LegalOption, OptionType, SelectContext, SelectType
from proposals import IntentUpdate, PendingIntent, Proposal
from rule_manifest import assert_rule_coverage
from rules.deck_safety import proposal_is_deck_safe


Rule = Callable[[GameView, AgentMemory], Proposal | None]


class _FrozenDict(dict):
    """dict互換を保ったまま、規則からのGameView書き換えを禁止する。"""

    @staticmethod
    def _readonly(*_args, **_kwargs):
        raise TypeError("GameViewは読み取り専用です。")

    __setitem__ = _readonly
    __delitem__ = _readonly
    clear = _readonly
    pop = _readonly
    popitem = _readonly
    setdefault = _readonly
    update = _readonly
    __ior__ = _readonly


def _freeze(value):
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(child) for child in value)
    return value


def _isolated_view(view: GameView) -> GameView:
    """全規則が共有する、元観測と切り離した読み取り専用viewを作る。"""
    return GameView.from_observation(_freeze(view.raw), view.catalog)


def _isolated_memory(memory: AgentMemory) -> AgentMemory:
    """Create a cheap rule-evaluation snapshot without copying decision history."""
    isolated = copy(memory)
    isolated.known_deck = (
        None if memory.known_deck is None else memory.known_deck.copy()
    )
    isolated.known_absent_deck_ids = set(memory.known_absent_deck_ids)
    isolated.known_prize_ids = memory.known_prize_ids.copy()
    isolated.opponent_public_card_ids = set(memory.opponent_public_card_ids)
    isolated.opponent_attacker_ids = set(memory.opponent_attacker_ids)
    isolated.opponent_profile_candidates = set(memory.opponent_profile_candidates)
    isolated.opponent_actions = list(memory.opponent_actions)
    isolated.seen_public_log_keys = set(memory.seen_public_log_keys)
    isolated.trace = []
    isolated.last_seen_own_serials = set(memory.last_seen_own_serials)
    isolated.last_seen_own_field_ids = dict(memory.last_seen_own_field_ids)
    return isolated


def validate_selection(select: dict, indices: Sequence[int]) -> None:
    minimum = int(select.get("minCount", 0))
    maximum = int(select.get("maxCount", minimum))
    if len(indices) < minimum or len(indices) > maximum:
        raise ValueError("選択数がminCount/maxCountの範囲外です。")
    if any(not isinstance(index, int) or isinstance(index, bool) for index in indices):
        raise ValueError("選択肢インデックスは整数で指定してください。")
    if len(indices) != len(set(indices)):
        raise ValueError("同じ選択肢を重複選択しています。")
    option_count = len(select.get("option") or [])
    if any(index < 0 or index >= option_count for index in indices):
        raise ValueError("選択肢インデックスが範囲外です。")


def _selected_options(
    view: GameView, indices: Sequence[int]
) -> tuple[LegalOption, ...]:
    by_position = {option.position: option for option in view.options}
    return tuple(by_position[int(index)] for index in indices)


def _metadata_int(intent: PendingIntent, key: str) -> int | None:
    for name, value in intent.metadata:
        if name != key:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _metadata_str(intent: PendingIntent, key: str) -> str | None:
    return next(
        (str(value) for name, value in intent.metadata if name == key),
        None,
    )


def _metadata_card_ids(intent: PendingIntent, key: str) -> tuple[int, ...]:
    raw = _metadata_str(intent, key)
    if raw is None:
        return ()
    result: list[int] = []
    for value in raw.split(","):
        try:
            card_id = int(value)
        except ValueError:
            return ()
        if card_id not in result:
            result.append(card_id)
    return tuple(result)


def _expected_petrel_poke_pad_deferred_intent(
    view: GameView,
    proposal: Proposal,
    source: PendingIntent | None,
) -> PendingIntent | None:
    if (
        source is not None
        and source.kind == "RECOVER_POKEMON_LINES"
        and source.effect_card_id == int(CardId.SACRED_ASH)
        and source.matches(view)
        and _metadata_str(source, "purpose") == "sacred_ash"
        and _metadata_int(source, "follow_up_card_id")
        == int(CardId.POKE_PAD)
    ):
        follow_up_serial = _metadata_int(source, "follow_up_card_serial")
        if follow_up_serial is None:
            return None
        from rules.petrel import PETREL_POKE_PAD_DEFERRED_KIND

        return PendingIntent.deferred_main_from_view(
            view,
            kind=PETREL_POKE_PAD_DEFERRED_KIND,
            card_ids=(int(CardId.ABRA),),
            card_groups=((int(CardId.ABRA),),),
            max_cards=1,
            metadata=(("purpose", "sacred_ash"),),
            effect_card_id=CardId.POKE_PAD,
            effect_serial=follow_up_serial,
            main_context=SelectContext.MAIN,
        )
    if (
        source is None
        or source.kind != "PETREL_TRAINER_SEARCH"
        or source.effect_card_id != int(CardId.TEAM_ROCKETS_PETREL)
        or not source.matches(view)
        or _metadata_str(source, "purpose") != "basic_setup"
        or int(CardId.POKE_PAD) not in source.card_ids
    ):
        return None

    from rules.petrel import (
        PETREL_POKE_PAD_DEFERRED_KIND,
        PETREL_SETUP_BASIC_IDS_METADATA_KEY,
    )

    target_ids = _metadata_card_ids(source, PETREL_SETUP_BASIC_IDS_METADATA_KEY)
    if not target_ids or any(
        card_id not in (int(CardId.ABRA), int(CardId.DUNSPARCE))
        for card_id in target_ids
    ):
        return None
    selected = _selected_options(view, proposal.option_indices)
    if len(selected) != 1:
        return None
    poke_pad = selected[0]
    if (
        poke_pad.card_id != int(CardId.POKE_PAD)
        or poke_pad.card_serial is None
    ):
        return None
    return PendingIntent.deferred_main_from_view(
        view,
        kind=PETREL_POKE_PAD_DEFERRED_KIND,
        card_ids=target_ids,
        card_groups=(target_ids,),
        max_cards=1,
        metadata=source.metadata,
        effect_card_id=CardId.POKE_PAD,
        effect_serial=poke_pad.card_serial,
        main_context=SelectContext.MAIN,
    )


def _expected_recycled_abra_deploy_deferred_intent(
    view: GameView,
    proposal: Proposal,
    source: PendingIntent | None,
) -> PendingIntent | None:
    if (
        source is None
        or source.kind != "PETREL_POKE_PAD_BASIC_SETUP"
        or source.effect_card_id != int(CardId.POKE_PAD)
        or not source.matches(view)
        or _metadata_str(source, "purpose") != "sacred_ash"
    ):
        return None
    selected = _selected_options(view, proposal.option_indices)
    if len(selected) != 1:
        return None
    abra = selected[0]
    if abra.card_id != int(CardId.ABRA) or abra.card_serial is None:
        return None
    from rules.petrel import PETREL_RECYCLED_ABRA_DEPLOY_DEFERRED_KIND

    return PendingIntent.deferred_main_from_view(
        view,
        kind=PETREL_RECYCLED_ABRA_DEPLOY_DEFERRED_KIND,
        card_ids=(int(CardId.ABRA),),
        card_groups=((int(CardId.ABRA),),),
        max_cards=1,
        metadata=(("purpose", "sacred_ash"),),
        effect_card_id=CardId.ABRA,
        effect_serial=abra.card_serial,
        main_context=SelectContext.MAIN,
    )


def _with_petrel_poke_pad_deferred_intent(
    view: GameView,
    proposal: Proposal,
    memory: AgentMemory,
) -> Proposal:
    if (
        proposal.intent_update is not IntentUpdate.CLEAR
        or proposal.next_intent is not None
    ):
        return proposal
    expected = _expected_petrel_poke_pad_deferred_intent(
        view,
        proposal,
        memory.pending_intent,
    )
    if expected is None:
        expected = _expected_recycled_abra_deploy_deferred_intent(
            view,
            proposal,
            memory.pending_intent,
        )
    if expected is None:
        return proposal
    return replace(proposal, deferred_intent=expected)


def _allowed_intent_card_ids(
    intent: PendingIntent,
    advance_steps: int = 1,
) -> frozenset[int] | None:
    effect_card_id = int(intent.effect_card_id or -1)
    if intent.card_groups and effect_card_id in (
        int(CardId.HILDA),
        int(CardId.DAWN),
    ):
        group_index = (
            len(intent.card_groups)
            - len(intent.remaining_contexts)
            + max(0, int(advance_steps) - 1)
        )
        if 0 <= group_index < len(intent.card_groups):
            return frozenset(int(card_id) for card_id in intent.card_groups[group_index])
        raise ValueError("複数段階意図のカード群が現在の選択段階と一致しません。")
    if intent.card_groups:
        return frozenset(
            int(card_id)
            for group in intent.card_groups
            for card_id in group
        )
    if intent.card_ids:
        return frozenset(int(card_id) for card_id in intent.card_ids)
    return None


def _validate_intent_origin(view: GameView, proposal: Proposal) -> None:
    intent = proposal.next_intent
    if intent is None or not intent.has_complete_origin:
        raise ValueError("意図の発生元が完全ではありません。")
    if int(intent.created_turn) != int(view.current.get("turn", -1)) or int(
        intent.created_action_count
    ) != int(view.current.get("turnActionCount", -1)):
        raise ValueError("意図の発生手番が現在の選択と一致しません。")
    selected = _selected_options(view, proposal.option_indices)
    if intent.effect_card_id is None or intent.effect_serial is None:
        if any(option.type == int(OptionType.RETREAT) for option in selected):
            return
        raise ValueError("効果カードを持たない意図は、にげる選択からのみ開始できます。")
    if any(option.type == int(OptionType.ATTACK) for option in selected):
        # CABT の ATTACK option は attackId だけを持ち、発生元カードの
        # cardId / serial を含まない。攻撃の発生元は必ず現在のバトル場なので、
        # テレポートアタック等の継続意図はバトル場の実体で検証する。
        active = view.active
        if (
            active is not None
            and active.id == int(intent.effect_card_id)
            and active.serial == int(intent.effect_serial)
        ):
            return
        raise ValueError("選択したワザの発生元が意図の発生元と一致しません。")
    if not any(
        option.card_id == int(intent.effect_card_id)
        and option.card_serial == int(intent.effect_serial)
        for option in selected
    ):
        raise ValueError("選択したカードが意図の発生元と一致しません。")


def _validate_intent_choice(
    view: GameView,
    proposal: Proposal,
    intent: PendingIntent,
) -> None:
    if not intent.matches(view):
        raise ValueError("現在の選択画面が記録済み意図と一致しません。")
    expected = intent.advance(view, proposal.intent_advance_steps)
    if proposal.intent_update is IntentUpdate.SET:
        if expected is None or proposal.next_intent != expected:
            raise ValueError("次の意図が現在の選択段階と一致しません。")
    elif proposal.intent_update is IntentUpdate.CLEAR and expected is not None:
        raise ValueError("完了していない複数段階意図を消去しようとしています。")

    selected = _selected_options(view, proposal.option_indices)
    allowed_ids = _allowed_intent_card_ids(
        intent, proposal.intent_advance_steps
    )
    effect_card_id = int(intent.effect_card_id or -1)
    if effect_card_id == int(CardId.POKE_PAD) and allowed_ids is not None:
        option_ids = {
            int(option.card_id)
            for option in view.options
            if option.card_id is not None
        }
        if not option_ids.intersection(allowed_ids):
            from rules.poke_pad import plan_poke_pad_targets

            replanned_ids = next(
                (
                    frozenset(int(card_id) for card_id in plan.card_ids)
                    for plan in plan_poke_pad_targets(view)
                    if option_ids.intersection(plan.card_ids)
                ),
                frozenset(),
            )
            allowed_ids = replanned_ids
    if allowed_ids is not None and any(
        option.card_id is None or int(option.card_id) not in allowed_ids
        for option in selected
    ):
        raise ValueError("選択したカードが記録済み意図に含まれていません。")

    if effect_card_id == int(CardId.RARE_CANDY):
        if any(
            option.card_id != int(CardId.ALAKAZAM)
            or option.target is None
            or option.target.serial != intent.target_serial
            for option in selected
        ):
            raise ValueError("ふしぎなアメの進化先または対象が意図と一致しません。")
    elif effect_card_id == int(CardId.BOSSES_ORDERS):
        if any(
            option.source is None or option.source.serial != intent.target_serial
            for option in selected
        ):
            raise ValueError("ボスの指令の対象が意図と一致しません。")
    elif effect_card_id == int(CardId.ENHANCED_HAMMER):
        energy_serial = _metadata_int(intent, "energy_serial")
        if energy_serial is None or any(
            option.source is None
            or option.source.serial != intent.target_serial
            or option.card_serial != energy_serial
            for option in selected
        ):
            raise ValueError("改造ハンマーの対象エネルギーが意図と一致しません。")


def _validate_petrel_poke_pad_deferred_handoff(
    view: GameView,
    proposal: Proposal,
    source: PendingIntent,
) -> None:
    expected = _expected_petrel_poke_pad_deferred_intent(
        view,
        proposal,
        source,
    )
    if expected is None:
        expected = _expected_recycled_abra_deploy_deferred_intent(
            view,
            proposal,
            source,
        )
    if expected is None:
        if proposal.deferred_intent is None:
            return
        raise ValueError("ラムダからポケパッドへのdeferred意図が発生元と一致しません。")
    if proposal.deferred_intent != expected:
        raise ValueError("ラムダからポケパッドへのdeferred意図が発生元と一致しません。")


def _validate_reserved_petrel_poke_pad_main(
    view: GameView,
    proposal: Proposal,
    memory: AgentMemory,
) -> None:
    deferred = memory.pending_intent
    if deferred is None or not deferred.matches_deferred_main(view):
        return
    from rules.petrel import (
        PETREL_RECYCLED_ABRA_DEPLOY_DEFERRED_KIND,
        PETREL_POKE_PAD_DEFERRED_KIND,
        _deferred_recycled_abra_deploy_proposal,
        _deferred_poke_pad_proposal,
    )

    if deferred.kind not in {
        PETREL_POKE_PAD_DEFERRED_KIND,
        PETREL_RECYCLED_ABRA_DEPLOY_DEFERRED_KIND,
    }:
        return
    selected = _selected_options(view, proposal.option_indices)
    uses_reserved_serial = any(
        option.type == int(OptionType.PLAY)
        and option.card_id == int(deferred.effect_card_id)
        and option.card_serial == deferred.effect_serial
        for option in selected
    )
    if not uses_reserved_serial:
        return
    canonical = (
        _deferred_poke_pad_proposal(view, memory)
        if deferred.kind == PETREL_POKE_PAD_DEFERRED_KIND
        else _deferred_recycled_abra_deploy_proposal(view, memory)
    )
    if (
        canonical is None
        or proposal.intent_update is not canonical.intent_update
        or proposal.option_indices != canonical.option_indices
        or proposal.next_intent != canonical.next_intent
    ):
        raise ValueError(
            "予約した回収経路は、記録済みの検索・展開意図で使用してください。"
        )


def validate_proposal(
    view: GameView,
    proposal: Proposal,
    memory: AgentMemory,
) -> None:
    """選択数に加え、カード効果を開始・継続する意味まで検証する。"""
    validate_selection(view.select, proposal.option_indices)
    is_main = (
        int(view.select.get("type", -1)) == int(SelectType.MAIN)
        and int(view.select.get("context", -1)) == int(SelectContext.MAIN)
    )
    if is_main and proposal.intent_update is IntentUpdate.SET:
        _validate_intent_origin(view, proposal)
    elif (
        not is_main
        and proposal.intent_update in (IntentUpdate.SET, IntentUpdate.CLEAR)
    ):
        if memory.pending_intent is None:
            raise ValueError("継続する記録済み意図がありません。")
        _validate_intent_choice(view, proposal, memory.pending_intent)
    elif not is_main and proposal.intent_update is IntentUpdate.UNCHANGED:
        effect = view.select.get("effect")
        discard_count = max(0, int(view.hand_size) - 3)
        looks_like_opponent_hand_reduction = (
            isinstance(effect, dict)
            and effect.get("playerIndex") is not None
            and int(effect["playerIndex"]) != int(view.own_index)
            and int(view.select.get("type", -1)) == int(SelectType.CARD)
            and int(view.select.get("context", -1)) == int(SelectContext.DISCARD)
            and int(view.select.get("minCount", -1)) == discard_count
            and int(view.select.get("maxCount", -1)) == discard_count
        )
        if looks_like_opponent_hand_reduction:
            from rules.disruption import is_exact_xerosic_contract

            if (
                not is_exact_xerosic_contract(view)
                or "PLAYBOOK-XEROSIC-KEEP" not in proposal.rule_ids
            ):
                raise ValueError(
                    "intentなしの相手手札トラッシュ選択はクセロシキ専用規則だけが扱えます。"
                )
    if is_main:
        _validate_reserved_petrel_poke_pad_main(view, proposal, memory)
    if not is_main and memory.pending_intent is not None:
        _validate_petrel_poke_pad_deferred_handoff(
            view,
            proposal,
            memory.pending_intent,
        )
    elif proposal.deferred_intent is not None:
        if is_main or memory.pending_intent is None:
            raise ValueError("deferred意図を引き継ぐ効果選択がありません。")
    if not proposal_is_deck_safe(
        view,
        proposal,
        pending_intent=memory.pending_intent,
    ):
        raise ValueError("山札安全予算を超える任意行動です。")


def _default_rules(prefer_first: bool) -> tuple[tuple[Rule, ...], tuple[Rule, ...], tuple[Callable, ...]]:
    # 遅延importにより、単体テストではPolicyの取引契約だけを独立検証できる。
    from rules.attack import propose_attack
    from rules.development import propose_development
    from rules.draw_engine import propose_draw
    from rules.evolution import propose_evolution
    from rules.prompts import resolve_prompt
    from rules.protection import propose_protection
    from rules.recovery import propose_recovery
    from rules.search import propose_search
    from rules.setup import propose_setup
    from rules.petrel import propose_petrel

    def setup_rule(view: GameView, memory: AgentMemory) -> Proposal | None:
        return propose_setup(view, memory, prefer_first)

    main_rules: tuple[Rule, ...] = (
        propose_attack,
        propose_draw,
        propose_evolution,
        propose_petrel,
        propose_development,
        propose_search,
        propose_protection,
        propose_recovery,
    )
    prompt_rules: tuple[Rule, ...] = (
        setup_rule,
        resolve_prompt,
        propose_draw,
        propose_evolution,
        propose_recovery,
    )
    coverage_rules = (
        propose_setup,
        resolve_prompt,
        propose_attack,
        propose_draw,
        propose_evolution,
        propose_petrel,
        propose_development,
        propose_search,
        propose_protection,
        propose_recovery,
        update_known_deck_and_prizes,
    )
    return main_rules, prompt_rules, coverage_rules


class Policy:
    def __init__(
        self,
        prefer_first: bool = False,
        *,
        main_rules: tuple[Rule, ...] | None = None,
        prompt_rules: tuple[Rule, ...] | None = None,
        fallback_rule: Rule | None = None,
        enforce_rule_coverage: bool = True,
    ) -> None:
        from rules.fallback import propose_fallback

        using_defaults = main_rules is None and prompt_rules is None
        coverage_rules: tuple[Callable, ...] = ()
        if using_defaults:
            main_rules, prompt_rules, coverage_rules = _default_rules(prefer_first)
        self.main_rules = tuple(main_rules or ())
        self.prompt_rules = tuple(prompt_rules or ())
        self.fallback_rule = fallback_rule or propose_fallback
        self.last_rejections: list[dict] = []
        self.last_candidates: list[dict] = []
        if enforce_rule_coverage:
            if not using_defaults:
                raise ValueError("規則網羅検査を行うPolicyには既定規則が必要です。")
            assert_rule_coverage(
                (*coverage_rules, self.fallback_rule),
                static_rule_ids=("PLAYBOOK-CARD-VERSIONS",),
            )

    @staticmethod
    def _is_main(view: GameView) -> bool:
        return (
            int(view.select.get("type", -1)) == int(SelectType.MAIN)
            and int(view.select.get("context", -1)) == int(SelectContext.MAIN)
        )

    def choose(self, view: GameView, memory: AgentMemory) -> Proposal:
        evaluation_view = _isolated_view(view)
        rules = (
            self.main_rules if self._is_main(evaluation_view) else self.prompt_rules
        )
        candidates: list[tuple[int, Proposal]] = []
        self.last_rejections = []
        self.last_candidates = []
        for order, rule in enumerate((*rules, self.fallback_rule)):
            # 規則評価は試合memoryのコピー上で行い、不採用proposalの副作用を隔離する。
            try:
                proposal = rule(evaluation_view, _isolated_memory(memory))
            except Exception as error:
                self.last_rejections.append({
                    "rule": getattr(rule, "__name__", type(rule).__name__),
                    "error_type": type(error).__name__,
                    "error": "ルール評価中に例外が発生しました。",
                })
                continue
            if proposal is None:
                continue
            try:
                proposal = _with_petrel_poke_pad_deferred_intent(
                    evaluation_view,
                    proposal,
                    memory,
                )
                validate_proposal(evaluation_view, proposal, memory)
            except ValueError as error:
                self.last_rejections.append({
                    "rule": getattr(rule, "__name__", type(rule).__name__),
                    "reason": proposal.reason,
                    "indices": tuple(proposal.option_indices),
                    "error": str(error),
                })
                continue
            candidates.append((order, proposal))
            committed_intent = (
                proposal.next_intent
                if proposal.intent_update is IntentUpdate.SET
                else proposal.deferred_intent
                if proposal.intent_update is IntentUpdate.CLEAR
                else None
            )
            self.last_candidates.append({
                "rule": getattr(rule, "__name__", type(rule).__name__),
                "priority": int(proposal.priority),
                "reason": proposal.reason,
                "alternative": proposal.alternative,
                "indices": tuple(proposal.option_indices),
                "rule_ids": tuple(proposal.rule_ids),
                "facts": tuple(proposal.facts),
                "next_intent": (
                    None
                    if proposal.next_intent is None
                    else proposal.next_intent.kind
                ),
                "next_intent_card_groups": (
                    ()
                    if proposal.next_intent is None
                    else tuple(
                        tuple(group)
                        for group in proposal.next_intent.card_groups
                    )
                ),
                "committed_intent": (
                    None if committed_intent is None else committed_intent.kind
                ),
                "committed_intent_card_groups": (
                    ()
                    if committed_intent is None
                    else tuple(
                        tuple(group)
                        for group in committed_intent.card_groups
                    )
                ),
                "committed_intent_effect_serial": (
                    None
                    if committed_intent is None
                    else committed_intent.effect_serial
                ),
            })
        if not candidates:
            details = "; ".join(item["error"] for item in self.last_rejections)
            raise RuntimeError(f"合法な提案がありません。{details}")
        _, selected = max(
            candidates,
            key=lambda item: (int(item[1].priority), -int(item[0])),
        )
        return selected


_HIDDEN_OPPONENT_AREAS = frozenset(
    {int(Area.HAND), int(Area.DECK), int(Area.PRIZE)}
)


def _card_signature(value: object) -> tuple[int | None, int | None]:
    if not isinstance(value, dict):
        return (None, None)
    card_id = value.get("id")
    serial = value.get("serial")
    return (
        None if card_id is None else int(card_id),
        None if serial is None else int(serial),
    )


def _decision_option_signature(
    view: GameView, option: LegalOption
) -> tuple[object, ...]:
    owner = int(option.raw.get("playerIndex", view.own_index))
    area_value = option.raw.get("area")
    area = None if area_value is None else int(area_value)
    hidden = owner != view.own_index and area in _HIDDEN_OPPONENT_AREAS
    return (
        option.position,
        option.type,
        owner,
        area,
        option.raw.get("index"),
        option.raw.get("inPlayArea"),
        option.raw.get("inPlayIndex"),
        option.raw.get("energyIndex"),
        option.raw.get("toolIndex"),
        option.raw.get("count"),
        option.attack_id,
        None if hidden else option.card_id,
        None if hidden else option.card_serial,
        None if hidden or option.source is None else option.source.serial,
        None if hidden or option.target is None else option.target.serial,
    )


def _decision_key(view: GameView) -> tuple[object, ...]:
    """同一CABTプロンプトの再送だけを識別する公開情報キー。"""
    return (
        int(view.current.get("turn", 0)),
        int(view.current.get("turnActionCount", 0)),
        int(view.own_index),
        int(view.select.get("type", -1)),
        int(view.select.get("context", -1)),
        int(view.select.get("minCount", 0)),
        int(view.select.get("maxCount", 0)),
        _card_signature(view.select.get("effect")),
        _card_signature(view.select.get("contextCard")),
        tuple(_decision_option_signature(view, option) for option in view.options),
    )


class AgentSession:
    def __init__(
        self,
        prefer_first: bool = False,
        catalog: CardCatalog | None = None,
        policy: Policy | None = None,
    ) -> None:
        self.memory = AgentMemory()
        self.policy = policy or Policy(prefer_first)
        self.catalog = catalog or CardCatalog.from_cg()
        self._last_decision_key: tuple[object, ...] | None = None
        self._last_decision_indices: tuple[int, ...] | None = None

    def decide(self, obs_dict: dict) -> list[int]:
        view = GameView.from_observation(obs_dict, self.catalog)
        decision_key = _decision_key(view)
        if (
            decision_key == self._last_decision_key
            and self._last_decision_indices is not None
        ):
            return list(self._last_decision_indices)
        self.memory.observe_game(view)
        self._prune_strategic_roles(view)
        self.memory.observe_public_opponent(view)
        update_known_deck_and_prizes(view, self.memory)
        proposal = self.policy.choose(view, self.memory)
        indices = list(proposal.option_indices)
        validate_proposal(view, proposal, self.memory)
        self._commit_intent(proposal)
        self._commit_strategic_roles(view, proposal)
        trace_decision(
            view,
            proposal,
            self.memory,
            rejections=self.policy.last_rejections,
            candidates=self.policy.last_candidates,
        )
        self._last_decision_key = decision_key
        self._last_decision_indices = tuple(indices)
        return indices

    def _commit_intent(self, proposal: Proposal) -> None:
        if proposal.intent_update is IntentUpdate.SET:
            self.memory.pending_intent = proposal.next_intent
        elif proposal.intent_update is IntentUpdate.CLEAR:
            self.memory.pending_intent = proposal.deferred_intent

    def _prune_strategic_roles(self, view: GameView) -> None:
        attacker_serials = {
            pokemon.serial
            for pokemon in view.field
            if pokemon.serial is not None
            and int(pokemon.id) in (
                int(CardId.ABRA),
                int(CardId.KADABRA),
                int(CardId.ALAKAZAM),
            )
        }
        abra_serials = {
            pokemon.serial
            for pokemon in view.field
            if pokemon.serial is not None and int(pokemon.id) == int(CardId.ABRA)
        }
        if (
            self.memory.reserved_attacker_serial is not None
            and self.memory.reserved_attacker_serial not in attacker_serials
        ):
            self.memory.reserved_attacker_serial = None
        if (
            self.memory.protected_abra_serial is not None
            and self.memory.protected_abra_serial not in abra_serials
        ):
            self.memory.protected_abra_serial = None

    def _commit_strategic_roles(self, view: GameView, proposal: Proposal) -> None:
        by_position = {option.position: option for option in view.options}

        def remember(serial: int | None, *, protect: bool, override: bool) -> None:
            if serial is None:
                return
            value = int(serial)
            if override or self.memory.reserved_attacker_serial is None:
                self.memory.reserved_attacker_serial = value
            if protect and (override or self.memory.protected_abra_serial is None):
                self.memory.protected_abra_serial = value

        intent = proposal.next_intent
        if (
            intent is not None
            and intent.target_serial is not None
            and intent.kind in {
                "BENCH_PSYCHIC_BASICS",
                "RARE_CANDY_ATTACKER",
                "SEARCH_ALAKAZAM_AFTER_CANDY",
            }
        ):
            target = next(
                (
                    pokemon for pokemon in view.field
                    if pokemon.serial == int(intent.target_serial)
                ),
                None,
            )
            remember(
                intent.target_serial,
                protect=target is not None and int(target.id) == int(CardId.ABRA),
                override=True,
            )

        context = int(view.select.get("context", SelectContext.MAIN))
        for position in proposal.option_indices:
            option = by_position.get(int(position))
            if option is None:
                continue
            if (
                option.type == int(OptionType.ATTACH)
                and option.card_id in (
                    int(CardId.BASIC_PSYCHIC),
                    int(CardId.TELEPATH_PSYCHIC_ENERGY),
                )
                and option.target is not None
                and int(option.target.id) in (
                    int(CardId.ABRA),
                    int(CardId.KADABRA),
                    int(CardId.ALAKAZAM),
                )
            ):
                remember(
                    option.target.serial,
                    protect=int(option.target.id) == int(CardId.ABRA),
                    override=True,
                )
            elif (
                option.type == int(OptionType.EVOLVE)
                and option.target is not None
                and option.card_id in (int(CardId.KADABRA), int(CardId.ALAKAZAM))
            ):
                remember(
                    option.target.serial,
                    protect=(
                        int(option.target.id) == int(CardId.ABRA)
                        and option.card_id != int(CardId.ALAKAZAM)
                    ),
                    override=False,
                )
            elif (
                option.card_id == int(CardId.ABRA)
                and option.card_serial is not None
                and (
                    option.type == int(OptionType.PLAY)
                    or context in (
                        int(SelectContext.SETUP_ACTIVE_POKEMON),
                        int(SelectContext.SETUP_BENCH_POKEMON),
                        int(SelectContext.TO_BENCH),
                    )
                )
            ):
                remember(option.card_serial, protect=True, override=False)


def trace_decision(
    view: GameView,
    proposal: Proposal,
    memory: AgentMemory,
    *,
    rejections: list[dict] | None = None,
    candidates: list[dict] | None = None,
) -> None:
    committed_intent = (
        proposal.next_intent
        if proposal.intent_update is IntentUpdate.SET
        else proposal.deferred_intent
        if proposal.intent_update is IntentUpdate.CLEAR
        else None
    )
    selected_items: list[dict] = []
    for position in proposal.option_indices:
        option = next(
            (
                candidate
                for candidate in view.options
                if candidate.position == position
            ),
            None,
        )
        if option is None:
            continue
        owner = int(option.raw.get("playerIndex", view.own_index))
        area_value = option.raw.get("area")
        area = None if area_value is None else int(area_value)
        redacted = (
            owner != view.own_index and area in _HIDDEN_OPPONENT_AREAS
        )
        selected_items.append({
            "position": option.position,
            "type": option.type,
            "card_id": None if redacted else option.card_id,
            "card_serial": None if redacted else option.card_serial,
            "source_serial": (
                None
                if redacted or option.source is None
                else option.source.serial
            ),
            "target_serial": (
                None
                if redacted or option.target is None
                else option.target.serial
            ),
            "attack_id": option.attack_id,
            "redacted": redacted,
        })
    selected = tuple(selected_items)
    entry = {
        "turn": int(view.current.get("turn", 0)),
        "own_turn": view.own_turn_number,
        "rule_ids": tuple(proposal.rule_ids),
        "reason": proposal.reason,
        "alternative": proposal.alternative,
        "facts": tuple(proposal.facts),
        "indices": tuple(proposal.option_indices),
        "selected": selected,
        "hand_size": view.hand_size,
        "required_hand_for_ko": view.required_hand_for_active_ko,
        "intent_update": proposal.intent_update.value,
        "next_intent": (
            None if proposal.next_intent is None else proposal.next_intent.kind
        ),
        "next_intent_card_groups": (
            ()
            if proposal.next_intent is None
            else tuple(tuple(group) for group in proposal.next_intent.card_groups)
        ),
        "committed_intent": (
            None if committed_intent is None else committed_intent.kind
        ),
        "committed_intent_card_groups": (
            ()
            if committed_intent is None
            else tuple(tuple(group) for group in committed_intent.card_groups)
        ),
        "committed_intent_effect_serial": (
            None if committed_intent is None else committed_intent.effect_serial
        ),
        "candidates": tuple(candidates or ()),
        "rejections": tuple(rejections or ()),
    }
    memory.trace.append(entry)
    if os.environ.get("PTCG_AGENT_TRACE") == "1":
        print(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
