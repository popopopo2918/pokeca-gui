import rawCardRows from '../lib/cabt/cardData.generated.json';
import jaCardRows from '../lib/cards/cardsJa.generated.json';

// 公式サイト（pokemon-card.com）のデッキコードから、CABTで使える貼り付け形式の
// デッキリストを作る。印刷用ページ（print.html）の表〔カード名/枚数/…〕を読み取り、
// 日本語カード名でCABTのカードプールへ対応付ける。CABTに存在しないカードは
// warnings として返し、リストからは除外する。

type CardRow = { id: number; name: string; set: string; setNumber: string };

const CARD_ROWS = rawCardRows as CardRow[];
const ROW_BY_ID = new Map<number, CardRow>();
for (const row of CARD_ROWS) {
  if (!ROW_BY_ID.has(row.id)) {
    ROW_BY_ID.set(row.id, row);
  }
}

const IDS_BY_JA_NAME = new Map<string, number[]>();
for (const [id, card] of Object.entries(jaCardRows as Record<string, { name?: string }>)) {
  const name = normalizeName(card?.name ?? '');
  if (!name || !ROW_BY_ID.has(Number(id))) {
    continue;
  }
  const ids = IDS_BY_JA_NAME.get(name) ?? [];
  ids.push(Number(id));
  IDS_BY_JA_NAME.set(name, ids);
}

function normalizeName(name: string): string {
  const normalized = name.normalize('NFKC').replace(/\s+/g, '').trim();
  // 公式表記「基本超エネルギー」→ CABT日本語データ「基本【超】エネルギー」
  const energy = normalized.match(/^基本(草|炎|水|雷|超|闘|悪|鋼)エネルギー$/);
  return energy ? `基本【${energy[1]}】エネルギー` : normalized;
}

export type OfficialDeckResult =
  | { ok: true; text: string; total: number; warnings: string[] }
  | { ok: false; error: string };

export async function importOfficialDeckCode(code: string): Promise<OfficialDeckResult> {
  const trimmed = code.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9-]{2,60}$/.test(trimmed)) {
    return { ok: false, error: 'デッキコードの形式が正しくありません。' };
  }
  let html: string;
  try {
    const response = await fetch(
      `https://www.pokemon-card.com/deck/print.html/deckID/${encodeURIComponent(trimmed)}/`,
      { headers: { 'User-Agent': 'cabt-viewer (local playtest tool)' }, redirect: 'follow' },
    );
    if (!response.ok) {
      return { ok: false, error: `公式サイトからデッキを取得できませんでした（HTTP ${response.status}）。` };
    }
    html = await response.text();
  } catch (error) {
    return { ok: false, error: `公式サイトへ接続できませんでした: ${error instanceof Error ? error.message : String(error)}` };
  }

  const entries = parsePrintPage(html);
  if (!entries.length) {
    return { ok: false, error: 'デッキコードからカードを読み取れませんでした。コードが有効か確認してください。' };
  }

  const lines: string[] = [];
  const warnings: string[] = [];
  let total = 0;
  for (const entry of entries) {
    const ids = IDS_BY_JA_NAME.get(normalizeName(entry.name));
    const row = ids?.length ? ROW_BY_ID.get(ids[0]) : undefined;
    if (!row) {
      warnings.push(`「${entry.name}」×${entry.count} はCABTのカードプールに無いため除外しました。`);
      continue;
    }
    const jaName = (jaCardRows as Record<string, { name?: string }>)[String(row.id)]?.name ?? row.name;
    lines.push(`${entry.count} ${jaName} ${row.set} ${row.setNumber}`);
    total += entry.count;
  }
  if (!lines.length) {
    return { ok: false, error: 'このデッキのカードはCABTのカードプールに1枚も見つかりませんでした。' };
  }
  if (total !== 60) {
    warnings.push(`合計 ${total} 枚です（60枚になるよう調整してください）。`);
  }
  return { ok: true, text: lines.join('\n'), total, warnings };
}

/** print.html の表から〔カード名, 枚数〕を取り出す。カード行は
 * 「名前 / 枚数 / エキスパンション / コレクションNo.」の4セル構成。 */
function parsePrintPage(html: string): Array<{ name: string; count: number }> {
  const entries: Array<{ name: string; count: number }> = [];
  for (const rowMatch of html.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)) {
    const cells = [...rowMatch[1].matchAll(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/g)]
      .map((cell) => cell[1]
        .replace(/<[^>]+>/g, ' ')
        .replace(/&nbsp;/g, ' ')
        .replace(/&amp;/g, '&')
        .replace(/\s+/g, ' ')
        .trim());
    if (cells.length < 2) {
      continue;
    }
    const name = cells[0];
    const count = Number(cells[1]);
    if (!name || !Number.isInteger(count) || count < 1 || count > 60) {
      continue;
    }
    if (/^(小計|合計)$/.test(name)) {
      continue; // 集計行はカードではない
    }
    entries.push({ name, count });
  }
  return entries;
}
