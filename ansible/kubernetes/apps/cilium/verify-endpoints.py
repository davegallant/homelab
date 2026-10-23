#!/usr/bin/env python3
"""Require every active pod using the pod network to have a Cilium endpoint."""
import argparse
import ipaddress
import json
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--context', required=True)
parser.add_argument('--namespace')
args = parser.parse_args()
base = ['kubectl', '--context', args.context]
scope = ['-n', args.namespace] if args.namespace else ['-A']


def read(kind):
    return json.loads(subprocess.check_output(base + ['get', kind] + scope + ['-o', 'json'],
                                             text=True, timeout=30))['items']


endpoints = {(p['metadata']['namespace'], p['metadata']['name']): p for p in read('ciliumendpoints')}
checked = host_network = 0
for pod in read('pods'):
    if pod['status']['phase'] in ['Succeeded', 'Failed'] or pod['metadata'].get('deletionTimestamp'):
        continue
    if pod['spec'].get('hostNetwork', False):
        host_network += 1
        continue
    key = (pod['metadata']['namespace'], pod['metadata']['name'])
    assert pod['status']['phase'] == 'Running', f'{key}: not Running'
    address = pod['status']['podIP']
    assert ipaddress.ip_address(address) in ipaddress.ip_network('10.245.0.0/16'), f'{key}: {address}'
    assert key in endpoints, f'{key}: no Cilium endpoint'
    networking = endpoints[key].get('status', {}).get('networking', {}).get('addressing', [])
    assert any(item.get('ipv4') == address for item in networking), f'{key}: endpoint IP mismatch'
    checked += 1
print(f'{checked} pod-network pods verified as Cilium endpoints; {host_network} host-network pods accounted for')
