"""Compare two Claude Code sessions that built the same feature: one with the AI team, one without.

It reads only: the session logs under ~/.claude/projects, and (for `blind`) the git history of the
project. It prints numbers, stage names and file names, never prompt or answer text.

  python tools/compare-sessions.py measure A B [--rate 3.0]
  python tools/compare-sessions.py blind --repo D:/Projects/market-review --base <commit> A_BRANCH B_BRANCH --out <dir>

A and B are each a worktree name as the app made it (`busy-mayer-e1f9b0`), a session id, a session
log file, or a log folder. A worktree or folder with several sessions counts them all together.

`measure` gives, for each side: your messages, wall-clock time, time spent waiting on you, working
time, model calls, tokens by kind, weighted tokens and an estimated cost, shell time, and a line per
stage or subagent. Weights: input 1, cache write 1.25 (5 minutes) or 2 (1 hour), cache read 0.1,
output 5. `--rate` is dollars per million weighted tokens (3.0 was measured for the opus model on
2026-10-06); the cost is an estimate, the weighted tokens are the measure.

`blind` writes the two branches' changes against the base as X.diff and Y.diff in random order, a
key.txt that says which is which (keep it closed until the verdicts are in), and judge-prompt.md
for a fresh session that has seen neither branch.

For a fair run, both sides get the same answers to the request's open decisions: write them in a file
before either session starts, paste them into both, and pass the file to `blind` with `--answers`. The
judge then scores fit to those answers and the scope they set before anything else. Without them it can
only judge how well each side built what it chose, and a side that asked fewer questions may have built
a smaller product.
"""
import argparse
import glob
import json
import os
import random
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

PROJECTS = os.path.join(os.path.expanduser('~'), '.claude', 'projects')
SHELLS = {'Bash', 'PowerShell'}


def resolve(spec):
    """Session log files for a worktree name, session id, file or folder."""
    if os.path.isfile(spec):
        return [spec]
    if os.path.isdir(spec):
        return sorted(glob.glob(os.path.join(spec, '*.jsonl')))
    hits = glob.glob(os.path.join(PROJECTS, '*', spec + '.jsonl'))
    if hits:
        return hits
    folders = [d for d in glob.glob(os.path.join(PROJECTS, '*'))
               if os.path.isdir(d) and os.path.basename(d).endswith('-worktrees-' + spec)]
    if len(folders) == 1:
        return sorted(glob.glob(os.path.join(folders[0], '*.jsonl')))
    sys.exit(f'{spec}: found {len(folders)} log folders; give a session id, file or folder instead')


def ts(record):
    t = record.get('timestamp')
    return datetime.fromisoformat(t.replace('Z', '+00:00')) if t else None


def records(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                pass


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(c, dict) and c.get('type') == 'tool_result' for c in content):
            return None
        # The app puts a reminder (worktree path and the like) before the typed text, as its own part.
        return '\n'.join(c.get('text', '') for c in content if isinstance(c, dict) and c.get('type') == 'text'
                         and not c.get('text', '').lstrip().startswith('<system-reminder>'))
    return ''


def is_prompt(record):
    """A message you typed: not a tool result, not a reminder or notice the harness added."""
    if record.get('type') != 'user' or record.get('isMeta') or record.get('isSidechain'):
        return False
    txt = text_of((record.get('message') or {}).get('content'))
    if not txt or not txt.strip():
        return False
    s = txt.lstrip()
    if s.startswith('<command-message>') or s.startswith('<command-name>'):
        return not re.search(r'<command-name>/?(compact|clear|context|cost|model|effort)</command-name>', s)
    return not (s.startswith('<') or s.startswith('Caveat:'))


def weights(u):
    cc = u.get('cache_creation') or {}
    w5, w1 = cc.get('ephemeral_5m_input_tokens'), cc.get('ephemeral_1h_input_tokens')
    if w5 is None and w1 is None:
        w5, w1 = u.get('cache_creation_input_tokens') or 0, 0
    k = {
        'input': u.get('input_tokens') or 0,
        'cache write': (w5 or 0) + (w1 or 0),
        'cache read': u.get('cache_read_input_tokens') or 0,
        'output': u.get('output_tokens') or 0,
        'thinking': (u.get('output_tokens_details') or {}).get('thinking_tokens') or 0,
    }
    k['weighted'] = k['input'] + 1.25 * (w5 or 0) + 2 * (w1 or 0) + 0.1 * k['cache read'] + 5 * k['output']
    return k


