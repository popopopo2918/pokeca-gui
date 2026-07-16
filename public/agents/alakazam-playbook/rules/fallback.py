from __future__ import annotations

from cards import AttackId, CardId
from model import OptionType, SelectContext, SelectType
from proposals import Proposal, covers


def _identity_key(option) -> tuple[int, int, int, int]:
    return (
        10**9 if option.card_id is None else int(option.card_id),
        10**9 if option.card_serial is None else int(option.card_serial),
        int(option.type),
        int(option.position),
    )


def _first_by_identity(options):
    return min(options, key=_identity_key, default=None)


@covers("PLAYBOOK-NO-RANDOM", "PLAYBOOK-NO-ENRICHING-RETREAT")
def propose_fallback(view, memory) -> Proposal:
    del memory
    minimum = int(view.select.get("minCount", 1))
    maximum = int(view.select.get("maxCount", minimum))
    select_type = int(view.select.get("type", SelectType.MAIN))
    context = int(view.select.get("context", SelectContext.MAIN))

    if minimum == 0 and select_type != int(SelectType.MAIN):
        return Proposal(
            (),
            1,
            "目的が確定していない任意選択では0枚を選ぶ",
            ("PLAYBOOK-NO-RANDOM",),
            alternative="optional=0",
        )

    if select_type == int(SelectType.MAIN):
        hand_power = _first_by_identity(
            option
            for option in view.options
            if option.type == int(OptionType.ATTACK)
            and option.attack_id == int(AttackId.HAND_POWER)
        )
        if hand_power is not None:
            return Proposal(
                (hand_power.position,),
                1,
                "既知のハンドパワーを使って番を終える",
                ("PLAYBOOK-NO-RANDOM",),
                alternative="known-attack",
            )
        end = _first_by_identity(
            option for option in view.options
            if option.type == int(OptionType.END)
        )
        if end is not None:
            return Proposal(
                (end.position,),
                1,
                "にげる計画を作れないため安全に番を終える",
                ("PLAYBOOK-NO-RANDOM", "PLAYBOOK-NO-ENRICHING-RETREAT"),
                alternative="end-before-unplanned-retreat",
            )

    effect = view.select.get("effect")
    if (
        context == int(SelectContext.DISCARD_ENERGY)
        and effect is None
    ):
        non_enriching = tuple(
            option for option in view.options
            if option.card_id != int(CardId.ENRICHING_ENERGY)
        )
        candidate = _first_by_identity(non_enriching)
        if candidate is None:
            candidate = _first_by_identity(view.options)
        if candidate is not None:
            return Proposal(
                (candidate.position,),
                1,
                "開始済みにげるの必須コストを払い、リッチを可能な限り温存する",
                ("PLAYBOOK-NO-RANDOM", "PLAYBOOK-NO-ENRICHING-RETREAT"),
                alternative=(
                    "only-enriching-remained-after-unplanned-retreat"
                    if candidate.card_id == int(CardId.ENRICHING_ENERGY)
                    else "discard-non-enriching"
                ),
            )

    if select_type == int(SelectType.YES_NO):
        no = _first_by_identity(
            option for option in view.options
            if option.type == int(OptionType.NO)
        )
        if no is not None:
            return Proposal(
                (no.position,),
                1,
                "未知のYES/NO効果は起動しない",
                ("PLAYBOOK-NO-RANDOM",),
                alternative="decline-unknown-effect",
            )

    ranked = sorted(view.options, key=_identity_key)
    chosen = tuple(option.position for option in ranked[:minimum])
    return Proposal(
        chosen,
        1,
        "必須数だけ公開カード識別子順で決定的に選ぶ",
        ("PLAYBOOK-NO-RANDOM",),
        alternative=f"required={minimum};max={maximum}",
    )
