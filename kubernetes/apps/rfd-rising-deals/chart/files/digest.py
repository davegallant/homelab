#!/usr/bin/env python3
"""Generate an RFD digest and optionally deliver it to Gotify."""
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

FEED = 'https://rfd.davegallant.ca/topics.json'
FORUM = 'https://forums.redflagdeals.com'


def rank(topics, now):
    result = []
    for item in topics:
        try:
            if item.get('forum_id') != 9:
                continue
            path, title = item['web_path'], item['title']
            age = (now - datetime.fromisoformat(item['post_time'].replace('Z', '+00:00'))).total_seconds() / 3600
            votes = item['Votes']['total_up']
            if isinstance(votes, bool) or not isinstance(votes, int):
                continue
            if not isinstance(title, str) or not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or not 0 < age <= 24 or votes < 0:
                continue
            result.append({'id': int(item['topic_id']), 'title': title, 'url': urljoin(FORUM, path),
                           'merchant': (item.get('Offer') or {}).get('dealer_name') or 'Unknown merchant',
                           'votes': votes, 'per_hour': votes / age})
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(result, key=lambda x: (-x['per_hour'], x['id']))


def validate_format(item, formatted):
    if formatted.get('id') != item['id']:
        raise ValueError('model returned incorrect topic id')
    title, price = formatted.get('title'), formatted.get('price')
    if not isinstance(title, str) or not title.strip() or len(title) > 200 or re.search(r'[<>\n\r]', title):
        raise ValueError('invalid model title')
    source_title = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', item['title'])
    source_words = set(re.findall(r'\w+', source_title.casefold()))
    if not set(re.findall(r'\w+', title.casefold())).issubset(source_words):
        raise ValueError('model title contains words absent from source')
    if not isinstance(price, str) or (price != 'Price not listed' and (not price or price not in item['title'])):
        raise ValueError('price not present in source title')
    return title, price


def safe_format(item, formatted):
    try:
        return validate_format(item, formatted)
    except (ValueError, TypeError, KeyError, AttributeError):
        # The feed remains authoritative when the model invents or changes data.
        title = re.sub(r'[\r\n\x00-\x1f]+', ' ', item['title']).strip()
        match = re.search(r'\$\s*\d[\d,]*(?:\.\d{1,2})?', title)
        if match:
            price = match.group(0)
            title = (title[:match.start()] + title[match.end():]).strip(' -–—')
            if title:
                return title, price
        return title, 'Price not listed'


def get_json(url, data=None, headers=None):
    request_headers = {'User-Agent': 'rfd-rising-deals/1.0'}
    request_headers.update(headers or {})
    request = Request(url, data=data, headers=request_headers, method='POST' if data else 'GET')
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def send_gotify(message, token):
    if not token:
        raise ValueError('Gotify token is missing')
    body = json.dumps({'title': 'RFD rising deals — top 5', 'message': message,
                       'priority': 5, 'extras': {'client::display': {'contentType': 'text/markdown'}}}).encode()
    request = Request('https://gotify.davegallant.ca/message', data=body,
                      headers={'Content-Type': 'application/json', 'X-Gotify-Key': token,
                               'User-Agent': 'rfd-rising-deals/1.0'}, method='POST')
    with urlopen(request, timeout=30) as response:
        if not 200 <= response.status < 300:
            raise ValueError(f'Gotify returned HTTP {response.status}')


def main():
    topics = get_json(FEED)
    if not isinstance(topics, list):
        raise ValueError('feed is not a list')
    candidates = rank(topics, datetime.now(timezone.utc))
    selected = []
    for item in candidates:
        try:
            request = Request(item['url'], headers={'User-Agent': 'curl/8.7.1'})
            with urlopen(request, timeout=10) as response:
                final = urlparse(response.geturl())
                body = response.read(65536)
                if (response.status != 200 or final.hostname != 'forums.redflagdeals.com'
                        or not re.search(rf'(?<!\d){item["id"]}(?!\d)', final.path)
                        or b'<title>' not in body.lower() or str(item['id']).encode() not in body):
                    continue
            selected.append(item)
        except Exception as exc:
            print(f"Skipping topic {item['id']}: {type(exc).__name__}", file=sys.stderr)
        if len(selected) == 5:
            break
    if len(selected) < 5:
        raise ValueError('fewer than five verified eligible topics')
    key = os.environ['LITELLM_API_KEY']
    endpoint = os.environ.get('LITELLM_BASE_URL', 'http://litellm.litellm.svc.cluster.local:4000/v1').rstrip('/')
    instruction = ('Return only a JSON array, one object per input, with id, title and price. '
                   'Use only words copied exactly from the source title, preserving numbers. '
                   'Shorten titles without inventing facts; remove merchant and price from titles. '
                   'Price must be copied exactly from the input title or be Price not listed. No Markdown.')
    request = {'model': 'gpt-6-luna', 'messages': [{'role': 'system', 'content': instruction},
               {'role': 'user', 'content': json.dumps(selected)}]}
    for attempt in range(2):
        response = get_json(endpoint + '/chat/completions', json.dumps(request).encode(),
                            {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        try:
            formatted = json.loads(response['choices'][0]['message']['content'])
            if not isinstance(formatted, list) or len(formatted) != len(selected):
                raise ValueError('model returned wrong number of items')
            validated = [safe_format(item, raw) for item, raw in zip(selected, formatted)]
            break
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            if attempt == 1:
                raise
            print('Model output failed validation; retrying once.', file=sys.stderr)
    lines = [datetime.now(ZoneInfo('America/Toronto')).strftime('%Y-%m-%d %H:%M') +
             ' — Top 5 by upvotes/hour (last 24h).']
    for number, (item, (title, price)) in enumerate(zip(selected, validated), 1):
        merchant = re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', item['merchant'])
        title = re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', title)
        lines.append(f"{number}. [{title}]({item['url']}) — **{price}**\n   {merchant} · {item['votes']} upvotes · {item['per_hour']:.2f}/hour")
    message = '\n'.join(lines)
    print(message)
    if os.environ.get('SEND_GOTIFY', 'false').lower() == 'true':
        send_gotify(message, os.environ['GOTIFY_TOKEN'])
        print('Gotify delivery succeeded.', file=sys.stderr)


if __name__ == '__main__':
    main()
