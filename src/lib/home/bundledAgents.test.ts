import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

type ManifestAgent = {
  id: string;
  name: string;
  path?: string;
  deckUrl?: string;
  fixedDeck?: boolean;
};

const root = process.cwd();
const manifest = JSON.parse(
  fs.readFileSync(path.join(root, 'public', 'agents', 'agents.json'), 'utf8'),
) as { agents: ManifestAgent[] };

describe('bundled alakazam-playbook agent', () => {
  it('registers the runtime and fixed sixty-card deck', () => {
    const agent = manifest.agents.find(
      (candidate) => candidate.id === 'alakazam-playbook',
    );
    expect(agent).toMatchObject({
      id: 'alakazam-playbook',
      name: 'フーディンAI（現行sample_a）',
      path: 'public/agents/alakazam-playbook/main.py',
      deckUrl: '/agents/alakazam-playbook/deck.csv',
      fixedDeck: true,
    });
    const deck = fs
      .readFileSync(
        path.join(
          root,
          'public',
          'agents',
          'alakazam-playbook',
          'deck.csv',
        ),
        'utf8',
      )
      .split(/\r?\n/u)
      .map((row) => row.trim())
      .filter(Boolean);
    expect(deck).toHaveLength(60);
  });

  it('imports main.py and returns its sixty-card deck without bundled cg binaries', () => {
    const mainPath = path.join(
      root,
      'public',
      'agents',
      'alakazam-playbook',
      'main.py',
    );
    const python = process.env.PYTHON || 'python';
    const program = [
      'import importlib.util, json, pathlib, sys',
      'path = pathlib.Path(sys.argv[1]).resolve()',
      'spec = importlib.util.spec_from_file_location("cabt_bundled_alakazam", path)',
      'module = importlib.util.module_from_spec(spec)',
      'spec.loader.exec_module(module)',
      'print(json.dumps({"deckSize": len(module.agent({"select": None}))}))',
    ].join('; ');
    const result = spawnSync(python, ['-B', '-c', program, mainPath], {
      encoding: 'utf8',
    });
    expect(result.status, result.stderr).toBe(0);
    expect(JSON.parse(result.stdout)).toEqual({ deckSize: 60 });
    expect(
      fs.existsSync(
        path.join(root, 'public', 'agents', 'alakazam-playbook', 'cg'),
      ),
    ).toBe(false);
  });
});

