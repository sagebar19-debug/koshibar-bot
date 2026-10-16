"""Analyseur avancé et extracteur de configurations VPN (SSH, V2Ray, DNSTT, Hysteria, etc.)."""
import base64
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

# Augmentation de la limite à 100 Mo pour accepter tous les gros APK
MAX_BYTES = 100 * 1024 * 1024
MAX_ZIP_ENTRIES = 3500
MAX_UNCOMPRESSED = 150 * 1024 * 1024
MAX_ENTRY = 10 * 1024 * 1024

PATTERNS = {
    "VLESS": rb"vless://[^\s\x00\"'<>]{1,3000}",
    "VMESS": rb"vmess://[^\s\x00\"'<>]{1,3000}",
    "TROJAN": rb"trojan://[^\s\x00\"'<>]{1,3000}",
    "SHADOWSOCKS": rb"ss://[^\s\x00\"'<>]{1,3000}",
    "SSH": rb"(?:ssh://|dropbear|openssh|proxy)[^\s\x00\"'<>]{1,1000}",
    "DNSTT / SlowDNS": rb"(?:dns|dnstt|ns[0-9]*\.)[^\s\x00\"'<>]{1,2000}",
    "HYSTERIA / UDP": rb"(?:hysteria|quic|udp)://[^\s\x00\"'<>]{1,2000}",
    "PAYLOAD / PROXY": rb"(?:GET|POST|HTTP/1\.[01]|CONNECT|UPGRADE|WEBSOCKET)\s+[^\s\x00\"'<>]+",
}

CONFIG_SUFFIXES = (".json", ".xml", ".conf", ".txt", ".yaml", ".yml", ".properties", ".hc", ".npvt", ".dark", ".sip", ".ovpn", ".ssh", ".bin")


def _hash_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan(data, totals, extracted_configs):
    for label, pattern in PATTERNS.items():
        matches = re.findall(pattern, data, flags=re.IGNORECASE)
        for m in matches:
            try:
                decoded_m = m.decode('utf-8', errors='ignore').strip()
                if decoded_m and decoded_m not in extracted_configs:
                    if len(extracted_configs) < 30:  # On élargit la capture pour ne rien rater
                        extracted_configs.append(decoded_m)
                totals[label] = totals.get(label, 0) + 1
            except Exception:
                pass


def analyze_file(path, display_name=None):
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError("Fichier trop grand (limite portée à 100 Mo).")
    filename = (display_name or Path(path).name)[:120]
    apk = filename.lower().endswith(".apk")
    report = {
        "filename": filename, "type": "APK" if apk else "CONFIG",
        "sha256": _hash_file(path), "scanned": 0, "protocols": {},
        "config_files": [], "format": "inconnu", "notes": [], "extracted": [], "raw_text": ""
    }
    
    if apk:
        if not zipfile.is_zipfile(path):
            raise ValueError("Ce fichier .apk n'est pas une archive ZIP valide.")
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES or sum(x.file_size for x in entries) > MAX_UNCOMPRESSED:
                raise ValueError("Archive trop volumineuse après décompression.")
            for entry in entries:
                if entry.is_dir() or entry.file_size > MAX_ENTRY or entry.flag_bits & 1:
                    continue
                if any(k in entry.filename.lower() for k in ["assets", "raw", "db", "config", ".json", ".dark", ".net", ".ovpn", ".orc"]):
                    report["config_files"].append(entry.filename[:100])
                try:
                    data = archive.read(entry)
                    _scan(data, report["protocols"], report["extracted"])
                    
                    # Décodage Base64 et recherche JSON interne
                    if len(data) > 5:
                        try:
                            compact = b"".join(data.split())
                            if len(compact) % 4 == 0:
                                decoded_b64 = base64.b64decode(compact, validate=True)
                                _scan(decoded_b64, report["protocols"], report["extracted"])
                                text_dec = decoded_b64.decode('utf-8', errors='ignore')
                                if "{" in text_dec and "}" in text_dec:
                                    report["raw_text"] += f"\n--- Fichier interne : {entry.filename} ---\n" + text_dec
                        except Exception:
                            pass
                except (OSError, RuntimeError, zipfile.BadZipFile):
                    continue
                report["scanned"] += 1
        report["config_files"] = report["config_files"][:30]
        report["notes"].append("Extraction approfondie et décodage complet des moteurs VPN effectués.")
    else:
        with open(path, "rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        _scan(data, report["protocols"], report["extracted"])
        report["scanned"] = 1
        try:
            text = data.decode("utf-8", errors='ignore')
            report["raw_text"] = text
            json_obj = json.loads(text)
            report["format"] = "JSON / Config structurée"
            report["raw_text"] = json.dumps(json_obj, indent=2, ensure_ascii=False)
        except (UnicodeError, ValueError):
            report["format"] = "Texte, Binaire ou Payload chiffré"
            report["raw_text"] = data.decode('utf-8', errors='ignore')
            
        # Décodage global Base64 pour les fichiers chiffrés (.dark, .hc, etc.)
        try:
            compact = b"".join(data.split())
            if len(compact) > 10 and len(compact) % 4 == 0:
                decoded = base64.b64decode(compact, validate=True)
                report["format"] += " + Décodé Base64"
                _scan(decoded, report["protocols"], report["extracted"])
                text_dec = decoded.decode('utf-8', errors='ignore')
                report["raw_text"] = text_dec
                try:
                    parsed_json = json.loads(text_dec)
                    report["raw_text"] = json.dumps(parsed_json, indent=2, ensure_ascii=False)
                except Exception:
                    pass
        except Exception:
            pass
            
        report["notes"].append("Analyse et décryptage complet du fichier terminés.")
    return report


def format_report(result):
    lines = ["🔎 KOSHIBAR — RAPPORT DE DÉCRYPTAGE", "━━━━━━━━━━━━━━━━━━",
             f"📁 Fichier : {result['filename']}", f"📦 Type : {result['type']}",
             f"🔐 SHA256 : {result['sha256'][:16]}...", f"📊 Éléments analysés : {result['scanned']}"]
             
    if result['type'] == 'APK':
        lines.append(f"📂 Fichiers internes ciblés : {len(result['config_files'])}")
    else:
        lines.append(f"🧾 Format : {result['format']}")
        
    lines.append("\n🌐 Protocoles & Méthodes détectés :")
    for key, count in result['protocols'].items():
        if count:
            lines.append(f"• {key} : {count} occurrence(s)")
            
    if not result['protocols'] and not result['extracted']:
        lines.append("Aucune configuration claire trouvée.")
        
    if result['extracted']:
        lines.append("\n🚀 CONFIGURATIONS EXTRAITES :")
        for item in result['extracted'][:8]:
            lines.append(f"<code>{item[:120]}</code>")
            
    lines.extend("\n⚠️ " + note for note in result['notes'])
    return "\n".join(lines)[:3900]
