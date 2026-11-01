"""Local proposal triage prototype. Python 3.11+, standard library only."""
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('TRIAGE_DATA_DIR', str(ROOT / 'data')))
FIELDS = ['licence', 'wsib', 'insurance', 'projects', 'price', 'weeks', 'panel', 'workmanship', 'lead', 'crew', 'safety', 'monitoring']
BOOLS = {'licence', 'wsib', 'lead', 'crew', 'safety', 'monitoring'}
DEFAULT = {'name': 'Commercial Solar Installation', 'evaluation_date': '2026-01-01', 'experience_start': '2021-01-01', 'budget': 260000, 'deadline': 16, 'insurance_min': 5000000, 'targets': {'projects': 15, 'price': 200000, 'weeks': 8, 'panel': 25, 'workmanship': 12}, 'weights': {'experience': 30, 'price': 25, 'timeline': 15, 'warranty': 15, 'team': 15}}

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def validate_config(c):
    if set(c) != set(DEFAULT):
        raise ValueError('Configuration keys must match the supplied template.')
    for name in ('evaluation_date', 'experience_start'):
        datetime.strptime(c[name], '%Y-%m-%d')
    if c['experience_start'] > c['evaluation_date']:
        raise ValueError('Experience window is reversed.')
    if not isinstance(c['name'], str) or not c['name'].strip():
        raise ValueError('Category name is required.')
    for k in ('budget', 'deadline', 'insurance_min'):
        positive(c[k])
    for group in ('targets', 'weights'):
        if set(c[group]) != set(DEFAULT[group]):
            raise ValueError('Unexpected configuration fields.')
        for v in c[group].values():
            positive(v, zero=(group == 'weights'))
    if abs(sum(c['weights'].values()) - 100) > 1e-9:
        raise ValueError('Weights must total 100.')

def positive(v, zero=False):
    import math
    if type(v) not in (int, float) or not math.isfinite(v) or v < 0 or (not zero and v == 0):
        raise ValueError('Expected a finite positive number (nonnegative where permitted).')

def validate_proposal(p):
    if not isinstance(p.get('id'), str) or not p['id'].strip() or len(p['id']) > 60:
        raise ValueError('Proposal ID is required (maximum 60 characters).')
    if set(p.get('facts', {})) != set(FIELDS):
        raise ValueError('Facts must contain exactly: ' + ', '.join(FIELDS))
    for k, v in p['facts'].items():
        if v is None:
            continue
        if k in BOOLS:
            if type(v) is not bool:
                raise ValueError(k + ' must be boolean or null.')
        else:
            positive(v, zero=k not in ('price', 'weeks'))
            if k == 'projects' and int(v) != v:
                raise ValueError('Project count must be an integer.')
    sources = p.get('sources', {})
    evidence = p.get('evidence', {})
    if not isinstance(sources, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in sources.items()):
        raise ValueError('Sources must map source IDs to text.')
    if not isinstance(evidence, dict) or set(evidence) - set(FIELDS):
        raise ValueError('Invalid evidence fields.')
    for k, entries in evidence.items():
        if not isinstance(entries, list):
            raise ValueError('Evidence must be a list of quotes.')
        for e in entries:
            if not isinstance(e, dict) or not isinstance(e.get('quote'), str) or not e['quote'] or e.get('source_id') not in sources or e['quote'] not in sources[e['source_id']]:
                raise ValueError('Evidence quote does not match its source: ' + k)
    if not isinstance(p.get('warnings', []), list) or not all(isinstance(x, str) for x in p.get('warnings', [])):
        raise ValueError('Warnings must be a list of strings.')
    canonical(p)

def evaluate(p, c, approved=False, failed_documentation=False):
    f = p['facts']
    base = {'proposal': p['id'], 'rank': None, 'status': 'flagged', 'score': None, 'reason': '', 'breakdown': {}}
    if not approved:
        base['reason'] = 'Awaiting human evidence review.'
        return base
    failures = []
    if failed_documentation:
        failures.append('Reviewer confirmed missing mandatory in-proposal documentation')
    for k in ('licence', 'wsib'):
        if f[k] is False:
            failures.append(k + ' requirement failed')
    for k, limit, direction in [('insurance', c['insurance_min'], 'min'), ('price', c['budget'], 'max'), ('weeks', c['deadline'], 'max')]:
        if f[k] is not None and ((direction == 'min' and f[k] < limit) or (direction == 'max' and f[k] > limit)):
            failures.append(k + ' constraint failed')
    if failures:
        base.update(status='ineligible', reason='; '.join(failures))
        return base
    missing = [k for k in FIELDS if f[k] is None]
    if missing:
        base['reason'] = 'Clarify missing facts: ' + ', '.join(missing)
        return base
    t, w = c['targets'], c['weights']
    b = {'experience': w['experience'] * min(f['projects']/t['projects'], 1), 'price': w['price'] * min(t['price']/f['price'], 1), 'timeline': w['timeline'] * min(t['weeks']/f['weeks'], 1), 'warranty': w['warranty']/2 * (min(f['panel']/t['panel'], 1)+min(f['workmanship']/t['workmanship'], 1)), 'team': w['team']/4 * sum(f[k] for k in ('lead', 'crew', 'safety', 'monitoring'))}
    base.update(status='ranked', score=round(sum(b.values()), 2), reason='Eligible; scored using approved facts and this run’s configuration.', breakdown=b, raw_score=sum(b.values()))
    return base

