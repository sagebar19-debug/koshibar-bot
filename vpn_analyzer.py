"""Analyse prudente de fichiers de configuration VPN, sans exécution de code."""
import base64
import gzip
import hashlib
import json
import re
import urllib.parse
import zlib

MAX_BYTES = 19 * 1024 * 1024
GROUPS = {
'EHI': '.ehi .ehil', 'HC': '.hc', 'NPVT': '.npvt .npvtsub .npv4',
'DARK': '.dark', 'SSC': '.ssc', 'EV2RAY': '.v2',
'HTTP TWEAK': '.ht', 'SIP': '.sip', 'HAT': '.hat', 'NETMOD': '.nm',
'OPENTUNNEL': '.tnl', 'SLIPNET': '.slipnet', 'TLS': '.tls',
'LINKLAYER': '.lnk', 'MINA': '.mina .oc',
'SANDOK': '.aura .bcl .bee .btv .ena .vel .eta .fix .glory .marvs .nur .mdvpn .md .ost .osv .ry .t20 .tik .tsm .tx .ulti .ultra .vlx .wolf .mmt',
'RENZ': '.tcx .7net .ihome .xhypher .izph .osp .bshield .enz',
'PRINCE': '.apnalite .bdnet .hxt .4ulite .fnf .omanova .ursa .hsome',
'STARK': '.stk', 'ZIV': '.ziv', 'WYR': '.wyr', 'INT': '.int',
'EUT': '.eut', 'NOOBDEV': '.maya .roy .ar'
}
EXTENSIONS = {ext: group for group, items in GROUPS.items() for ext in items.split()}
FORMAT_LIST = '\n'.join(f'[{name}] - {", ".join(exts.split())}' for name, exts in GROUPS.items())
URL_RE = re.compile(r'(?i)\b(?:vless|vmess|trojan|ss|ssh|http|https|socks5)://[^\s<>"\']{1,1500}')
DOMAIN_RE = re.compile(r'(?i)\b(?:[a-z0-9-]{1,63}\.)+[a-z]{2,24}\b')
KEY_RE = re.compile(r'(?i)(?:host|sni|server|address|port|method|payload|proxy|dns|message|user-agent|uuid|password|token|key)')
SENSITIVE = re.compile(r'(?i)(?:password|passwd|token|secret|uuid|private.?key|authorization|credential|account|user|payload)')


def _safe(value):
    value = str(value).replace('\n', ' ').replace('\r', ' ').strip()[:180]
    return '[masqué]' if SENSITIVE.search(value) else value


def _extract(data):
    text = data.decode('utf-8', 'replace')
    readable = sum(c.isprintable() or c in '\r\n\t' for c in text) / max(len(text), 1)
    return text, readable


def _structured(text):
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return []
    found = []
    def walk(item, prefix='', depth=0):
        if depth > 9 or len(found) >= 100:
            return
        if isinstance(item, dict):
            for k, v in list(item.items())[:150]:
                key = str(k)[:70]
                if isinstance(v, (dict, list)):
                    walk(v, key, depth+1)
                elif KEY_RE.search(key):
                    found.append((key, '[masqué]' if SENSITIVE.search(key) else _safe(v)))
        elif isinstance(item, list):
            for v in item[:100]:
                walk(v, prefix, depth+1)
    walk(obj)
    return found


def analyze_file(path):
    from pathlib import Path
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in EXTENSIONS:
        raise ValueError('Format non autorisé')
    if p.stat().st_size > MAX_BYTES:
        raise ValueError('Fichier trop grand pour le téléchargement Telegram standard')
    data = p.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    decoded = [('Original', data)]
    text, ratio = _extract(data)
    compact = ''.join(text.split())
    if len(compact) >= 16 and len(compact) < 2_000_000 and re.fullmatch(r'[A-Za-z0-9+/=]+', compact):
        try:
            decoded.append(('Base64', base64.b64decode(compact, validate=True)))
        except (ValueError, base64.binascii.Error):
            pass
    for label, func in [('GZIP', gzip.decompress), ('ZLIB', zlib.decompress)]:
        try:
            if len(data) <= 1_000_000:
                result = func(data)
                if len(result) <= 2_000_000:
                    decoded.append((label, result))
        except (OSError, ValueError, zlib.error):
            pass
    links, hosts, fields, encodings = [], [], [], []
    for label, payload in decoded:
        content, score = _extract(payload[:2_000_000])
        if score < .55:
            continue
        encodings.append(label)
        for item in URL_RE.findall(content):
            scheme = urllib.parse.urlsplit(item).scheme.lower()
            links.append(scheme.upper())
            try:
                parsed = urllib.parse.urlsplit(item)
                if parsed.hostname:
                    hosts.append(parsed.hostname)
            except ValueError:
                pass
        hosts.extend(DOMAIN_RE.findall(content)[:300])
        fields.extend(_structured(content))
        for line in content.splitlines()[:3000]:
            match = re.match(r'^\s*([\w. -]{2,60})\s*[:=]\s*(.{1,250})$', line)
            if match and KEY_RE.search(match.group(1)):
                key, val = match.groups()
                fields.append((key, '[masqué]' if SENSITIVE.search(key) else _safe(val)))
    # No passwords, raw tokens, payloads, or complete connection URIs in reports.
    fields = list(dict.fromkeys(fields))[:60]
    hosts = list(dict.fromkeys(hosts))[:40]
    links = sorted(set(links))
    return {'format': EXTENSIONS[ext], 'extension': ext, 'sha256': sha,
            'size': len(data), 'encodings': encodings, 'hosts': hosts,
            'protocols': links, 'fields': fields,
            'status': 'Données lisibles détectées' if encodings else 'Contenu binaire ou chiffré non décodé'}


def format_report(result):
    lines = [
        '🔓 KOSHIBAR VPN ANALYZER', '━━━━━━━━━━━━━━━━━━━━',
        f'📂 Format : {result["format"]} ({result["extension"]})',
        f'📦 Taille : {result["size"]} octets',
        f'🔎 SHA256 : {result["sha256"]}',
        f'📌 Résultat : {result["status"]}',
        f'📖 Encodages lisibles : {", ".join(result["encodings"]) or "aucun"}',
        f'🌐 Protocoles repérés : {", ".join(result["protocols"]) or "aucun"}',
        '', '🖥️ Hôtes/domaines détectés :'
    ]
    lines.extend('• ' + host for host in result['hosts'][:30])
    if not result['hosts']:
        lines.append('Aucun')
    lines.append('\n⚙️ Paramètres lisibles (secrets masqués) :')
    lines.extend(f'• {k}: {v}' for k, v in result['fields'][:35])
    if not result['fields']:
        lines.append('Aucun')
    lines.append('\n⚠️ Les formats propriétaires chiffrés nécessitent un décodeur et les clés compatibles. Aucun déchiffrement garanti.')
    return '\n'.join(lines)[:3900]
