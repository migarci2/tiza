"""Run an end-to-end check against a synthetic Tiza deployment (never a real workspace)."""
import argparse
from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo
import httpx

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://localhost:8080')
args = parser.parse_args()
client = httpx.Client(base_url=args.url, timeout=20)
assert client.get('/api/config').json()['demo_mode'], 'Smoke check requires synthetic demo mode'
verified = client.post('/api/auth/demo-code', json={'code': '246810'})
verified.raise_for_status()
login = verified.json()
client.headers['X-CSRF-Token'] = login['csrf_token']
local = datetime.fromisoformat(login['demo_now']).astimezone(ZoneInfo('Europe/Madrid'))
hours = (10 - local.hour) % 24
if hours:
    clock = client.post('/api/demo/clock/advance', json={'hours': hours})
    clock.raise_for_status()
    now = datetime.fromisoformat(clock.json()['demo_now'])
else:
    now = local
r = client.post('/api/cycles', json={'classroom_id': login['classroom_id'], 'objective': 'Add fractions with unlike denominators', 'closes_at': (now + timedelta(days=2)).isoformat(), 'budget_minutes': 12})
r.raise_for_status()
cycle = r.json()
client.post(f"/api/cycles/{cycle['id']}/concepts", json={'concept_ids': ['equivalence', 'add-different-denominator']}).raise_for_status()
queued = client.post(f"/api/cycles/{cycle['id']}/prepare", json={})
queued.raise_for_status()
for _ in range(60):
    response = client.get(f"/api/cycles/{cycle['id']}/draft")
    if response.status_code == 200:
        break
    time.sleep(1)
response.raise_for_status()
draft = response.json()
assert len(draft['assignments']) == 8
approval = client.post(f"/api/cycles/{cycle['id']}/approve", json={'version': draft['cycle']['version'], 'assignment_ids': [a['id'] for a in draft['assignments']], 'allow_reminder': True})
approval.raise_for_status()
published = client.post(f"/api/cycles/{cycle['id']}/publish", json={'version': draft['cycle']['version'], 'approval_id': approval.json()['id']})
published.raise_for_status()
assignment = draft['assignments'][0]
switched = client.post('/api/demo/switch', json={'user_id': assignment['learner']['id']}).json()
client.headers['X-CSRF-Token'] = switched['csrf_token']
practice = client.get('/api/assignments/' + assignment['id']).json()
item = practice['items'][0]
assert 'answer' not in item['exercise'] and 'explanation' not in item['exercise']
client.post(f"/api/assignments/{assignment['id']}/items/{item['id']}/hint", json={}).raise_for_status()
options = item['exercise'].get('options')
answer = options[0]['id'] if options and isinstance(options[0], dict) else options[0] if options else '1/2'
body = {'item_id': item['id'], 'response': answer, 'client_key': 'compose-smoke-attempt'}
first = client.post('/api/assignments/' + assignment['id'] + '/attempts', json=body)
first.raise_for_status()
replay = client.post('/api/assignments/' + assignment['id'] + '/attempts', json=body)
assert replay.json()['id'] == first.json()['id'] and first.json()['used_hint']
teacher = client.post('/api/demo/switch', json={'user_id': login['actor']['id']}).json()
client.headers['X-CSRF-Token'] = teacher['csrf_token']
brief = client.get(f"/api/cycles/{cycle['id']}/brief").json()
assert brief['completion']['not_started'] == 7
for _ in range(40):
    deliveries = client.get(f"/api/cycles/{cycle['id']}/deliveries").json()
    if all(d['state'] != 'queued' for d in deliveries):
        break
    time.sleep(1)
print({'cycle': cycle['id'], 'assignments': len(draft['assignments']), 'attempt_replayed_once': True,
       'participation': brief['completion'], 'deliveries': {s: sum(d['state'] == s for d in deliveries) for s in {d['state'] for d in deliveries}}})
assert all(d['state'] == 'provider_accepted' for d in deliveries), 'Inspect provider states; requires local Mailpit'
