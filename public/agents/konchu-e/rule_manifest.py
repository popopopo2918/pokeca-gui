from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    source: str
    summary: str


_FLOW = {
    "FLOW-SETUP-ACTIVE": "現行デッキではノコッチ、ケーシィ、やむを得ない場合のキチキギスexの順で前を選ぶ",
    "FLOW-DEVELOP-ALAKAZAM": "完成済みフーディンを攻撃可能にする",
    "FLOW-DEVELOP-KADABRA": "進化可能ユンゲラーからフーディンへつなぐ",
    "FLOW-DEVELOP-ABRA": "進化可能ケーシィを残してアメとフーディンを探す",
    "FLOW-DRAW-FEZANDIPITI": "条件を満たすキチキギスexのさかてにとるを先に使う",
    "FLOW-DRAW-EVOLUTIONS": "フーディンとユンゲラーの進化時ドローを使う",
    "FLOW-ATTACK-ENERGY": "現在または次番のフーディン系統へ超エネルギーを付け、最速攻撃と連続KOを成立させる",
    "FLOW-ATTACK-HAND": "展開後にハンドパワーの最速KOを選び、2ターン目だけ非KO攻撃も評価する",
    "FLOW-ATTACK-BOSS": "倒せるベンチがいるならボスの指令を評価する",
    "FLOW-ATTACK-HAMMER": "Hand PowerのKOを解禁する妨害エネルギーを最優先し、一般妨害は主力系統ベンチ、複数供給、倒せないバトル場、その他ベンチ、serial順で選ぶ",
    "FLOW-PROTECT-SHAYMIN": "現行デッキ非採用のシェイミは旧観測互換としてのみ効果を判定する",
    "FLOW-PROTECT-PSYDUCK": "現行デッキ非採用のコダックは旧観測互換としてのみ効果を判定する",
    "FLOW-PROTECT-GENESECT": "現行デッキ非採用のゲノセクトとふうせんは旧観測互換としてのみ効果を判定する",
}
_PLAYBOOK = {
    "PLAYBOOK-CARD-VERSIONS": "現行デッキのノコッチ305と妨害エネルギー等の参照カードIDを固定する",
    "PLAYBOOK-ABRA-ZERO": "場にケーシィ0体ならポケパッドでケーシィを優先する",
    "PLAYBOOK-ABRA-LIMIT": "ケーシィは最大4体までにする",
    "PLAYBOOK-POFFIN": "なかよしポフィンでケーシィと不足するノコッチを展開する",
    "PLAYBOOK-POKE-PAD": "ポケパッドでルールを持たない不足ポケモンを取る",
    "PLAYBOOK-RARE-CANDY": "前の番からいるケーシィをフーディンへ直接進化する",
    "PLAYBOOK-T1-TELEPATH": "1ターン目に攻撃役ケーシィへテレパス超を優先する",
    "PLAYBOOK-TELEPATH-LIMIT": "テレパス超でもケーシィ4体上限とベンチ枠を守る",
    "PLAYBOOK-ENRICHING-CONDITION": "攻撃役と退避経路を確保できる時だけリッチを使い、ノココッチの先行ドローで逃げエネルギーを探せる局面では手貼り権を残す",
    "PLAYBOOK-ENRICHING-RECYCLE": "リッチをノココッチで山札へ戻して再利用する",
    "PLAYBOOK-NO-ENRICHING-RETREAT": "同番攻撃・KOまたは連続KO維持の最後の手段以外ではリッチを逃げるコストとして捨てない",
    "PLAYBOOK-PRESERVE-ABRA": "アメ用ケーシィを最低1体残し、前の個体はテレポートアタック等で超を失わず退避する",
    "PLAYBOOK-MAX-DRAW": "通常1、リッチ4、ノココッチ9、フーディン3、ユンゲラー2を評価する",
    "PLAYBOOK-CANDY-FIRST": "検索可能なフーディンより検索不能なアメを自然ドローで先に探す",
    "PLAYBOOK-HILDA": "トウコは進化ポケモンとエネルギーを取り、終盤に安全枠が1枚なら完成済み攻撃役の超だけを取る",
    "PLAYBOOK-T1-HILDA-SETUP": "1ターン目のトウコで次ターンのドロー装置とテレパス超を準備する",
    "PLAYBOOK-DAWN": "ヒカリはたね、1進化、2進化を取る",
    "PLAYBOOK-AIR-BALLOON": "自デッキのふうせんは採用せず、相手の公開カード認識だけは維持する",
    "PLAYBOOK-BASIC-PSYCHIC": "ハンドパワーには超エネルギーが必要でリッチは代用できない",
    "PLAYBOOK-HAND-THRESHOLD": "必要手札は相手残りHPを20で切り上げる",
    "PLAYBOOK-DISRUPTION-HOLD": "現在KO確定時だけ、クセロシキまたはアンフェアスタンプ後の復帰用に進化時ドローとノココッチを温存する",
    "PLAYBOOK-TURN-TWO-NON-KO": "自分2ターン目だけ、将来のKOへつなぐ非KOハンドパワーを暫定的に許可する",
    "PLAYBOOK-TELEPORT-ATTACK": "超付きバトル場ケーシィはノコッチを壁にできる時、テレポートアタックで超を失わず退避する",
    "PLAYBOOK-STOP-WHEN-KO": "KO可能後は不要なカードを使わない",
    "PLAYBOOK-BOARD-MINIMUM": "サイドを取り切らない限り攻撃後もベンチを残す",
    "PLAYBOOK-PROMOTE-COMPLETE": "完成済みフーディンを再構築より優先して前へ出す",
    "PLAYBOOK-T3-KADABRA": "2ターン目はノコッチの先取り検索よりユンゲラー2枚ドローを先に使い、失敗後も通常進化で3ターン目攻撃する",
    "PLAYBOOK-SACRED-ASH": "せいなるはいでポケモンを再利用する",
    "PLAYBOOK-LANAS-AID": "スイレンのお世話でルールなしポケモンと基本超を戻す",
    "PLAYBOOK-ENHANCED-HAMMER": "改造ハンマーは現在KO打点を割らず、対面のミスト・ロック闘採用証拠に応じて温存し、KO予定の相手バトル場を一般妨害対象から外す",
    "PLAYBOOK-XEROSIC-KEEP": "クセロシキ後は現在のバトル場が倒される前提で、次のフーディン攻撃・手札回復・後続を最大化する3枚を残す",
    "PLAYBOOK-BOSS": "ボスの指令は倒せるベンチを呼ぶ目的で使うが、初動はヒカリ・トウコによる展開を優先する",
    "PLAYBOOK-BATTLE-CAGE": "バトルコロシアムはダメカンを防ぎ通常ダメージは防がない",
    "PLAYBOOK-SHAYMIN-DAMAGE": "旧観測にシェイミがいる場合だけ、ルールなしベンチへの通常ダメージ防止を判定する",
    "PLAYBOOK-PSYDUCK": "旧観測にコダックがいる場合だけ、自身をきぜつさせる特性の停止を判定する",
    "PLAYBOOK-GENESECT": "旧観測にゲノセクトがいる場合だけ、どうぐ付きのACE SPEC停止を判定する",
    "PLAYBOOK-FEZANDIPITI": "前の相手番にきぜつがあればキチキギスexを評価する",
    "PLAYBOOK-FEZANDIPITI-DEPLOY": "前の相手番のきぜつ後、出さなければ現在攻撃または連続KOが切れる時だけ3枚ドローへつなぐ",
    "PLAYBOOK-FEZANDIPITI-TERMINAL": "クセロシキ対面の終盤だけ、現在KOと次番勝利を保ってキチキギスexを先置きする",
    "PLAYBOOK-SEARCH-INTENT": "検索理由と実際のカード・対象を一致させる",
    "PLAYBOOK-PETREL": "ラムダは同番の攻撃・KO・継続に直結するトレーナーズだけを検索する",
    "PLAYBOOK-NIGHT-STRETCHER": "夜のタンカはトラッシュの基本超を同番の攻撃または必要退避へ接続する",
    "PLAYBOOK-PRIZE-INFERENCE": "山札を見た時だけ固定リストから自分のサイドを確定する",
    "PLAYBOOK-NO-RANDOM": "未知局面でも無作為選択をしない",
    "PLAYBOOK-FIRST-SECOND": "先攻後攻を自分基準ターン数で独立して扱う",
    "PLAYBOOK-DECK-SAFETY": "山札10枚以下では残りサイド分を残し、ふうせんを自デッキ循環へ数えない",
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
