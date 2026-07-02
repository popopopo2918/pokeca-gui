const knownLabels: Record<string, string> = {
  AlertPrompt: 'お知らせ',
  AttachEnergyPrompt: 'エネルギーをつける',
  ChooseAttackPrompt: 'ワザを選ぶ',
  ChooseCardsPrompt: 'カードを選ぶ',
  ChooseEnergyPrompt: 'エネルギーを選ぶ',
  ChoosePokemonPrompt: 'ポケモンを選ぶ',
  ChoosePrizePrompt: 'サイドを選ぶ',
  CoinFlipPrompt: 'コイントス',
  ConfirmCardsPrompt: 'カードを確認',
  ConfirmPrompt: '確認',
  DiscardEnergyPrompt: 'エネルギーをトラッシュ',
  MoveDamagePrompt: 'ダメカンを移動',
  MoveEnergyPrompt: 'エネルギーを移動',
  OrderCardsPrompt: 'カードを並べ替え',
  PutDamagePrompt: 'ダメカンをのせる',
  RemoveDamagePrompt: 'ダメカンを取り除く',
  SelectOptionPrompt: '選択',
  SelectPrompt: '選ぶ',
  ShowCardsPrompt: 'カード',
  ShowMulliganPrompt: 'マリガン',
  ShuffleDeckPrompt: '山札をシャッフル',
  WaitPrompt: '待機中',
  CANNOT_ATTACK_ON_FIRST_TURN: '先攻の最初の番はワザを使えません',
  CANNOT_RETREAT: 'にげられません',
  CHOOSE_ATTACK_TO_DISABLE: '使えなくするワザを選ぶ',
  CHOOSE_CARD_TO_DISCARD: 'トラッシュするカードを選ぶ',
  CHOOSE_CARD_TO_HAND: '手札に加えるカードを選ぶ',
  CHOOSE_CARD_TO_PUT_ONTO_BENCH: 'ベンチに出すポケモンを選ぶ',
  CHOOSE_ENERGIES_TO_DISCARD: 'トラッシュするエネルギーを選ぶ',
  CHOOSE_ENERGIES_TO_HAND: '手札に加えるエネルギーを選ぶ',
  CHOOSE_ENERGY_FROM_DECK: '山札からエネルギーを選ぶ',
  CHOOSE_ENERGY_FROM_DISCARD: 'トラッシュからエネルギーを選ぶ',
  CHOOSE_ENERGY_TO_DISCARD: 'トラッシュするエネルギーを選ぶ',
  CHOOSE_ENERGY_TO_PAY_RETREAT_COST: 'にげるためのエネルギーを選ぶ',
  CHOOSE_ENERGY_TYPE: 'エネルギーのタイプを選ぶ',
  CHOOSE_STARTING_POKEMONS: '最初のポケモンを選ぶ',
  GO_FIRST: '先攻にしますか？',
  LOG_PLAYER_ATTACHES_CARD: 'カードをつけた',
  LOG_PLAYER_DEALS_DAMAGE: 'ダメージを与えた',
  LOG_PLAYER_DISABLES_ATTACK: 'ワザを使えなくした',
  LOG_PLAYER_DRAWS_CARD: 'カードを引いた',
  LOG_PLAYER_ENDS_TURN: '番を終えた',
  LOG_PLAYER_CONCEDED: '投了した',
  LOG_GAME_FINISHED: '対戦終了',
  LOG_GAME_FINISHED_DRAW: '引き分けで終了',
  LOG_GAME_FINISHED_WINNER: '対戦終了',
  LOG_PLAYER_PLAYS_BASIC_POKEMON: 'たねポケモンを出した',
  LOG_PLAYER_RETREATS: 'にげた',
  LOG_PLAYER_USES_ATTACK: 'ワザを使った',
  LOG_PLAYER_USES_ABILITY: '特性を使った',
  LOG_TURN: '新しい番',
  RETREAT_ALREADY_USED: 'この番はもうにげました',
  SETUP_WHO_BEGINS_FLIP: 'コインで先攻を決める',
  WANT_TO_DISCARD_ENERGY: 'エネルギーをトラッシュしますか？',
};

export function labelFor(value: unknown): string {
  if (typeof value !== 'string') {
    return '';
  }
  if (knownLabels[value]) {
    return knownLabels[value];
  }
  if (/^[A-Z0-9_]+$/.test(value)) {
    return value
      .replace(/^LOG_/, '')
      .split('_')
      .filter(Boolean)
      .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
      .join(' ');
  }
  return value;
}
