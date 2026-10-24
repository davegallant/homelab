#!/usr/bin/env python3
"""Verify Service requests and their translated backend Hubble flows."""
import argparse
import json
import random
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--context', required=True)
parser.add_argument('--namespace', default='cilium-canary-1')
parser.add_argument('--node', default='k8s-w-2')
args = parser.parse_args()
base = ['kubectl', '--context', args.context]


def run(*command):
    return subprocess.check_output(base + list(command), text=True, timeout=20)


pods = json.loads(run('-n', args.namespace, 'get', 'pods', '-o', 'json'))['items']
clients = [p for p in pods if p['metadata']['labels'].get('kind') == 'client']
backends = {p['status']['podIP'] for p in pods
            if p['metadata']['labels'].get('name') == 'echo-same-node'}
service = json.loads(run('-n', args.namespace, 'get', 'service', 'echo-same-node', '-o', 'json'))
address = service['spec']['clusterIP']
agent = json.loads(run('-n', 'cilium-system', 'get', 'pods', '-l', 'k8s-app=cilium',
                       '--field-selector', 'spec.nodeName=' + args.node, '-o', 'json'))['items'][0]
assert clients and backends, 'Missing test clients or backend'
for client in clients:
    name = client['metadata']['name']
    source = client['status']['podIP']
    port = random.randint(35000, 49000)
    code = run('-n', args.namespace, 'exec', name, '--', 'curl', '-sS', '--max-time', '10',
               '--local-port', str(port), '-o', '/dev/null', '-w', '%{http_code}',
               'http://' + address + ':8080/')
    assert code == '200', f'{name}: Service returned {code}'
    for attempt in range(10):
        output = run('-n', 'cilium-system', 'exec', agent['metadata']['name'], '-c',
                     'cilium-agent', '--', 'hubble', 'observe', '--pod',
                     args.namespace + '/' + name, '--last', '100', '--output', 'json')
        request = reply = False
        for line in output.splitlines():
            flow = json.loads(line).get('flow', {})
            ip = flow.get('IP', {})
            tcp = flow.get('l4', {}).get('TCP', {})
            forward = (ip.get('source') == source and ip.get('destination') in backends
                       and tcp.get('source_port') == port)
            reverse = (ip.get('destination') == source and ip.get('source') in backends
                       and tcp.get('destination_port') == port)
            if forward or reverse:
                assert flow.get('verdict') == 'FORWARDED', f'{name}: {flow.get("verdict")}'
                flags = tcp.get('flags', {})
                request |= forward and flags.get('SYN', False)
                reply |= reverse and flags.get('SYN', False) and flags.get('ACK', False)
        if request and reply:
            print(f'{name}: Service HTTPS-independent HTTP 200; translated SYN/SYN-ACK FORWARDED')
            break
        time.sleep(0.5)
    else:
        raise AssertionError(f'{name}: missing translated request/reply Hubble flows')
