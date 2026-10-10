#!/usr/bin/env python3
"""Update a user-owned free DuckDNS hostname; keep its token outside Git/argv."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import urlopen


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--private-config',required=True,type=Path);a=p.parse_args()
    config=json.loads(a.private_config.read_text())
    try:
        # Empty ip asks DuckDNS to use the requesting CPU server's public IPv4.
        url='https://www.duckdns.org/update?'+urlencode({'domains':config['subdomain'],'token':config['token'],'ip':''})
        with urlopen(url,timeout=15) as response:result=response.read().decode().strip()
        if result!='OK':raise RuntimeError('DNS update was refused')
    except Exception as error:
        print('DuckDNS update failed: '+type(error).__name__,file=sys.stderr);return 1
    print('DuckDNS hostname updated');return 0

if __name__=='__main__':sys.exit(main())
