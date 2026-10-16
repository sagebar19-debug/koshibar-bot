"""Analyseur avancé et extracteur de configurations VPN (SSH, V2Ray, DNSTT, Hysteria, etc.)."""
import base64
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024
MAX_ZIP_ENTRIES = 2500
MAX_UNCOMPRESSED = 60 * 1024 * 1024
MAX_ENTRY = 3 * 1024 * 1024

# Motifs élargis pour détecter TOUTES vos méthodes VPN
PATTERNS = {
    "VLESS": rb"vless://[^\s\x00\"'<>]{1,2000}",
    "VMESS": rb"vmess://[^\s\x00\"'<>]{1,2000}",
    "TROJAN": rb"trojan://[^\s\x00\"'<>]{1,2000}",
    "SHADOWSOCKS": rb"ss://[^\s\x00\"'<>]{1,2000}",
    "SSH": rb"(?:ssh://|dropbear|openssh)[^\s\x00\"'<>]{1,500}",
    "DNSTT / SlowDNS": rb"(?:dns|dnstt|ns[0-9]*\.)[^\s\x00\"'<>]{1,2000}",
    "HYSTERIA / UDP": rb"(?:hysteria|quic|udp)://[^\s\x00\"'<>]{1,2000}",
    "PAYLOAD / PROXY": rb"(?:GET|POST|HTTP/1\.[01]|CONNECT)\s+[^\s\x00\"'<>]+",
}

CONFIG_SUFFIXES = (".json", ".xml", ".conf", ".txt", ".yaml", ".yml", ".properties", ".hc", ".npvt", ".dark", ".sip", ".ovpn", ".ssh")


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
                    if len(extracted_configs) < 15:  # Limite pour éviter de saturer le message Telegram
                        extracted_configs.append(decoded_m)
                totals[label] = totals.get(label, 0) + 1
            except Exception:
                pass


def analyze_file(path, display_name=None):
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError("Fichier trop grand (20 Mo maximum).")
    filename = (display_name or Path(path).name)[:120]
    apk = filename.lower().endswith(".apk")
    report = {
        "filename": filename, "type": "APK" if apk else "CONFIG",
        "sha256": _hash_file(path), "scanned": 0, "protocols": {},
        "config_files": [], "format": "inconnu", "notes": [], "extracted": []
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
                # On cible les fichiers de config ou les dossiers assets/raw/databases
                if entry.filename.lower().endswith(CONFIG_SUFFIXES) or 'assets' in entry.filename.lower() or 'raw' in entry.filename.lower() or 'db' in entry.filename.lower():
                    report["config_files"].append(entry.filename[:100])
                try:
                    data = archive.read(entry)
                    _scan(data, report["protocols"], report["extracted"])
                    
                    # Tentative de décodage Base64 interne aux fichiers de l'APK
                    if len(data) > 10:
                        try:
                            compact = b"".join(data.split())
                            if len(compact) % 4 == 0:
                                decoded_b64 = base64.b64decode(compact, validate=True)
                                _scan(decoded_b64, report["protocols"], report["extracted"])
                        except Exception:
                            pass
                except (OSError, RuntimeError, zipfile.BadZipFile):
                    continue
                report["scanned"] += 1
        report["config_files"] = report["config_files"][:20]
        report["notes"].append("Extraction approfondie des moteurs VPN et configurations internes effectuée.")
    else:
        with open(path, "rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        _scan(data, report["protocols"], report["extracted"])
        report["scanned"] = 1
        try:
            text = data.decode("utf-8", errors='ignore')
            json.loads(text)
            report["format"] = "JSON / Config structurée"
        except (UnicodeError, ValueError):
            report["format"] = "Texte, Binaire ou Payload chiffré"
            
        # Tenter un décodage global Base64 si le fichier est une config encodée (.hc ou autre)
        try:
            compact = b"".join(data.split())
            if len(compact) > 10 and len(compact) % 4 == 0:
                decoded = base64.b64decode(compact, validate=True)
                report["format"] += " + Décodé Base64 avec succès"
                _scan(decoded, report["protocols"], report["extracted"])
                text_dec = decoded.decode('utf-8', errors='ignore')
                for line in text_dec.splitlines():
                    if len(line.strip()) > 5 and line.strip() not in report["extracted"]:
                        if len(report["extracted"]) < 15:
                            report["extracted"].append(line.strip())
        except Exception:
            pass
            
        report["notes"].append("Analyse et décryptage du fichier de configuration terminés.")
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
            lines.append(v := f"• {key} : {count} occurrence(s)")
            
    if not result['protocols'] and not result['extracted']:
        lines.append("Aucune configuration claire trouvée (Fichier entièrement protégé ou inconnu).")
        
    if result['extracted']:
        lines.append("\n🚀 CONFIGURATIONS / EXTRAITS DÉCRYPTÉS :")
        for item in result['extracted'][:10]: # Affiche jusqu'à 10 lignes de configuration trouvées
            lines.append(f"<code>{item[:150]}</code>")
            
    lines.extend("\n⚠️ " + note for note in result['notes'])
    return "\n".join(lines)[:3900]
