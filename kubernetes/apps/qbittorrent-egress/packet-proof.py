#!/usr/bin/env python3
"""Run an isolated, init-held probe with simultaneous header-only captures."""

import argparse
import json
import pathlib
import shlex
import subprocess
import tempfile
import time

PROBE = r'''
import http.client,json,socket,ssl,struct,sys,threading,time
mode=sys.argv[1];target_ip=sys.argv[2] if len(sys.argv)>2 else open('/gate/target-ip').read().strip();packets=[];stop=threading.Event();ready=threading.Event()
s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));s.bind(('eth0',0));s.settimeout(.1)
def capture():
 ready.set()
 while not stop.is_set():
  try:p=s.recv(65535)
  except socket.timeout:continue
  if len(p)<34:continue
  if p[12:14]==b'\x08\x00':
   src=socket.inet_ntop(socket.AF_INET,p[26:30]);dst=socket.inet_ntop(socket.AF_INET,p[30:34]);proto=p[23];o=14+(p[14]&15)*4
   if not ({src,dst}&{target_ip,'1.1.1.1'}) or proto not in [6,17] or len(p)<o+8:continue
   a,b=struct.unpack('!HH',p[o:o+4]);packets.append({'time':time.time(),'src':src,'dst':dst,'protocol':proto,'sport':a,'dport':b})
  elif p[12:14]==b'\x86\xdd' and len(p)>=54:
   src=socket.inet_ntop(socket.AF_INET6,p[22:38]);dst=socket.inet_ntop(socket.AF_INET6,p[38:54])
   if '2606:4700:4700::1111' in [src,dst]:packets.append({'ipv6_src':src,'ipv6_dst':dst})
t=threading.Thread(target=capture);t.start();ready.wait();results=[];failed=False
try:
 if mode in ('startup','normal'):
  class PinnedHTTPSConnection(http.client.HTTPSConnection):
   def connect(self):
    raw=socket.create_connection((target_ip,self.port),self.timeout,self.source_address)
    self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
  c=PinnedHTTPSConnection('am.i.mullvad.net',timeout=6,context=ssl.create_default_context());c.connect()
  for n in range(2):
   local=c.sock.getsockname();c.request('GET','/json',headers={'Connection':'keep-alive'});r=c.getresponse();d=json.loads(r.read())
   results.append({'TCP_probe':n,'local_socket':local,'HTTP_status':r.status,'public_ip':d.get('ip'),'mullvad_exit':d.get('mullvad_exit_ip')})
   if d.get('mullvad_exit_ip') is not True:failed=True
  c.close();fresh=PinnedHTTPSConnection('am.i.mullvad.net',timeout=6,context=ssl.create_default_context());fresh.connect()
  fresh_local=fresh.sock.getsockname();fresh.request('GET','/json',headers={'Connection':'close'});fr=fresh.getresponse();fd=json.loads(fr.read())
  results.append({'fresh_TCP_probe':True,'local_socket':fresh_local,'HTTP_status':fr.status,'public_ip':fd.get('ip'),'mullvad_exit':fd.get('mullvad_exit_ip')})
  if fd.get('mullvad_exit_ip') is not True or fresh_local==local:failed=True
  fresh.close();u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  for n in range(3):
   if n==2:u.close();u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
   u.sendto(('isolated-egress-udp-'+str(n)).encode(),('1.1.1.1',33434));results.append({'UDP_probe':n,'local_socket':u.getsockname(),'peer':['1.1.1.1',33434]})
  u.close()
 else:
  c=socket.socket(socket.AF_INET,socket.SOCK_STREAM);c.settimeout(3)
  try:c.connect((target_ip,443));results.append({'TCP':'UNEXPECTED_CONNECTED'});failed=True
  except socket.timeout:results.append({'TCP':'timeout'})
  finally:c.close()
  u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);u.settimeout(2);u.sendto(b'isolated-egress-drop-probe',('1.1.1.1',54321))
  try:u.recvfrom(1024);results.append({'UDP':'UNEXPECTED_RESPONSE'});failed=True
  except socket.timeout:results.append({'UDP':'timeout'})
  finally:u.close()
 v=socket.socket(socket.AF_INET6,socket.SOCK_STREAM);v.settimeout(2)
 try:v.connect(('2606:4700:4700::1111',443));results.append({'IPv6':'UNEXPECTED_CONNECTED'});failed=True
 except OSError as e:
  results.append({'IPv6_errno':e.errno})
  if e.errno!=101:failed=True
 finally:v.close()
except Exception as e:results.append({'probe_error':type(e).__name__});failed=True
finally:stop.set();t.join();s.close()
print(json.dumps({'results':results,'pod_packets':packets}),flush=True)
sys.exit(1 if failed else 0)
'''


