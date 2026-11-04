"""Reconcile stable route IDs without logging tokens, URLs or responses."""
import json
import os
import sys
import time
from urllib.request import Request, build_opener, ProxyHandler


def reconcile(check=False):
    base = os.environ['ADMIN_URL']
    headers = {'Authorization': 'Bearer ' + os.environ['STOA_ADMIN_API_TOKEN'],
               'Content-Type': 'application/json'}
    client = build_opener(ProxyHandler({}))
    if check:
        with client.open(Request(base + '/admin/apis', headers=headers), timeout=3) as r:
            actual = {r['id']: r for r in json.load(r)}
    for name in ('echo', 'meteo'):
        route = dict(id='demo-' + name, name='demo-' + name, tenant_id='demo',
                     path_prefix='/apis/demo/' + name,
                     backend_url='http://demo-echo:8080/apis/demo/' + name,
                     methods=[], spec_hash='', activated=True)
        if check:
            if any(actual.get(route['id'], {}).get(k) != v for k, v in route.items()):
                raise ValueError('Routes not ready')
        else:
            req = Request(base + '/admin/apis', data=json.dumps(route).encode(), headers=headers)
            with client.open(req, timeout=3) as response:
                if response.status not in (200, 201):
                    raise ValueError('Route rejected')


if __name__ == '__main__':
    check = '--check' in sys.argv
    deadline = time.monotonic() + 120
    while True:
        try:
            reconcile(check)
            if check or '--once' in sys.argv:
                break
        except Exception:
            if check or ('--once' in sys.argv and time.monotonic() > deadline):
                sys.exit(1)
        time.sleep(5)
