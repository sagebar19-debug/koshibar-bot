"""Analyse statique et prudente des APK et configurations VPN (sans exécution)."""
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
PATTERNS = {
    "VLESS": rb"vless://[^\s\x00\"'<>]{1,2000}",
    "VMESS": rb"vmess://[^\s\x00\"'<>]{1,2000}",
    "TROJAN": rb"trojan://[^\s\x00\"'<>]{1,2000}",
    "SHADOWSOCKS": rb"ss://[^\s\x00\"'<>]{1,2000}",
    "SSH": rb"ssh://[^\s\x00\"'<>]{1,2000}",
}
CONFIG_SUFFIXES = (".json", ".xml", ".conf", ".txt", ".yaml", ".yml", ".properties", ".hc", ".npvt", ".dark")


def _hash_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan(data, totals):
    for label, pattern in PATTERNS.items():
        matches = re.findall(pattern, data, flags=re.IGNORECASE)
        totals[label] = totals.get(label, 0) + len(set(matches))


def analyze_file(path, display_name=None):
    """Ne renvoie jamais de secrets en clair, seulement des comptes et métadonnées."""
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError("Fichier trop grand (20 Mo maximum).")
    filename = (display_name or Path(path).name)[:120]
    apk = filename.lower().endswith(".apk")
    report = {
        "filename": filename, "type": "APK" if apk else "CONFIG",
        "sha256": _hash_file(path), "scanned": 0, "protocols": {},
        "config_files": [], "format": "inconnu", "notes": []
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
                if entry.filename.lower().endswith(CONFIG_SUFFIXES):
                    report["config_files"].append(entry.filename[:100])
                # On ne décompresse que les petites entrées, avec un plafond global.
                try:
                    data = archive.read(entry)
                except (OSError, RuntimeError, zipfile.BadZipFile):
                    continue
                _scan(data, report["protocols"])
                report["scanned"] += 1
        report["config_files"] = report["config_files"][:20]
        report["notes"].append("Analyse statique : pas d'exécution ni de déchiffrement des ressources protégées.")
    else:
        with open(path, "rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        _scan(data, report["protocols"])
        report["scanned"] = 1
        try:
            text = data.decode("utf-8")
            json.loads(text)
            report["format"] = "JSON"
        except (UnicodeError, ValueError):
            report["format"] = "texte ou binaire"
        compact = b"".join(data.split())
        if 16 < len(compact) < 2_000_000 and len(compact) % 4 == 0:
            try:
                decoded = base64.b64decode(compact, validate=True)
                report["format"] += " / Base64 possible"
                _scan(decoded, report["protocols"])
            except (ValueError, base64.binascii.Error):
                pass
        report["notes"].append("Un format propriétaire chiffré nécessite sa clé et un décodeur compatible.")
    return report


def format_report(result):
    lines = ["🔎 KOSHIBAR — RAPPORT D'ANALYSE", "━━━━━━━━━━━━━━━━━━",
             f"📁 Fichier : {result['filename']}", f"📦 Type : {result['type']}",
             f"🔐 SHA256 : {result['sha256']}", f"📊 Éléments analysés : {result['scanned']}"]
    if result['type'] == 'APK':
        lines.append(f"📂 Fichiers config repérés : {len(result['config_files'])}")
        lines.extend("• " + name for name in result['config_files'][:10])
    else:
        lines.append(f"🧾 Format : {result['format']}")
    lines.append("\n🌐 Liens VPN visibles (nombre) :")
    lines.extend(f"• {key} : {count}" for key, count in result['protocols'].items() if count)
    if not result['protocols']:
        lines.append("Aucun lien VPN reconnu en clair.")
    lines.extend("⚠️ " + note for note in result['notes'])
    lines.append("\nLes mots de passe et liens complets ne sont pas affichés.")
    return "\n".join(lines)[:3900]