def command(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def run(mode):
    namespace = 'qbittorrent' if mode in ('startup', 'normal') else 'qbittorrent-egress-test'
    name = 'qbittorrent-egress-' + mode
    labels = {'app.kubernetes.io/name': name,
              'app.kubernetes.io/controller': 'qbittorrent' if mode == 'startup' else 'drop-test'}
    image = 'docker.io/linuxserver/qbittorrent:5.3.0@sha256:75ecbb1c89ab7b0a21c4bde40b4820e4f1649d2d56d83b91913422155e8d2a5f'
    pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name, 'namespace': namespace, 'labels': labels},
           'spec': {'nodeSelector': {'kubernetes.io/hostname': 'k8s-w-1'},
                    'restartPolicy': 'Never', 'automountServiceAccountToken': False,
                    'initContainers': [{'name': 'hold', 'image': image,
                                        'command': ['python3', '-c', 'import os,time\nwhile not os.path.exists("/gate/release"):time.sleep(.1)'],
                                        'securityContext': {'allowPrivilegeEscalation': False},
                                        'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'}, 'limits': {'memory': '64Mi'}},
                                        'volumeMounts': [{'name': 'gate', 'mountPath': '/gate'}]}],
                    'containers': [{'name': 'probe', 'image': image, 'command': ['python3', '-c', PROBE, mode],
                                    'securityContext': {'allowPrivilegeEscalation': False},
                                    'resources': {'requests': {'cpu': '10m', 'memory': '64Mi'}, 'limits': {'memory': '128Mi'}},
                                    'volumeMounts': [{'name': 'gate', 'mountPath': '/gate'}]}],
                    'volumes': [{'name': 'gate', 'emptyDir': {}}]}}
    if mode == 'normal':
        items = json.loads(subprocess.check_output([
            'kubectl', '-n', namespace, 'get', 'pods',
            '-l', 'app.kubernetes.io/name=qbittorrent', '-o', 'json'
        ]))['items']
        if len(items) != 1 or items[0].get('status', {}).get('phase') != 'Running':
            raise RuntimeError('HALT: production qBittorrent pod is not uniquely Running')
        obj = items[0]
        name = obj['metadata']['name']
    else:
        command(['kubectl', 'apply', '-f', '-'], input=json.dumps(pod), text=True)
        for _ in range(60):
            obj = json.loads(subprocess.check_output(['kubectl', '-n', namespace, 'get', 'pod', name, '-o', 'json']))
            if any(x.get('state', {}).get('running') for x in obj.get('status', {}).get('initContainerStatuses', [])):
                break
            time.sleep(1)
        else:
            raise RuntimeError('HALT: init hold did not start')
    ip = obj['status']['podIP']
    cilium_pod = subprocess.check_output([
        'kubectl', '-n', 'cilium-system', 'get', 'pods',
        '-l', 'k8s-app=cilium', '--field-selector', 'spec.nodeName=k8s-w-1',
        '-o', 'jsonpath={.items[0].metadata.name}',
    ], text=True).strip()
    if not cilium_pod:
        raise RuntimeError('HALT: no Cilium agent found on w-1')
    for _ in range(30):
        mapping = subprocess.check_output(['kubectl', '-n', 'cilium-system', 'exec', cilium_pod, '--', 'cilium-dbg', 'bpf', 'egress', 'list'], text=True)
        rows = [x for x in mapping.splitlines() if x.split() and x.split()[0] == ip and '0.0.0.0/0' in x]
        if rows and ((mode in ('startup', 'normal') and '192.168.1.152' in rows[0]) or (mode == 'missing' and ('Not Found' in rows[0] or 'NotFound' in rows[0] or '0.0.0.0' in rows[0].split()[2:]))):
            break
        time.sleep(.5)
    else:
        raise RuntimeError('HALT: required map not observed; init remains held')
    probe_container = 'app' if mode == 'normal' else 'hold'
    target_ip = subprocess.check_output([
        'kubectl', '-n', namespace, 'exec', name, '-c', probe_container, '--',
        'python3', '-c',
        "import socket; print(next(x[4][0] for x in socket.getaddrinfo('am.i.mullvad.net',443,type=socket.SOCK_STREAM) if x[0]==socket.AF_INET))",
    ], text=True).strip()
    if not target_ip:
        raise RuntimeError('HALT: Mullvad check hostname did not resolve inside the held pod')
    if mode != 'normal':
        command(['kubectl', '-n', namespace, 'exec', name, '-c', 'hold', '--', 'python3', '-c',
                 'import sys; open("/gate/target-ip", "w").write(sys.argv[1])', target_ip])
    folder = pathlib.Path(tempfile.mkdtemp(prefix='qbittorrent-' + mode + '-proof-'))
    (folder / 'map.txt').write_text(mapping)
    udp_port = '33434' if mode in ('startup', 'normal') else '54321'
    flt = '((tcp and host ' + target_ip + ' and port 443) or (udp and host 1.1.1.1 and port ' + udp_port + ')) or (ip6 and host 2606:4700:4700::1111)'
    capture_seconds = 60
    commands = {
        'node': ['ssh', '-o', 'BatchMode=yes', 'root@pve-g3-1', f'timeout {capture_seconds} tcpdump -nn -l -i tap146i0 ' + shlex.quote(flt)],
        'router_lan': ['ssh', '-o', 'BatchMode=yes', 'root@opnsense', f'timeout {capture_seconds} tcpdump -nn -l -i vtnet0 ' + shlex.quote(flt)],
        'router_tunnel': ['ssh', '-o', 'BatchMode=yes', 'root@opnsense', f'timeout {capture_seconds} tcpdump -nn -l -i wg0 ' + shlex.quote(flt)],
        'router_wan_plain': ['ssh', '-o', 'BatchMode=yes', 'root@opnsense', f'timeout {capture_seconds} tcpdump -nn -l -i pppoe0 ' + shlex.quote(flt)],
        'router_wan_vpn': ['ssh', '-o', 'BatchMode=yes', 'root@opnsense', f'timeout {capture_seconds} tcpdump -nn -l -i pppoe0 ' + shlex.quote('host 23.234.87.2 and udp port 51820')],
    }
    handles = []
    processes = {}
    for key, args in commands.items():
        out = open(folder / (key + '.txt'), 'w')
        err = open(folder / (key + '.stderr'), 'w')
        handles.extend([out, err])
        processes[key] = subprocess.Popen(args, stdout=out, stderr=err)
    for _ in range(30):
        if all(process.poll() is None and 'listening on' in (folder / (k + '.stderr')).read_text() for k, process in processes.items()):
            break
        time.sleep(.2)
    else:
        raise RuntimeError('HALT: capture readiness failed; init remains held')
    print('map_before_probe:', rows[0], flush=True)
    if mode == 'normal':
        probe_process = subprocess.Popen([
            'kubectl', '-n', namespace, 'exec', name, '-c', 'app', '--',
            'python3', '-c', PROBE, mode, target_ip,
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    else:
        command(['kubectl', '-n', namespace, 'exec', name, '-c', 'hold', '--', 'python3', '-c', 'open("/gate/release","w").close()'])
    probe_started = time.monotonic()
    for _ in range(60):
        if any(process.poll() is not None for process in processes.values()):
            raise RuntimeError('HALT: a packet capture exited before the probe completed')
        if mode == 'normal':
            if probe_process.poll() is not None:
                break
        else:
            obj = json.loads(subprocess.check_output(['kubectl', '-n', namespace, 'get', 'pod', name, '-o', 'json']))
            if obj['status']['phase'] in ['Succeeded', 'Failed']:
                break
        time.sleep(.5)
    probe_seconds = time.monotonic() - probe_started
    if probe_seconds >= capture_seconds - 5:
        raise RuntimeError('HALT: probe ended too close to packet-capture timeout')
    if mode == 'normal':
        stdout, stderr = probe_process.communicate(timeout=5)
        if stderr.strip():
            raise RuntimeError('HALT: production pod probe emitted stderr')
        log = stdout
        probe_succeeded = probe_process.returncode == 0
    else:
        log = subprocess.check_output(['kubectl', '-n', namespace, 'logs', name, '-c', 'probe'], text=True)
        probe_succeeded = obj['status']['phase'] == 'Succeeded'
    (folder / 'pod.json').write_text(log)
    print(log, flush=True)
    for process in processes.values():
        process.wait(timeout=capture_seconds + 5)
    for handle in handles:
        handle.close()
    print('evidence_directory:', folder)
    counts = {}
    tcp_evidence = {}
    udp_evidence = {}
    for key in commands:
        returncode = processes[key].returncode
        stderr = (folder / (key + '.stderr')).read_text()
        if returncode != 124 or 'packets captured' not in stderr:
            raise RuntimeError(f'HALT: {key} capture did not complete its full timed window (exit {returncode})')
        lines = [line for line in (folder / (key + '.txt')).read_text().splitlines() if line.strip()]
        counts[key] = len(lines)
        tcp_evidence[key] = any(target_ip + '.443:' in line and 'Flags' in line for line in lines)
        udp_evidence[key] = any('1.1.1.1.' + udp_port + ':' in line and 'UDP' in line for line in lines)
        print(key, 'packet_lines:', len(lines))
        print('\n'.join(lines[:3]))
    if not probe_succeeded or counts['router_wan_plain']:
        raise RuntimeError('HALT: probe failed or plaintext probe traffic appeared on WAN')
    pod_data = json.loads(log)
    pod_packets = pod_data.get('pod_packets', [])
    if mode in ('startup', 'normal'):
        if not any(p.get('dst') == target_ip and p.get('protocol') == 6 for p in pod_packets):
            raise RuntimeError('HALT: pod capture lacks the TCP probe')
        if not any(p.get('dst') == '1.1.1.1' and p.get('protocol') == 17 for p in pod_packets):
            raise RuntimeError('HALT: pod capture lacks the UDP probe')
    else:
        if not any(p.get('dst') == target_ip and p.get('protocol') == 6 for p in pod_packets):
            raise RuntimeError('HALT: pod capture lacks the blocked TCP attempt')
        if not any(p.get('dst') == '1.1.1.1' and p.get('protocol') == 17 for p in pod_packets):
            raise RuntimeError('HALT: pod capture lacks the blocked UDP attempt')
    if mode in ('startup', 'normal') and any(not tcp_evidence[k] or not udp_evidence[k] for k in ['node', 'router_lan', 'router_tunnel']):
        raise RuntimeError('HALT: a capture lacks TCP or UDP positive packet evidence')
    if mode in ('startup', 'normal') and not counts['router_wan_vpn']:
        raise RuntimeError('HALT: no encrypted WireGuard carrier packet captured on WAN')
    if mode == 'missing' and any(counts[k] for k in ['node', 'router_lan', 'router_tunnel']):
        raise RuntimeError('HALT: isolated drop probe escaped node')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['normal', 'startup', 'missing'])
    run(parser.parse_args().mode)