describe('bundled Konchu E agent', () => {
  it('keeps its runtime environment profile eligible for deployment', () => {
    const profilePath = 'public/agents/konchu-e/data/top200_environment_2026-07-18.json';
    const result = spawnSync('git', ['check-ignore', '--no-index', '--quiet', profilePath], {
      cwd: root,
      encoding: 'utf8',
    });

    expect(result.status).toBe(1);
  });

  it('coexists with sample_a and registers a fixed sixty-card deck', () => {
    const konchuE = manifest.agents.find((agent) => agent.id === 'konchu-e');
    const sampleA = manifest.agents.find(
      (agent) => agent.id === 'alakazam-playbook',
    );

    expect(konchuE).toMatchObject({
      id: 'konchu-e',
      name: '昆虫E',
      path: 'public/agents/konchu-e/main.py',
      deckUrl: '/agents/konchu-e/deck.csv',
      fixedDeck: true,
    });
    expect(sampleA).toBeDefined();
  });

  it('imports main.py and returns its sixty-card deck without bundled cg binaries', () => {
    const mainPath = path.join(
      root,
      'public',
      'agents',
      'konchu-e',
      'main.py',
    );
    const python = process.env.PYTHON || 'python';
    const program = [
      'import importlib.util, json, pathlib, sys',
      'path = pathlib.Path(sys.argv[1]).resolve()',
      'spec = importlib.util.spec_from_file_location("cabt_bundled_konchu_e", path)',
      'module = importlib.util.module_from_spec(spec)',
      'spec.loader.exec_module(module)',
      'print(json.dumps({"deckSize": len(module.agent({"select": None}))}))',
    ].join('; ');
    const result = spawnSync(python, ['-B', '-c', program, mainPath], {
      encoding: 'utf8',
    });
    expect(result.status, result.stderr).toBe(0);
    expect(JSON.parse(result.stdout)).toEqual({ deckSize: 60 });
    expect(
      fs.existsSync(path.join(root, 'public', 'agents', 'konchu-e', 'cg')),
    ).toBe(false);
  });

  it('ignores display-only ability logs when observing the opponent', () => {
    const agentRoot = path.join(root, 'public', 'agents', 'konchu-e');
    const python = process.env.PYTHON || 'python';
    const program = [
      'import pathlib, sys, types',
      'root = pathlib.Path(sys.argv[1]).resolve()',
      'sys.path.insert(0, str(root))',
      'from memory import AgentMemory',
      'view = types.SimpleNamespace(current={"turn": 4}, own_index=1, raw={"logs": [{"type": "ability", "playerIndex": 0}]}, opponent_public_card_ids=set(), opponent_discard_ids=set(), opponent_public_ace_spec_ids=set())',
      'memory = AgentMemory()',
      'memory.observe_public_opponent(view)',
      'print("ok")',
    ].join('; ');
    const result = spawnSync(python, ['-B', '-c', program, agentRoot], {
      encoding: 'utf8',
    });

    expect(result.status, result.stderr).toBe(0);
    expect(result.stdout.trim()).toBe('ok');
  });

  it('keeps the fetched deck.csv aligned with the Python setup deck', () => {
    const deckRows = fs
      .readFileSync(
        path.join(root, 'public', 'agents', 'konchu-e', 'deck.csv'),
        'utf8',
      )
      .split(/\r?\n/u)
      .map((row) => row.trim())
      .filter(Boolean);
    expect(deckRows).toHaveLength(60);
    for (const row of deckRows) {
      expect(row).toMatch(/^\d+$/u);
    }
    const fetchedDeck = deckRows.map(Number);

    const mainPath = path.join(
      root,
      'public',
      'agents',
      'konchu-e',
      'main.py',
    );
    const python = process.env.PYTHON || 'python';
    const program = [
      'import importlib.util, json, pathlib, sys',
      'path = pathlib.Path(sys.argv[1]).resolve()',
      'spec = importlib.util.spec_from_file_location("cabt_bundled_konchu_e_deck", path)',
      'module = importlib.util.module_from_spec(spec)',
      'spec.loader.exec_module(module)',
      'print(json.dumps({"deck": module.agent({"select": None})}))',
    ].join('; ');
    const result = spawnSync(python, ['-B', '-c', program, mainPath], {
      encoding: 'utf8',
    });
    expect(result.status, result.stderr).toBe(0);
    const pythonDeck = JSON.parse(result.stdout) as { deck: number[] };
    expect(pythonDeck.deck).toHaveLength(60);
    expect(pythonDeck.deck).toEqual(fetchedDeck);
  });
});

describe('bundled Omatsuri Ondo agent', () => {
  it('registers the canonical runtime and fixed sixty-card deck', () => {
    const agent = manifest.agents.find((candidate) => candidate.id === 'omatsuri-ondo');
    expect(agent).toMatchObject({
      id: 'omatsuri-ondo',
      name: 'おまつりおんどAI（カミッチュ）',
      path: 'public/agents/omatsuri-ondo/main.py',
      deckUrl: '/agents/omatsuri-ondo/deck.csv',
      fixedDeck: true,
    });

    const deck = fs
      .readFileSync(path.join(root, 'public', 'agents', 'omatsuri-ondo', 'deck.csv'), 'utf8')
      .split(/\r?\n/u)
      .map((row) => row.trim())
      .filter(Boolean);
    expect(deck).toHaveLength(60);
    expect(deck.every((row) => /^\d+$/u.test(row))).toBe(true);
  });

  it('imports in isolation without native binaries or development-only modules', () => {
    const agentRoot = path.join(root, 'public', 'agents', 'omatsuri-ondo');
    const mainPath = path.join(agentRoot, 'main.py');
    const python = process.env.PYTHON || 'python';
    const program = [
      'import importlib.util, json, pathlib, sys',
      'path = pathlib.Path(sys.argv[1]).resolve()',
      'spec = importlib.util.spec_from_file_location("cabt_bundled_omatsuri", path)',
      'module = importlib.util.module_from_spec(spec)',
      'spec.loader.exec_module(module)',
      'print(json.dumps({"deckSize": len(module.agent({"select": None}))}))',
    ].join('; ');
    const result = spawnSync(python, ['-B', '-c', program, mainPath], {
      cwd: agentRoot,
      encoding: 'utf8',
    });

    expect(result.status, result.stderr).toBe(0);
    expect(JSON.parse(result.stdout)).toEqual({ deckSize: 60 });
    expect(fs.existsSync(path.join(agentRoot, 'cg'))).toBe(false);
    expect(fs.existsSync(path.join(agentRoot, 'src', 'agent', 'omatsuri_ondo', 'tests'))).toBe(false);
    expect(fs.existsSync(path.join(agentRoot, 'src', 'agent', 'omatsuri_ondo', 'rules'))).toBe(false);
  });
});
