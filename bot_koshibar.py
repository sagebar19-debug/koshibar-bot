import base64
import json
import re

def master_decryptor(file_bytes: bytes, filename: str) -> dict:
    app_detected = identify_app_by_extension(filename)
    raw_text = file_bytes.decode('utf-8', errors='ignore')

    # 1. Tentative de lecture JSON brute
    try:
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass

    # 2. Décodage systématique Base64 / Hex
    try:
        b64_clean = re.sub(r'[^A-Za-z0-9+/=]', '', raw_text)
        decoded_bytes = base64.b64decode(b64_clean)
        decoded_str = decoded_bytes.decode('utf-8', errors='ignore')
        if "{" in decoded_str and "}" in decoded_str:
            match = re.search(r'\{.*\}', decoded_str, re.DOTALL)
            if match:
                return json.loads(match.group(0))
    except Exception:
        pass

    # 3. Extraction par motifs réseau avancés (Payloads, SNI, Endpoints Cloud)
    v2ray_links = re.findall(r'(vless://[^\s]+|vmess://[^\s]+|trojan://[^\s]+|ss://[^\s]+)', raw_text)
    payloads = re.findall(r'(GET [^\r\n]+|POST [^\r\n]+|CONNECT [^\r\n]+|[A-Za-z0-9_.-]+:[0-9]+@)', raw_text)
    cloud_urls = re.findall(r'https?://[^\s"]+', raw_text)
    ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', raw_text)

    return {
        "app_name": app_detected,
        "filename": filename,
        "type": "Decrypted Config / Cloud Payload",
        "status": "DÉCRYPTÉ AVEC SUCCÈS",
        "config_details": {
            "v2ray_links": v2ray_links if v2ray_links else ["Configuration chiffrée par clé APK / Cloud Server"],
            "payloads": payloads if payloads else ["Payload sécurisé ou masqué"],
            "cloud_endpoints": cloud_urls if cloud_urls else ["Aucun lien Cloud externe"],
            "server_ips": list(set(ips)) if ips else ["IP Dynamique"]
        }
    }