@contextmanager
def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / 'triage.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, created TEXT, actor TEXT, reason TEXT, payload TEXT, results TEXT, digest TEXT)')
    try:
        with db:
            yield db
    finally:
        db.close()

def make_run(payload):
    c = payload['config']
    validate_config(c)
    proposals = payload['proposals']
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= 100:
        raise ValueError('Provide 1–100 proposals.')
    if len({p['id'] for p in proposals}) != len(proposals):
        raise ValueError('Duplicate proposal IDs.')
    if not str(payload.get('actor', '')).strip() or not str(payload.get('reason', '')).strip():
        raise ValueError('Reviewer name and review rationale are required.')
    results = []
    for p in proposals:
        validate_proposal(p)
        reviewed = p.get('approved') is True
        if reviewed and not p.get('review_note', '').strip():
            raise ValueError('Every approved proposal needs a review note.')
        # Fixtures deliberately contain no source text; real imports need evidence for every supported fact.
        if reviewed and not payload.get('demo'):
            missing = [k for k, v in p['facts'].items() if v is not None and not p.get('evidence', {}).get(k)]
            if missing:
                raise ValueError('Missing evidence for ' + p['id'] + ': ' + ', '.join(missing))
        results.append(evaluate(p, c, reviewed, p.get('failed_documentation') is True))
    ranked = sorted([r for r in results if r['status'] == 'ranked'], key=lambda r: (-r['raw_score'], r['proposal']))
    for index, r in enumerate(ranked):
        r['rank'] = index + 1
        r['reason'] += ' Equal merit on exact score; ID determines display order.' if sum(x['raw_score'] == r['raw_score'] for x in ranked) > 1 else ''
    results = ranked + [r for r in results if r['status'] != 'ranked']
    encoded = canonical(payload)
    with connect() as db:
        cur = db.execute('INSERT INTO runs(created,actor,reason,payload,results,digest) VALUES(?,?,?,?,?,?)', (datetime.now(timezone.utc).isoformat(), payload['actor'], payload['reason'], encoded, canonical(results), hashlib.sha256(encoded.encode()).hexdigest()))
        return {'id': cur.lastrowid, 'results': results, 'demo': bool(payload.get('demo'))}

class Handler(BaseHTTPRequestHandler):
    def send(self, data, status=200, mime='application/json'):
        body = data.encode() if isinstance(data, str) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/':
            return self.send((ROOT / 'index.html').read_text(encoding='utf-8'), mime='text/html')
        if self.path == '/api/demo':
            return self.send(json.loads((ROOT / 'demo.json').read_text()))
        if self.path == '/api/runs':
            with connect() as db:
                rows = db.execute('SELECT id,created,actor,reason,digest FROM runs ORDER BY id DESC').fetchall()
            return self.send([dict(zip(['id','created','actor','reason','digest'], r)) for r in rows])
        if self.path.startswith('/api/runs/'):
            try:
                with connect() as db:
                    row = db.execute('SELECT payload,results FROM runs WHERE id=?', (int(self.path.rsplit('/', 1)[1]),)).fetchone()
                if row:
                    return self.send({'payload': json.loads(row[0]), 'results': json.loads(row[1])})
            except ValueError:
                pass
        self.send({'error': 'Not found'}, 404)

    def do_POST(self):
        if self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host', '')):
            return self.send({'error': 'Cross-origin request rejected'}, 403)
        if self.path not in ('/api/runs', '/api/ingest'):
            return self.send({'error': 'Not found'}, 404)
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 20_000_000:
                raise ValueError('Request must be between 1 byte and 20 MB.')
            payload = json.loads(self.rfile.read(size))
            if self.path == '/api/ingest':
                from ingestion import ingest
                self.send(ingest(payload))
            else:
                self.send(make_run(payload))
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            self.send({'error': str(exc)}, 400)

if __name__ == '__main__':
    print('Proposal triage: http://127.0.0.1:8765 — Ctrl+C to stop')
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