class Part:
    """One log: the main conversation or one subagent."""

    def __init__(self, path, label, until=None):
        self.label, self.calls, self.models = label, {}, defaultdict(float)
        self.first = self.last = None
        self.prompts, self.shell_s, self.shell_n, self.shell_cut = [], 0.0, 0, 0
        self.times, self.ask_s = [], 0.0
        started, asked = {}, {}
        for r in records(path):
            t = ts(r)
            if t and until and t > until:
                break
            if t:
                self.first = self.first or t
                self.last = t
            msg = r.get('message') or {}
            if r.get('type') == 'assistant':
                if t:
                    self.times.append(t)
                if msg.get('id') and msg.get('usage'):
                    self.calls[msg['id']] = (msg.get('model') or '?', msg['usage'])
                for c in msg.get('content') or []:
                    if isinstance(c, dict) and c.get('type') == 'tool_use' and c.get('name') in SHELLS and t:
                        started[c.get('id')] = t
                    if isinstance(c, dict) and c.get('type') == 'tool_use' and c.get('name') == 'AskUserQuestion' and t:
                        asked[c.get('id')] = t
            elif r.get('type') == 'user':
                if is_prompt(r) and t:
                    self.prompts.append(t)
                content = msg.get('content')
                if isinstance(content, list) and t:
                    for c in content:
                        if isinstance(c, dict) and c.get('type') == 'tool_result' and c.get('tool_use_id') in asked:
                            self.ask_s += (t - asked.pop(c['tool_use_id'])).total_seconds()
                        if isinstance(c, dict) and c.get('type') == 'tool_result' and c.get('tool_use_id') in started:
                            d = (t - started.pop(c['tool_use_id'])).total_seconds()
                            self.shell_s += d
                            self.shell_n += 1
                            self.shell_cut += d >= 599
                if self.label == 'subagent' and not self.prompts:
                    m = re.search(r'Stage:\s*([^\n]+)', text_of(content) or '')
                    if m:
                        self.label = 'stage ' + m.group(1).strip()
        self.tokens = defaultdict(float)
        for model, u in self.calls.values():
            k = weights(u)
            for name, v in k.items():
                self.tokens[name] += v
            self.models[model] += k['weighted']


def side(spec, until=None):
    parts = []
    for main in resolve(spec):
        parts.append(Part(main, 'main conversation', until))
        for sub in sorted(glob.glob(os.path.join(main[:-6], 'subagents', '*.jsonl'))):
            p = Part(sub, 'subagent', until)
            if p.label == 'subagent':
                meta = sub[:-6] + '.meta.json'
                try:
                    with open(meta, encoding='utf-8') as f:
                        p.label = 'subagent ' + (json.load(f).get('agentType') or '')
                except (OSError, ValueError):
                    pass
            if p.first:
                parts.append(p)
    return [p for p in parts if p.label == 'main conversation'] + sorted(
        (p for p in parts if p.label != 'main conversation'), key=lambda p: p.first or datetime.max.astimezone())


def summary(parts):
    mains = [p for p in parts if p.label == 'main conversation']
    prompts = sorted(t for p in mains for t in p.prompts)
    first = prompts[0] if prompts else min(p.first for p in parts if p.first)
    last = max(p.last for p in parts if p.last)
    events = sorted(t for p in parts for t in p.times)  # when the model last spoke, in any part
    waiting = 0.0
    for t in prompts[1:]:
        before = [e for e in events if e < t]
        if before:
            waiting += (t - before[-1]).total_seconds()
    waiting += sum(p.ask_s for p in parts)  # time a question box stood open
    tok = defaultdict(float)
    for p in parts:
        for k, v in p.tokens.items():
            tok[k] += v
    return {
        'your messages': len(prompts),
        'wall clock': (last - first).total_seconds(),
        'waiting on you': waiting,
        'working': (last - first).total_seconds() - waiting,
        'model calls': sum(len(p.calls) for p in parts),
        'subagents': len(parts) - len(mains),
        'shell time': sum(p.shell_s for p in parts),
        'shell commands': sum(p.shell_n for p in parts),
        'commands cut at 10 min': sum(p.shell_cut for p in parts),
        **{k: tok[k] for k in ('input', 'cache write', 'cache read', 'output', 'thinking', 'weighted')},
    }


def hm(s):
    s = int(s)
    return f'{s // 3600}h {s % 3600 // 60:02d}m' if s >= 3600 else f'{s // 60}m {s % 60:02d}s'


