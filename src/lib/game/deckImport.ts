import jaCardRows from '../cards/cardsJa.generated.json';

const JA_NAME_BY_ID = new Map<number, string>();
for (const [id, card] of Object.entries(jaCardRows as Record<string, { name?: string }>)) {
  if (card?.name) {
    JA_NAME_BY_ID.set(Number(id), card.name);
  }
}

function normalizeLookupName(name: string): string {
  return name.normalize('NFC').replace(/\s+/g, ' ').trim().toLowerCase();
}

// Reverse lookup (Japanese card name -> ids) so a pasted deck list can use bare card names without a
// set code when the name is unambiguous in the catalog. Ambiguous names still require a set code.
const IDS_BY_JA_NAME = new Map<string, number[]>();
for (const [id, name] of JA_NAME_BY_ID) {
  const key = normalizeLookupName(name);
  const ids = IDS_BY_JA_NAME.get(key);
  if (ids) {
    if (!ids.includes(id)) {
      ids.push(id);
    }
  } else {
    IDS_BY_JA_NAME.set(key, [id]);
  }
}

export type ParsedDeck = {
  cards: string[];
  errors: string[];
};

export type DeckCardMetadata = {
  id: number;
  name: string;
  set: string;
  setNumber?: string | null;
  cardType?: number | null;
};

// 初期デッキ（アプリ起動時に読み込まれる既定デッキ）。フーディン＋キチキギスexの超タイプ。
// カードIDから set/番号 を引いて生成し、name+set が意図したIDへ一意解決すること、および
// 60枚でCABTエンジンの battle_start を通過する合法デッキであることを検証済み。
export const SAMPLE_DECK = `ポケモン: 22
3 フーディン MEG 56
4 ユンゲラー MEG 55
4 ケーシィ MEG 54
3 ノココッチ TEF 129
3 ノコッチ JTG 120
1 スピンロトム SCR 118
1 ゲノセクト SFA 40
1 シェイミ DRI 10
1 コダック ASC 39
1 キチキギスex SFA 38

トレーナーズ: 32
4 なかよしポフィン TEF 144
4 ポケパッド POR 81
4 ふしぎなアメ SVI 191
1 せいなるはい DRI 168
2 改造ハンマー TWM 148
3 ふうせん BLK 79
3 トウコ WHT 84
3 ヒカリ PFL 87
3 ボスの指令 PAL 172
1 スイレンのお世話 TWM 155
4 バトルコロシアム PFL 85

エネルギー: 6
1 リッチエネルギー SSP 191
3 テレパス【超】エネルギー POR 87
2 基本【超】エネルギー SVE 5`;

