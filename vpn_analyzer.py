"""KOSHIBAR VPN decoder: safe static analysis of authorized configurations.
No proprietary encryption bypass or secret extraction.
"""
import base64
import gzip
import hashlib
import json
import re
import zlib
from pathlib import Path
from urllib.parse import urlsplit

MAX_SIZE = 20 * 1024 * 1024
FORMATS = {
 'EHI':'.ehi .ehil', 'HC':'.hc', 'NPVT':'.npvt .npvtsub .npv4',
 'DARK':'.dark', 'SSC':'.ssc', 'EV2RAY':'.v2', 'HTTP TWEAK':'.ht',
 'SIP':'.sip', 'HAT':'.hat', 'NETMOD':'.nm', 'OPENTUNNEL':'.tnl',
 'SLIPNET':'.slipnet', 'TLS':'.tls', 'LINKLAYER':'.lnk',
 'MINA':'.mina .oc',
 'SANDOK':'.aura .bcl .bee .btv .ena .vel .eta .fix .glory .marvs .nur .mdvpn .md .ost .osv .ry .t20 .tik .tsm .tx .ulti .ultra .vlx .wolf .mmt',
 'RENZ':'.tcx .7net .ihome .xhypher .izph .osp .bshield .enz',
 'PRINCE':'.apnalite .bdnet .hxt .4ulite .fnf .omanova .ursa .hsome',
 'STARK':'.stk', 'ZIV':'.ziv', 'WYR':'.wyr', 'INT':'.int',
 'EUT':'.eut', 'NOOBDEV':'.maya .roy .ar',
}
EXTENSIONS = {ext: family for family, values in FORMATS.items() for ext in values.split()}
EXTENSIONS['.json'] = 'JSON'
EXTENSIONS['.txt'] = 'TEXT'
EXTENSIONS['.yaml'] = 'YAML'
EXTENSIONS['.yml'] = 'YAML'
EXTENSIONS['.conf'] = 'CONFIG'
EXTENSIONS['.xml'] = 'XML'

FIELDS = {
 'host': ('host','hostname','server','address','remote','serveraddress'),
 'port': ('port','serverport','remoteport'),
 'sni': ('sni','servername','server_name','tlsservername'),
 'proxy': ('proxy','proxyhost','proxyaddress'),
 'dns': ('dns','dnsserver','resolver'),
 'payload': ('payload','httppayload','requestpayload'),
 'method': ('method','httpmethod','security','network'),
 'message': ('message','note','description','remarks'),
 'path': ('path','wspath','websocketpath'),
 'protocol': ('protocol','type','vpnprotocol'),
}
SENSITIVE = re.compile(r'(password|passwd|token|secret|private|credential|uuid|user(name)?|authorization|cookie|key)',re.I)
HOST_RE = re.compile(r'(?<![\w.-])(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?![\w.-])')
URL_RE = re.compile(r'(?i)\b(?:vless|vmess|trojan|ss|ssh|https?|httptweak)://[^\s<>"\']+')


def _text(data):
    return data.decode('utf-8', errors='replace')


def _decoded_layers(data):
    """Bounded non-cryptographic decoding, max 2 nested layers."""
    yield 'Original', data
    queue = [('Original', data, 0)]
    seen = {hashlib.sha256(data).digest()}
    while queue:
        label, blob, depth = queue.pop(0)
        if depth >= 2:
            continue
        candidates = []
        for name, func in [('GZIP',gzip.decompress), ('ZLIB',zlib.decompress)]:
            try:
                candidates.append((name,func(blob)))
            except (OSError,zlib.error,EOFError,ValueError):
                pass
        try:
            compact = re.sub(rb'\s+', b'', blob)
            if len(compact) >= 16 and len(compact) % 4 == 0 and re.fullmatch(rb'[A-Za-z0-9+/]+={0,2}',compact):
                candidates.append(('Base64',base64.b64decode(compact,validate=True)))
        except (ValueError,base64.binascii.Error):
            pass
        for name, decoded in candidates:
            if len(decoded) > MAX_SIZE or not decoded:
                continue
            digest = hashlib.sha256(decoded).digest()
            if digest not in seen:
                seen.add(digest)
                next_label = label + ' → ' + name
                yield next_label, decoded
                queue.append((next_label,decoded,depth+1))