def measure(a, b, rate, until_a=None, until_b=None):
    sides = {'A': side(a, until_a), 'B': side(b, until_b)}
    sums = {k: summary(v) for k, v in sides.items()}
    print(f'A = {a}\nB = {b}\n')
    print('| Measure | A | B | B / A |\n|---|---:|---:|---:|')
    for key in sums['A']:
        va, vb = sums['A'][key], sums['B'][key]
        ratio = f'{vb / va:.2f}' if va else '-'
        if key in ('wall clock', 'waiting on you', 'working', 'shell time'):
            fa, fb = hm(va), hm(vb)
        elif isinstance(va, float):
            fa, fb = f'{va / 1e6:.2f} M', f'{vb / 1e6:.2f} M'
        else:
            fa, fb = str(va), str(vb)
        print(f'| {key} | {fa} | {fb} | {ratio} |')
    ca, cb = sums['A']['weighted'] * rate / 1e6, sums['B']['weighted'] * rate / 1e6
    print(f'| estimated cost at ${rate}/M weighted | ${ca:.2f} | ${cb:.2f} | {cb / ca if ca else 0:.2f} |')
    for name, parts in sides.items():
        total = sum(p.tokens['weighted'] for p in parts) or 1
        print(f'\n{name}, by part:\n\n| Part | Calls | Weighted | Share | Shell time |\n|---|---:|---:|---:|---:|')
        for p in parts:
            print(f"| {p.label} | {len(p.calls)} | {p.tokens['weighted'] / 1e6:.2f} M | "
                  f"{100 * p.tokens['weighted'] / total:.0f}% | {hm(p.shell_s)} |")
        models = defaultdict(float)
        for p in parts:
            for m, v in p.models.items():
                models[m] += v
        print('\nModels: ' + ', '.join(f'{m} {100 * v / total:.0f}%' for m, v in sorted(models.items(), key=lambda kv: -kv[1])))


JUDGE = """You are judging two changes made for the same request. You do not know who or what made either,
and nothing in your judgement should depend on guessing it.

The request is the GitHub issue below. The changes are `X.diff` and `Y.diff` in this folder, each against
the same base commit `{base}` of the repository at `{repo}`. Read the repository at that commit for
context; do not check out, build or change anything.

Judge each change on these, in this order, and give evidence (file and line) for each point:
0. Fit: does it build the product the owner asked for, at the scope the owner intended? Judge this against
   the owner's answers below when there are any; say plainly when a change builds less, or something else.
1. Does it do what the issue asks, all of it? List each point of "Wanted" and say met, partly or not.
2. Is it correct? Look for bugs and missed cases, including any the issue names.
3. Does it come with the tests the issue asks for, and would they fail without the change?
4. Does it keep to the project's rules in CLAUDE.md (budgets, wording, structure)?
5. Size and clarity: is anything changed that did not need to be?

Then pick one: X or Y is better, or they are equal. Fit (0) weighs most. Say why in three sentences or
fewer. No scores.

## The owner's answers to the open decisions

{answers}

## The issue

{issue}
"""


def blind(repo, base, a, b, out, issue, answers=None):
    os.makedirs(out, exist_ok=True)
    pair = [('A', a), ('B', b)]
    random.shuffle(pair)
    for letter, (name, branch) in zip('XY', pair):
        diff = subprocess.run(['git', '-C', repo, 'diff', f'{base}...{branch}'],
                              capture_output=True, text=True, encoding='utf-8', check=True).stdout
        with open(os.path.join(out, f'{letter}.diff'), 'w', encoding='utf-8') as f:
            f.write(diff)
        files = subprocess.run(['git', '-C', repo, 'diff', '--stat', f'{base}...{branch}'],
                               capture_output=True, text=True, encoding='utf-8', check=True).stdout
        print(f'{letter}.diff:\n{files}')
    with open(os.path.join(out, 'key.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(f'{x} = {name} ({branch})' for x, (name, branch) in zip('XY', pair)) + '\n')
    body = ''
    if issue:
        body = subprocess.run(['gh', 'issue', 'view', str(issue), '--json', 'title,body', '--jq', '"# " + .title + "\n\n" + .body'],
                              cwd=repo, capture_output=True, text=True, encoding='utf-8', check=True).stdout
    with open(os.path.join(out, 'judge-prompt.md'), 'w', encoding='utf-8') as f:
        given = 'None were given. Judge each change by how well it built what it chose.'
        if answers:
            with open(answers, encoding='utf-8') as g:
                given = g.read().strip()
        f.write(JUDGE.format(base=base, repo=repo, issue=body, answers=given))
    print(f'Wrote X.diff, Y.diff, key.txt and judge-prompt.md to {out}. Keep key.txt closed until the verdicts are in.')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('measure')
    m.add_argument('a')
    m.add_argument('b')
    m.add_argument('--rate', type=float, default=3.0)
    m.add_argument('--until-a', help='leave out what A did after this time (ISO, UTC), such as a later unrelated request')
    m.add_argument('--until-b', help='the same for B')
    bl = sub.add_parser('blind')
    bl.add_argument('--repo', required=True)
    bl.add_argument('--base', required=True)
    bl.add_argument('a_branch')
    bl.add_argument('b_branch')
    bl.add_argument('--out', required=True)
    bl.add_argument('--issue', type=int)
    bl.add_argument('--answers', help="a file with the owner's answers, given to both sides")
    args = ap.parse_args()
    if args.cmd == 'measure':
        cut = lambda v: datetime.fromisoformat(v.replace('Z', '+00:00')) if v else None
        measure(args.a, args.b, args.rate, cut(args.until_a), cut(args.until_b))
    else:
        blind(args.repo, args.base, args.a_branch, args.b_branch, args.out, args.issue, args.answers)


if __name__ == '__main__':
    main()
