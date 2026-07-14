// リプレイJSON（対戦ログ）→ 人が読めるテキスト棋譜
// 使い方: npx tsx scripts/replay-to-text.ts <replay.json> <out.txt>
import fs from 'node:fs';
import { formatCabtLog } from '../src/lib/cabt/logFormat';
import { CabtLogType } from '../src/lib/cabt/types';

const [, , inPath, outPath] = process.argv;
if (!inPath || !outPath) {
  console.error('usage: npx tsx scripts/replay-to-text.ts <replay.json> <out.txt>');
  process.exit(1);
}
const replay = JSON.parse(fs.readFileSync(inPath, 'utf8'));
const frames: any[] = replay.visualize ?? [];
const info = replay.environment?.info ?? {};
const players: string[] = info.TeamNames ?? ['プレイヤー1', 'プレイヤー2'];
const title: string = replay.environment?.title ?? '';
const winner = frames.at(-1)?.current?.result;

const lines: string[] = [];
lines.push(`【CABT対戦ログ】${title}`);
lines.push(`対戦: ${players[0]} vs ${players[1]}`);
lines.push(`結果: ${winner === 0 || winner === 1 ? `${players[winner]} の勝ち` : winner === 3 ? '引き分け' : '不明'}`);
lines.push('');

let turn = 0;
for (const frame of frames) {
  for (const log of frame.logs ?? []) {
    if (Number(log.type) === CabtLogType.TURN_START) {
      turn += 1;
      lines.push('');
      lines.push(`━━━ ターン${turn} ━━━`);
    }
    const text = formatCabtLog(log);
    if (text) lines.push(text);
  }
}
lines.push('');
lines.push(`（全${turn}ターンを記録）`);
// Windowsのメモ帳でも文字化けしないよう BOM + CRLF で書き出す
fs.writeFileSync(outPath, '﻿' + lines.join('\r\n'), 'utf8');
console.log(`${outPath} (${lines.length} 行)`);
