from io import BytesIO
from manualexpiringdict import ManualExpiringDict
from collections import defaultdict
import csv
import gzip
import asyncio
import re
import ipaddress
import logging
import websockets
import subprocess
import os
import urllib.request
import datetime
from functools import wraps
import time
import json
import random
import pickle

logging.getLogger().setLevel(logging.INFO)

hosts = ManualExpiringDict[str, set](max_age_seconds=180)
hosts_rev = ManualExpiringDict[str, set](max_age_seconds=180)
ipt_cache = set()
config = {}
ipv4_re = re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
PORT = os.environ.get('PORT') or 8765


def read_config():
    global config
    merge_keys = {'subnet_lists', 'subnets', 'domains', 'domain_lists', 'countries', 'route_table_num'}
    config = {

        'MAX_DEPTH': 5,
        'CHAIN': os.environ.get('CHAIN') or 'MRVPN_SUBNETS',
        'iptables': os.environ.get('IPTABLES') or '/usr/sbin/iptables',
        'iptables_save': os.environ.get('IPTABLES_SAVE') or '/usr/sbin/iptables-save',
        'iptables_restore': os.environ.get('IPTABLES_RESTORE') or '/usr/sbin/iptables-restore',

        'countries': os.environ.get('COUNTRIES') or 'RU|AM',
        'ROUTE_TABLE_NUM': os.environ.get('ROUTE_TABLE_NUM') or '11',
        'INBOUND_IF': os.environ.get('INBOUND_IF') or 'wg-firezone'}
    conf_file = os.environ.get('CONFIG')
    if conf_file:
        with open(conf_file, 'r') as f:
            conf_data = json.load(f)
            for key, value in conf_data.items():
                if key in merge_keys:
                    config[key] = value

    logging.info(f'Countries: {config["countries"]}')


def timeit(func):
    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        logging.info(f'Function {func.__name__}{args} {kwargs} Took {total_time:.4f} seconds')
        return result

    return timeit_wrapper


def get_request(l_url):
    buster = random.Random().randint(1, 1000000)
    if -1 != l_url.find('?'):
        l_url = l_url + f"&buster_{buster}"
    else:
        l_url = l_url + f"?buster_{buster}"
    return urllib.request.Request(
        l_url,
        data=None,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'
        }
    )


def load_domains() -> set[re.Pattern]:
    r = set()

    for url in config.get('domain_lists') or []:
        with urllib.request.urlopen(get_request(url)) as f:
            d = f.read().decode('utf-8')
            d = re.sub(r'\s+#.*', '', d)
            for p in d.splitlines():
                r.add(re.compile(p))
    logging.info(f'Loaded {len(r)} domain regexes: {r}')
    return r


def load_nets() -> set[ipaddress.IPv4Network]:
    c = []
    if type(config['countries']) == str:
        c = config['countries'].split('|')
    elif type(config['countries']) == list:
        c = config['countries']

    d = "{:%Y-%m}".format(datetime.datetime.now())

    url = f"https://download.db-ip.com/free/dbip-country-lite-{d}.csv.gz"
    nets = set()
    with urllib.request.urlopen(get_request(url)) as f:
        g = gzip.GzipFile(fileobj=BytesIO(f.read()), mode='r')
        subnets = list(csv.reader(g.read().decode('utf-8').splitlines()))
        for subnet in subnets:
            if subnet[2] in c and ipv4_re.match(subnet[0]) and ipv4_re.match(subnet[1]):
                nets |= set(
                    ipaddress.summarize_address_range(ipaddress.IPv4Address(subnet[0]),
                                                      ipaddress.IPv4Address(subnet[1])))
    for n in config['subnets']:
        nets.add(ipaddress.IPv4Network(n))
    for url in config.get('subnet_lists') or []:
        with urllib.request.urlopen(get_request(url)) as f:
            d = f.read().decode('utf-8')
            d = re.sub(r'\s+#.*', '', d)
            for ip in d.splitlines():
                if ipv4_re.match(ip):
                    nets.add(ipaddress.IPv4Network(ip))
    for sn in config.get('subnets') or []:
        sn = re.sub(r'\s+#.*', '', sn)
        if ipv4_re.match(sn):
            nets.add(ipaddress.IPv4Network(sn))
    rv = set(ipaddress.collapse_addresses(nets))
    return rv


