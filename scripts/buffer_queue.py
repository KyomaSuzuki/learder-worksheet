"""Schedule approved worksheet posts. No third-party dependencies or API retries."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import unicodedata
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'post/buffer_state.json'
UTC = dt.timezone.utc

def drafts():
    source = (ROOT / 'post/x_posts.md').read_text()
    sections = re.split(r'^## \d+\. ', source, flags=re.M)[1:]
    topics = []
    for section in sections:
        section = section.split('## 共通投稿')[0]
        blocks = re.findall(r'\*\*案([A-E])\*\*[^\n]*\n\s*```\n(.*?)\n```', section, re.S)
        if len(blocks) != 5:
            raise RuntimeError('Each topic must have five drafts')
        topics.append(dict(blocks))
    if len(topics) != 24:
        raise RuntimeError('Expected 24 topics')
    result = []
    for variant in 'ABCDE':
        for i, topic in enumerate(topics, 1):
            text = topic[variant].replace('[サイトURL]', 'https://learder-worksheet.hiyokingofheart.workers.dev/').strip()
            # Conservative count: emoji sequences count separately; never underestimate.
            plain = re.sub(r'https?://\S+', 'x' * 23, unicodedata.normalize('NFC', text))
            weight = sum(1 if ord(c) <= 0x10ff or 0x2000 <= ord(c) <= 0x200d or 0x2010 <= ord(c) <= 0x201f or 0x2032 <= ord(c) <= 0x2037 else 2 for c in plain)
            if weight > 280 or '[サイトURL]' in text:
                raise RuntimeError(f'Draft {i}{variant} invalid: {weight}')
            result.append({'key': f'{i:02d}{variant}', 'text': text})
    if len({p['text'] for p in result}) != len(result):
        raise RuntimeError('Duplicate draft text')
    return result

def api(query, variables=None):
    token = os.environ.get('BUFFER_API_KEY')
    if not token:
        raise RuntimeError('BUFFER_API_KEY is missing')
    req = urllib.request.Request('https://api.buffer.com',
        data=json.dumps({'query': query, 'variables': variables or {}}).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=40) as response:
        data = json.load(response)
    if data.get('errors'):
        raise RuntimeError('Buffer GraphQL: ' + json.dumps(data['errors']))
    return data['data']

def channel():
    orgs = api('{ account { organizations { id } } }')['account']['organizations']
    channels = []
    for org in orgs:
        channels += api('query($input: ChannelsInput!) { channels(input: $input) { id name service organizationId isDisconnected isLocked isQueuePaused } }',
                        {'input': {'organizationId': org['id']}})['channels']
    channels = [c for c in channels if c['service'] == 'twitter']
    selected = os.environ.get('BUFFER_CHANNEL_ID')
    if selected:
        channels = [c for c in channels if c['id'] == selected]
    if len(channels) != 1:
        raise RuntimeError('Expected exactly one X channel. Set BUFFER_CHANNEL_ID if there are multiple.')
    c = channels[0]
    if any(c[k] for k in ('isDisconnected', 'isLocked', 'isQueuePaused')):
        raise RuntimeError('X channel is disconnected, locked, or paused')
    print('Connected X channel:', c['name'])
    return c

def all_posts(c):
    posts, cursor = [], None
    for _ in range(30):
        data = api('''query($input: PostsInput!, $after: String) {
          posts(input: $input, first: 100, after: $after) {
            edges { node { id text dueAt status } }
            pageInfo { hasNextPage endCursor }
          }
        }''', {'input': {'organizationId': c['organizationId'], 'filter': {'channelIds': [c['id']]}}, 'after': cursor})['posts']
        posts.extend(e['node'] for e in data['edges'])
        if not data['pageInfo']['hasNextPage']:
            return posts
        cursor = data['pageInfo']['endCursor']
    raise RuntimeError('Too many posts; stopped without scheduling')

def checkpoint(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    # Persist intent BEFORE requesting a post. An uncertain result must never auto-retry.
    subprocess.run(['git', 'add', str(STATE)], cwd=ROOT, check=True)
    if subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=ROOT).returncode == 0:
        return
    subprocess.run(['git', 'commit', '-m', 'Record Buffer scheduling progress [skip ci]'], cwd=ROOT, check=True)
    subprocess.run(['git', 'push', 'origin', 'HEAD:main'], cwd=ROOT, check=True)

def due_slots(now):
    # 09:00 JST is 00:00 UTC. Leave at least 15 minutes to deliver the reservation.
    start = (now + dt.timedelta(minutes=15)).date()
    first = dt.datetime.combine(start, dt.time(), UTC)
    if first <= now + dt.timedelta(minutes=15):
        first += dt.timedelta(days=1)
    return [first + dt.timedelta(days=n) for n in range(7)]

def timestamp(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None

def run(publish=False, now=None):
    queue = drafts()
    now = now or dt.datetime.now(UTC)
    state = json.loads(STATE.read_text())
    c = channel()
    if state.get('channel_id') and state['channel_id'] != c['id']:
        raise RuntimeError('Channel changed; refusing to send to a different account')
    state['channel_id'] = c['id']
    posts = all_posts(c)
    by_id = {p['id']: p for p in posts}
    by_text = {p['text']: p for p in posts}
    for key, receipt in state['receipts'].items():
        p = by_id.get(receipt.get('id')) or by_text.get(receipt['text'])
        if receipt['status'] == 'pending':
            if not p:
                raise RuntimeError(f'Uncertain previous request for {key}; inspect Buffer before retrying')
            receipt.update(status='scheduled', id=p['id'])
        if p and p['status'] == 'error':
            raise RuntimeError(f'Buffer publishing failed for {key}; inspect Buffer')
    if publish:
        checkpoint(state)
    scheduled = [p for p in posts if p.get('dueAt') and timestamp(p['dueAt']) > now]
    if len(scheduled) >= 10:
        print('Queue already full; no changes')
        return
    occupied = {timestamp(p['dueAt']).date() for p in scheduled}
    available = [q for q in queue if q['key'] not in state['receipts'] and q['text'] not in by_text]
    count = 0
    for due in due_slots(now):
        if due.date() in occupied or len(scheduled) + count >= 10:
            continue
        if not available:
            print('All 120 drafts used; no repeats will be scheduled')
            break
        draft = available.pop(0)
        due_at = due.isoformat().replace('+00:00', 'Z')
        print(('Schedule' if publish else 'Preview'), draft['key'], due_at, draft['text'].splitlines()[0])
        if publish:
            receipt = dict(text=draft['text'], dueAt=due_at, status='pending')
            state['receipts'][draft['key']] = receipt
            checkpoint(state)
            result = api('''mutation($input: CreatePostInput!) {
              createPost(input: $input) {
                __typename
                ... on PostActionSuccess { post { id dueAt status } }
                ... on MutationError { message }
              }
            }''', {'input': {'channelId': c['id'], 'text': draft['text'],
                            'schedulingType': 'automatic', 'mode': 'customScheduled', 'dueAt': due_at}})['createPost']
            if result['__typename'] != 'PostActionSuccess':
                raise RuntimeError('Buffer rejected reservation: ' + result.get('message', result['__typename']))
            receipt.update(status='scheduled', id=result['post']['id'])
            checkpoint(state)
        count += 1
    print('Reservations added:' if publish else 'Reservations planned:', count)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--validate', action='store_true')
    args = parser.parse_args()
    if args.validate:
        print(f'{len(drafts())} drafts validated')
    else:
        run(args.publish)
