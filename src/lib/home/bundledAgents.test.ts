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
});
