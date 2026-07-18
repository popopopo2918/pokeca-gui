from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    source: str
    summary: str


_FLOW = {
    "FLOW-SETUP-ACTIVE": "スピンロトム、ノコッチ、ケーシィ、コダック、シェイミ、ゲノセクト、キチキギスexの順で前を選ぶ",
    "FLOW-SETUP-FAN-CALL": "最初の自分の番にファンコールでノコッチを可能な限り取る",
    "FLOW-DEVELOP-ALAKAZAM": "完成済みフーディンを攻撃可能にする",
    "FLOW-DEVELOP-KADABRA": "進化可能ユンゲラーからフーディンへつなぐ",
    "FLOW-DEVELOP-ABRA": "進化可能ケーシィを残してアメとフーディンを探す",
    "FLOW-DRAW-FEZANDIPITI": "条件を満たすキチキギスexのさかてにとるを先に使う",
    "FLOW-DRAW-EVOLUTIONS": "フーディンとユンゲラーの進化時ドローを使う",
    "FLOW-ATTACK-ENERGY": "原則はフーディンへ付け、初動のスピンロトム70点で確実にKOできる時だけ例外とする",
    "FLOW-ATTACK-HAND": "展開後に最速KOを選び、通常はハンドパワー、初動はスピンロトム70点も評価する",
    "FLOW-ATTACK-BOSS": "倒せるベンチがいるならボスの指令を評価する",
    "FLOW-ATTACK-HAMMER": "阻害する特殊エネルギーへ改造ハンマーを使う",
    "FLOW-PROTECT-SHAYMIN": "通常ダメージでベンチを狙う相手にはシェイミを置く",
    "FLOW-PROTECT-PSYDUCK": "自身をきぜつさせる特性にはコダックを置く",
    "FLOW-PROTECT-GENESECT": "アンフェアスタンプ対策にゲノセクトへふうせんを付ける",
}
_PLAYBOOK = {
    "PLAYBOOK-CARD-VERSIONS": "ノコッチ305とシェイミ343を使う",
    "PLAYBOOK-ABRA-ZERO": "場にケーシィ0体ならポケパッドでケーシィを優先する",
    "PLAYBOOK-ABRA-LIMIT": "ケーシィは最大3体までにする",
    "PLAYBOOK-POFFIN": "なかよしポフィンでケーシィと不足するノコッチを展開する",
    "PLAYBOOK-POKE-PAD": "ポケパッドでルールを持たない不足ポケモンを取る",
    "PLAYBOOK-RARE-CANDY": "前の番からいるケーシィをフーディンへ直接進化する",
    "PLAYBOOK-T1-TELEPATH": "1ターン目に攻撃役ケーシィへテレパス超を優先する",
    "PLAYBOOK-TELEPATH-LIMIT": "テレパス超でもケーシィ3体上限とベンチ枠を守る",
    "PLAYBOOK-ENRICHING-CONDITION": "攻撃役と退避経路を確保できる時だけリッチを使い、ノココッチの先行ドローで逃げエネルギーを探せる局面では手貼り権を残す",
    "PLAYBOOK-ENRICHING-RECYCLE": "リッチをノココッチで山札へ戻し、終盤はふうせんも戻す束へ加えて再利用する",
    "PLAYBOOK-NO-ENRICHING-RETREAT": "リッチを逃げるコストとして捨てない",
    "PLAYBOOK-PRESERVE-ABRA": "アメ用ケーシィを最低1体残し、唯一の個体が前で公開攻撃脅威にさらされる時はふうせんで退避する",
    "PLAYBOOK-MAX-DRAW": "通常1、リッチ4、ノココッチ9、フーディン3、ユンゲラー2を評価する",
    "PLAYBOOK-CANDY-FIRST": "検索可能なフーディンより検索不能なアメを自然ドローで先に探す",
    "PLAYBOOK-HILDA": "トウコは進化ポケモンとエネルギーを取り、終盤に安全枠が1枚なら完成済み攻撃役の超だけを取る",
    "PLAYBOOK-T1-HILDA-SETUP": "1ターン目のトウコで次ターンのドロー装置とテレパス超を準備する",
    "PLAYBOOK-DAWN": "ヒカリはたね、1進化、2進化を取る",
    "PLAYBOOK-AIR-BALLOON": "完成済み攻撃役への退避導線を任意展開より優先し、山札最低残数ではノココッチの循環束へ加える",
    "PLAYBOOK-BASIC-PSYCHIC": "ハンドパワーには超エネルギーが必要でリッチは代用できない",
    "PLAYBOOK-HAND-THRESHOLD": "必要手札は相手残りHPを20で切り上げる",
    "PLAYBOOK-STOP-WHEN-KO": "KO可能後は不要なカードを使わない",
    "PLAYBOOK-BOARD-MINIMUM": "サイドを取り切らない限り攻撃後もベンチを残す",
    "PLAYBOOK-PROMOTE-COMPLETE": "完成済みフーディンを再構築より優先して前へ出す",
    "PLAYBOOK-T3-KADABRA": "2ターン目はノコッチの先取り検索よりユンゲラー2枚ドローを先に使い、失敗後も通常進化で3ターン目攻撃する",
    "PLAYBOOK-SACRED-ASH": "せいなるはいでポケモンを再利用する",
    "PLAYBOOK-LANAS-AID": "スイレンのお世話でルールなしポケモンと基本超を戻す",
    "PLAYBOOK-ENHANCED-HAMMER": "改造ハンマーは相手の特殊エネルギーだけを対象にし、初回攻撃前はドロー進化を先に行う",
    "PLAYBOOK-BOSS": "ボスの指令は倒せるベンチを呼ぶ目的で使うが、初動はヒカリ・トウコによる展開を優先する",
    "PLAYBOOK-BATTLE-CAGE": "バトルコロシアムはダメカンを防ぎ通常ダメージは防がない",
    "PLAYBOOK-SHAYMIN-DAMAGE": "シェイミはルールなしベンチへの通常ダメージを防ぐ",
    "PLAYBOOK-PSYDUCK": "コダックは自身をきぜつさせる特性を止める",
    "PLAYBOOK-GENESECT": "ゲノセクトはどうぐ付きでACE SPECを止め山札アクセスには使わない",
    "PLAYBOOK-FEZANDIPITI": "前の相手番にきぜつがあればキチキギスexを評価する",
    "PLAYBOOK-FEZANDIPITI-DEPLOY": "前の相手番のきぜつ後、攻撃未成立ならキチキギスexを出して3枚ドローへつなぐ",
    "PLAYBOOK-SEARCH-INTENT": "検索理由と実際のカード・対象を一致させる",
    "PLAYBOOK-PRIZE-INFERENCE": "山札を見た時だけ固定リストから自分のサイドを確定する",
    "PLAYBOOK-NO-RANDOM": "未知局面でも無作為選択をしない",
    "PLAYBOOK-FIRST-SECOND": "先攻後攻を自分基準ターン数で独立して扱う",
    "PLAYBOOK-DECK-SAFETY": "山札10枚以下では残りサイド分を残し、最低残数ではふうせん付きノココッチで循環用の1枚を補う",
}
SOURCE_RULES = tuple(
    [RuleSpec(rule_id, "flowchart", summary) for rule_id, summary in _FLOW.items()]
    + [RuleSpec(rule_id, "playbook", summary) for rule_id, summary in _PLAYBOOK.items()]
)


def assert_rule_coverage(
    functions: Iterable[Callable], static_rule_ids: Iterable[str] = ()
) -> None:
    required = {rule.rule_id for rule in SOURCE_RULES}
    covered = set(static_rule_ids)
    covered.update(
        rule_id
        for function in functions
        for rule_id in getattr(function, "source_rule_ids", ())
    )
    missing = sorted(required - covered)
    unknown = sorted(covered - required)
    problems = []
    if missing:
        problems.append(f"未実装の戦略規則: {', '.join(missing)}")
    if unknown:
        problems.append(f"未知の戦略規則: {', '.join(unknown)}")
    if problems:
        raise AssertionError("; ".join(problems))
