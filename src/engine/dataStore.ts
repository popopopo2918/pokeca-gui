import fs from 'node:fs';
import path from 'node:path';
import { listFiles, downloadFile, uploadFiles, deleteFiles } from '@huggingface/hub';

// Optional free persistence: mirror the workspaces (agents) and game-logs to a Hugging Face
// Dataset repo so they survive Space restarts/rebuilds. Enabled when both env vars are set
// (HF_DATA_REPO like "user/pokeca-cabt-data", HF_DATA_TOKEN a write token via Space secret).
const REPO_NAME = (process.env.HF_DATA_REPO ?? '').trim();
const TOKEN = (process.env.HF_DATA_TOKEN ?? '').trim();
export const dataSyncEnabled = Boolean(REPO_NAME && TOKEN);
const repo = { type: 'dataset' as const, name: REPO_NAME };

export type SyncRoot = { repoPrefix: string; dir: string };

// Serialize all writes so concurrent uploads don't conflict on the dataset's git history.
let chain: Promise<unknown> = Promise.resolve();
function enqueue(fn: () => Promise<unknown>): void {
  chain = chain.then(fn, fn).catch((error) => {
    console.error('[dataStore] write failed:', error instanceof Error ? error.message : error);
  });
}

export async function pullAll(roots: SyncRoot[]): Promise<void> {
  if (!dataSyncEnabled) return;
  let count = 0;
  try {
    for await (const entry of listFiles({ repo, recursive: true, accessToken: TOKEN })) {
      if (entry.type !== 'file') continue;
      const root = roots.find((r) => entry.path === r.repoPrefix || entry.path.startsWith(`${r.repoPrefix}/`));
      if (!root) continue;
      const rel = entry.path.slice(root.repoPrefix.length).replace(/^\/+/, '');
      const dest = rel ? path.join(root.dir, rel) : root.dir;
      const response = await downloadFile({ repo, path: entry.path, accessToken: TOKEN });
      if (!response) continue;
      const buffer = Buffer.from(await response.arrayBuffer());
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.writeFileSync(dest, buffer);
      count += 1;
    }
    console.log(`[dataStore] pulled ${count} file(s) from ${REPO_NAME}`);
  } catch (error) {
    console.error('[dataStore] pull failed:', error instanceof Error ? error.message : error);
  }
}

export function pushFile(repoPath: string, content: Buffer | string): void {
  if (!dataSyncEnabled) return;
  enqueue(async () => {
    const bytes = typeof content === 'string' ? new TextEncoder().encode(content) : new Uint8Array(content);
    await uploadFiles({ repo, accessToken: TOKEN, files: [{ path: repoPath, content: new Blob([bytes]) }] });
  });
}

export function deleteRepoPaths(repoPaths: string[]): void {
  if (!dataSyncEnabled || repoPaths.length === 0) return;
  enqueue(async () => {
    await deleteFiles({ repo, accessToken: TOKEN, paths: repoPaths });
  });
}
