const CDP_PORT = Number(process.env.CDP_PORT ?? 9223);
const BASE_URL = process.env.BASE_URL ?? 'http://127.0.0.1:8196/';
const LIMIT_MS = 300;

const targets = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json`)).json();
const target = targets.find((item) => item.type === 'page');
if (!target?.webSocketDebuggerUrl) {
  throw new Error(`Chrome CDP ${CDP_PORT} にページがありません。`);
}

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.onopen = resolve;
  socket.onerror = reject;
});
let nextId = 0;
const pending = new Map();
socket.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    pending.get(message.id)(message);
    pending.delete(message.id);
  }
};

function send(method, params = {}) {
  return new Promise((resolve) => {
    const id = ++nextId;
    pending.set(id, resolve);
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const response = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (response.result?.exceptionDetails) {
    throw new Error(response.result.exceptionDetails.text ?? 'CDP evaluation failed');
  }
  return response.result?.result?.value;
}

async function waitFor(predicate, timeoutMs = 10_000, intervalMs = 20) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const value = await evaluate(predicate);
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(`画面待機がタイムアウトしました: ${predicate}`);
}

async function clickButton(text) {
  return evaluate(`(()=>{const button=[...document.querySelectorAll('button')].find((item)=>item.textContent.trim()===${JSON.stringify(text)}&&!item.disabled);if(!button)return false;button.click();return true})()`);
}

await send('Page.enable');
await send('Runtime.enable');

let measured;
let usedCard = '';
for (let attempt = 0; attempt < 6 && measured === undefined; attempt += 1) {
  await send('Page.navigate', { url: BASE_URL });
  await waitFor(`document.body?.innerText.includes('対戦開始')`);
  await evaluate(`(()=>{for(const tabs of document.querySelectorAll('[role="tablist"]')){const button=[...tabs.querySelectorAll('button')].find(x=>x.textContent.trim()==='自分'&&!x.disabled);button?.click()}return true})()`);
  await clickButton('対戦開始');
  await waitFor(`document.body?.innerText.includes('先攻・後攻を選ぶ')`);
  await clickButton('後攻');

  for (let setupStep = 0; setupStep < 30; setupStep += 1) {
    const ready = await evaluate(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='ターンエンド');return !!b&&!b.disabled&&!document.querySelector('.prompt-dock')})()`);
    if (ready) break;
    const numericChoice = await evaluate(`(()=>{const buttons=[...document.querySelectorAll('.prompt-dock button')].filter(x=>/^\\d+枚$/.test(x.textContent.trim())&&!x.disabled);const button=buttons.find(x=>x.textContent.trim()==='0枚')??buttons[0];if(!button)return false;button.click();return true})()`);
    if (numericChoice) {
      await new Promise((resolve) => setTimeout(resolve, 80));
      continue;
    }
    const selectable = await evaluate(`(()=>{const card=document.querySelector('.prompt-dock .selectable-card');if(!card)return false;card.click();return true})()`);
    if (selectable) {
      await new Promise((resolve) => setTimeout(resolve, 30));
      await clickButton('確定');
    } else if (!(await clickButton('確定'))) {
      await clickButton('スキップ');
    }
    await new Promise((resolve) => setTimeout(resolve, 80));
  }

  try {
    await waitFor(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='ターンエンド');return !!b&&!b.disabled&&!document.querySelector('.prompt-dock')})()`, 20_000);
  } catch {
    continue;
  }

  const selected = await evaluate(`(()=>{const names=['Buddy-Buddy Poffin','Poké Pad','Hilda'];for(const name of names){const card=[...document.querySelectorAll('button[data-testid^="hand-card-"]:not(:disabled)')].find(x=>x.getAttribute('title')===name);if(!card)continue;card.click();window.__cabtLatencyCard=name;return name;}return ''})()`);
  if (!selected) continue;
  usedCard = selected;
  try {
    await waitFor(`document.querySelector('.game-board-plane.can-play-on-board')`, 1_000, 10);
  } catch {
    continue;
  }
  await evaluate(`(()=>{const board=document.querySelector('.game-board-plane.can-play-on-board');if(!board)return false;window.__cabtLatencyStart=performance.now();board.click();return true})()`);
  try {
    await waitFor(`document.querySelector('.prompt-dock .selectable-card')`, 5_000, 10);
  } catch {
    const diagnostic = await evaluate(`(()=>({
      card:window.__cabtLatencyCard,
      prompt:document.querySelector('.prompt-dock')?.textContent.trim().slice(0,500)??'',
      overlays:[...document.querySelectorAll('[class*="prompt"],[class*="overlay"]')].map(x=>({class:x.className,text:x.textContent.trim().slice(0,160)})).filter(x=>x.text).slice(0,20),
      error:document.body.innerText.split('\\n').filter(x=>x.includes('エラー')||x.includes('失敗')).slice(-10)
    }))()`);
    socket.close();
    throw new Error(`カード使用後の選択画面が見つかりません: ${JSON.stringify(diagnostic)}`);
  }
  measured = await evaluate(`performance.now()-window.__cabtLatencyStart`);
}

if (measured === undefined) {
  const diagnostic = await evaluate(`(()=>({
    hand:[...document.querySelectorAll('[data-testid^="hand-card-"]')].map(x=>({testId:x.getAttribute('data-testid'),title:x.getAttribute('title'),text:x.textContent.trim().slice(0,80)})),
    prompt:document.querySelector('.prompt-dock')?.textContent.trim().slice(0,300)??'',
    buttons:[...document.querySelectorAll('button')].filter(x=>!x.disabled).map(x=>x.textContent.trim()).filter(Boolean).slice(-30)
  }))()`);
  socket.close();
  throw new Error(`選択プロンプトを開くカードを6試合で引けませんでした: ${JSON.stringify(diagnostic)}`);
}
if (measured > LIMIT_MS) {
  socket.close();
  throw new Error(`カード使用後の入力待ちが長すぎます: ${measured.toFixed(1)}ms`);
}
socket.close();
process.stdout.write(`${JSON.stringify({ card: usedCard, cardUseToPromptMs: Math.round(measured), limitMs: LIMIT_MS })}\n`);