def _collect_json(node, found):
    if isinstance(node,dict):
        for key,value in node.items():
            if SENSITIVE.search(str(key)):
                continue
            normal = re.sub(r'[^a-z0-9]','',str(key).lower())
            if isinstance(value,(str,int,float,bool)):
                for field, aliases in FIELDS.items():
                    if normal in {re.sub(r'[^a-z0-9]','',x) for x in aliases}:
                        found.setdefault(field,set()).add(str(value)[:250])
            else:
                _collect_json(value,found)
    elif isinstance(node,list):
        for item in node[:500]:
            _collect_json(item,found)


def analyze_bytes(data, filename='configuration.conf'):
    if len(data) > MAX_SIZE:
        raise ValueError('Fichier trop volumineux (maximum 20 Mo pour cette analyse).')
    ext = Path(filename).suffix.lower()
    if ext not in EXTENSIONS:
        raise ValueError('Extension non prise en charge : ' + ext)
    fields = {}
    hosts = set()
    protocols = set()
    layers = []
    for label,blob in _decoded_layers(data):
        layers.append(label)
        txt = _text(blob)
        if len(txt) > MAX_SIZE:
            continue
        try:
            parsed = json.loads(txt)
            _collect_json(parsed,fields)
        except (ValueError,RecursionError):
            pass
        for match in URL_RE.findall(txt):
            scheme = match.split('://',1)[0].lower()
            protocols.add(scheme.upper())
            if scheme in ('http','https'):
                try:
                    host = urlsplit(match).hostname
                    if host:
                        hosts.add(host)
                except ValueError:
                    pass
        for match in HOST_RE.findall(txt):
            if len(match) < 120:
                hosts.add(match)
        for line in txt.splitlines()[:10000]:
            m = re.match(r'^\s*["\']?([\w.-]{2,35})["\']?\s*[:=]\s*(.{1,250})\s*$',line)
            if not m or SENSITIVE.search(m.group(1)):
                continue
            key = re.sub(r'[^a-z0-9]','',m.group(1).lower())
            value = m.group(2).strip().strip('"\',')
            for field, aliases in FIELDS.items():
                if key in {re.sub(r'[^a-z0-9]','',x) for x in aliases}:
                    fields.setdefault(field,set()).add(value[:250])
    # Redact possible credentials in free-form payloads and proxy URLs.
    def redact(v):
        v = re.sub(r'(?i)(password|token|secret|authorization|cookie|key)\s*[:=]\s*[^\s&;]+',r'\1=[MASQUÉ]',v)
        v = re.sub(r'://[^/@\s]+@','://[MASQUÉ]@',v)
        return v
    clean = {k:sorted({redact(x) for x in v})[:20] for k,v in fields.items()}
    return {
        'filename': Path(filename).name,
        'family': EXTENSIONS[ext],
        'size':len(data),
        'sha256':hashlib.sha256(data).hexdigest(),
        'layers':layers,
        'protocols':sorted(protocols),
        'hosts':sorted(hosts)[:30],
        'fields':clean,
        'status':'Paramètres accessibles détectés' if (clean or hosts or protocols) else 'Aucun paramètre décodable détecté',
        'warning':'La reconnaissance du format ne prouve pas son déchiffrement. Les formats propriétaires chiffrés nécessitent une méthode et des clés compatibles.'
    }


def analyze_file(path):
    p = Path(path)
    if p.stat().st_size > MAX_SIZE:
        raise ValueError('Fichier trop volumineux (20 Mo maximum).')
    return analyze_bytes(p.read_bytes(),p.name)


def format_report(result):
    lines = [
        '🔓 KOSHIBAR VPN DECODEZ',
        '━━━━━━━━━━━━━━━━━━━━',
        '📁 Fichier : '+result['filename'],
        '📂 Famille : '+result['family'],
        '📦 Taille : '+str(result['size'])+' octets',
        '🔎 Statut : '+result['status'],
        '📖 Couches : '+', '.join(result['layers']),
        '🌐 Protocoles : '+(', '.join(result['protocols']) or 'Aucun'),
        '🖥️ Hôtes : '+(', '.join(result['hosts']) or 'Aucun'),
        '', '⚙️ PARAMÈTRES ACCESSIBLES'
    ]
    for field, values in result['fields'].items():
        lines.append(field.upper() + ' : ' + '; '.join(values))
    if not result['fields']:
        lines.append('Aucun')
    lines.extend(['', '⚠️ '+result['warning']])
    return '\n'.join(lines)[:3900]

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        print('Usage: python vpn_analyzer.py fichier.tnl')
        sys.exit(1)
    print(format_report(analyze_file(sys.argv[1])))