export function parseDeckList(text: string): ParsedDeck {
  const cards: string[] = [];
  const errors: string[] = [];
  const lines = text.split(/\r?\n/);

  lines.forEach((rawLine, idx) => {
    const line = rawLine.replace(/\s+#.*$/, '').trim();
    if (!line) {
      return;
    }
    if (/^[^\d:][^:]+:\s*\d+\s*$/.test(line)) {
      return;
    }

    const match = line.match(/^(\d+)\s+(.+)$/);
    const count = match ? Number(match[1]) : 1;
    const name = (match ? match[2] : line)?.trim() ?? '';
    if (!Number.isInteger(count) || count < 1 || count > 60) {
      errors.push(`${idx + 1}行目: 枚数が正しくありません。`);
      return;
    }
    const tokens = name.split(/\s+/);
    const hasCollectorNumber = /^\d+[a-z]?$/i.test(tokens.at(-1) ?? '');
    const setCode = hasCollectorNumber ? tokens.at(-2) : tokens.at(-1);
    if (name && /^[A-Z0-9-]{2,8}$/.test(setCode ?? '')) {
      // "<name> <SET> [collector]" — the engine resolves this by name + set code.
      const normalizedName = normalizeImportName(hasCollectorNumber ? tokens.slice(0, -1).join(' ') : name);
      for (let i = 0; i < count; i += 1) {
        cards.push(normalizedName);
      }
      return;
    }
    // No set code: resolve a bare (Japanese) card name against the catalog when it is unambiguous,
    // emitting the numeric card id (which the engine accepts directly). This lets players paste a
    // simple name list instead of the "<name> <SET> <number>" export format.
    const ids = name ? (IDS_BY_JA_NAME.get(normalizeLookupName(name)) ?? []) : [];
    if (ids.length === 1) {
      for (let i = 0; i < count; i += 1) {
        cards.push(String(ids[0]));
      }
      return;
    }
    if (ids.length > 1) {
      errors.push(`${idx + 1}行目: 「${name}」は複数のカードに一致します。セット略号を付けてください（例:「${name} MEG」）。`);
      return;
    }
    errors.push(`${idx + 1}行目: 「${name}」が見つかりません。カード名を確認するか、セット略号を付けてください（例:「ラルトス SIT」）。`);
  });

  if (cards.length === 0) {
    errors.push('デッキが空です。');
  }

  return { cards, errors };
}

export function formatCabtDeckList(rawDeck: string, cardRows: DeckCardMetadata[]): string {
  const rowsById = new Map(cardRows.map((row) => [row.id, row]));
  const entries = rawDeck
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      if (!/^\d+$/.test(line)) {
        throw new Error(`CABT deck line ${index + 1}: expected a numeric card ID.`);
      }
      const id = Number(line);
      const row = rowsById.get(id);
      if (!row) {
        throw new Error(`CABT deck line ${index + 1}: unknown card ID ${id}.`);
      }
      return row;
    });
  if (entries.length !== 60) {
    throw new Error(`CABT deck must contain exactly 60 cards, found ${entries.length}.`);
  }

  const groups = new Map<string, { row: DeckCardMetadata; count: number }>();
  for (const row of entries) {
    const key = `${row.id}`;
    const group = groups.get(key);
    if (group) {
      group.count += 1;
    } else {
      groups.set(key, { row, count: 1 });
    }
  }

  const sections = [
    { title: 'ポケモン', rows: [] as string[] },
    { title: 'トレーナーズ', rows: [] as string[] },
    { title: 'エネルギー', rows: [] as string[] },
  ];
  for (const group of groups.values()) {
    const displayName = JA_NAME_BY_ID.get(group.row.id) ?? group.row.name;
    const line = `${group.count} ${displayName} ${group.row.set}${group.row.setNumber ? ` ${group.row.setNumber}` : ''}`;
    sections[deckSectionIndex(group.row)].rows.push(line);
  }

  return sections
    .filter((section) => section.rows.length)
    .map((section) => [`${section.title}: ${sumCounts(section.rows)}`, ...section.rows].join('\n'))
    .join('\n\n');
}

function deckSectionIndex(row: DeckCardMetadata) {
  if (row.cardType === 0) {
    return 0;
  }
  if (row.cardType === 5 || row.cardType === 6) {
    return 2;
  }
  return 1;
}

function sumCounts(lines: string[]) {
  return lines.reduce((sum, line) => sum + Number(line.split(/\s+/, 1)[0]), 0);
}

function normalizeImportName(name: string): string {
  // NFD strips Latin accents (\u00e9\u2192e) for English deck exports; NFC recomposes so Japanese
  // voiced kana (e.g. \u30ac) are not left decomposed.
  const normalized = name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').normalize('NFC');
  return normalized.replace(/^Basic \{([A-Z])\} Energy\b/, (_match, type: string) => {
    const energyNames: Record<string, string> = {
      G: 'Grass',
      R: 'Fire',
      W: 'Water',
      L: 'Lightning',
      P: 'Psychic',
      F: 'Fighting',
      D: 'Darkness',
      M: 'Metal',
    };
    return `${energyNames[type] ?? type} Energy`;
  });
}