def init_iptables(subnets):
    global ipt_cache, config
    iptables_save = config['iptables_save']
    iptables_restore = config['iptables_restore']
    iptables = config['iptables']
    chain = config['CHAIN']
    inbound_if = config['INBOUND_IF']
    route_table_num = config['ROUTE_TABLE_NUM']
    output = subprocess.check_output(f'sudo {iptables_save} -t mangle', shell=True).decode('utf-8')
    chains = output.splitlines()
    if f':{chain}' in [x.split()[0] for x in chains if re.match('^:.*', x)]:
        subprocess.check_output(f'sudo {iptables} -t mangle -F {chain}', shell=True)
    else:
        subprocess.check_output(f'sudo {iptables} -t mangle -N {chain}', shell=True)
    if 'MRVPN_SUBNETS_JUMP' not in output:
        subprocess.check_output(
            f'sudo iptables -A PREROUTING -t mangle -i {inbound_if} -p tcp -j {chain} '
            f'-m comment --comment "{chain}_JUMP"',
            shell=True)
    ipt_rules = '*mangle\n:MRVPN_SUBNETS -\n'
    for n in subnets:
        ipt_rules += f'-A {chain} --dst "{str(n)}" -j RETURN\n'
        ipt_cache.add(n)
    ipt_rules += 'COMMIT\n'
    subprocess.check_output(f'sudo {iptables_restore} --noflush', input=ipt_rules.encode('utf-8'), shell=True)
    subprocess.check_output(f'sudo {iptables} -A {chain} -t mangle -j MARK --set-mark "{route_table_num}"', shell=True)


def add_to_ipt(ip: ipaddress.IPv4Address):
    global config
    iptables = config['iptables']
    chain = config['CHAIN']
    c = [x for x in ipt_cache if ip in x]
    if len(c) == 0:
        logging.debug(f'Adding to iptables: {ip}')
        ipt_cache.add(ipaddress.IPv4Network(ip))
        cmd = f'sudo {iptables} -t mangle -I {chain} 1 -d {ip} -j RETURN' \
              ' -m comment --comment "MRVPN_HOST"'
        logging.debug(cmd)
        subprocess.check_output(cmd, shell=True)

    else:
        logging.debug(f'Already added: {ip}')
    pass


# find all descendants from the record and add ips to the iptables
def fw_process(record):
    global config
    lower = hosts.get(record)
    new = lower
    left_iters = config['MAX_DEPTH']
    while len(new) > 0 or left_iters > 0:
        c = set()
        for x in new:
            t = hosts.get(x)
            if t is not None:
                c |= hosts.get(x)
        new = c - lower
        lower |= new
        left_iters -= 1
    ips = {ipaddress.IPv4Address(x) for x in lower if ipv4_re.match(x)}
    for i in ips:
        add_to_ipt(i)


@timeit
def full_process():
    logging.info(f'Full processing')
    doms = {x for x in hosts if any(r.match(x) for r in dom_re)}
    for d in doms:
        fw_process(d)
    logging.info(f'Forward size: {len(hosts)}, reverse size: {len(hosts_rev)}, ipt_cache size {len(ipt_cache)}')


def fast_process(record: str, value: str):
    fw_dirty = False
    rev_dirty = False
    # add to forward match db
    if record in hosts.keys():
        if value not in hosts[record]:
            hosts[record].add(value)
            fw_dirty = True
    else:
        hosts[record] = {value}
        fw_dirty = True
    # add to reverse db
    if value in hosts_rev.keys():
        if record not in hosts_rev[value]:
            hosts_rev[value].add(record)
            rev_dirty = True
    else:
        hosts_rev[value] = {record}
        rev_dirty = True
    # check if domain in list
    if any(r.match(record) for r in dom_re):
        # if the record points to IP address - process immediately
        logging.info(f"{record} matches")
        if ipv4_re.match(value):
            logging.info(f"Have ip Adding {value} for {record}")
            add_to_ipt(ipaddress.IPv4Address(value))
        else:
            logging.info(f"Performing forward process for {record}")
            fw_process(record)
    else:
        if fw_dirty or rev_dirty:
            logging.info(f"Db is dirty starting full process for {record}")
            full_process()


async def echo(websocket):
    async for message in websocket:
        logging.debug(message)
        record, rec_type, value = message.split(':')
        record = record.lower()
        value = value.lower()
        fast_process(record, value)
        hosts.expire()
        hosts_rev.expire()


async def main():
    global config
    async with websockets.serve(echo, "localhost", PORT, ping_timeout=30, ping_interval=30):
        await asyncio.Future()  # run forever


def test():
    fast_process('google.ru.', 'cn1.')
    fast_process('ozon.ru.', 'cn1.')
    fast_process('cn1.', 'cn2.')
    fast_process('cn1.', 'cn3.')
    fast_process('cn3.', 'cn4.')
    time.sleep(20)
    fast_process('cn4.', '1.1.1.1')


read_config()
dom_re = load_domains()
init_iptables(load_nets())
# test()
# hosts.expire()
# pass
asyncio.run(main())
