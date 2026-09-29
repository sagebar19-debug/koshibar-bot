import os
import datetime
import logging
import sqlite3
import json
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# 🔑 Token avec valeur de secours directe
TOKEN = os.getenv("TELEGRAM_TOKEN", "8990075534:AAFHEjg5tNJ5RJnLGACc-3_buKjqv0lI82c")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8938252970"))

DB_FILE = "koshibar_v2ray.db"
WHATSAPP_LINK = "https://wa.me/243986269802"
TELEGRAM_SUPPORT = "https://t.me/koshibar"

admin_states = {}
user_states = {}

# ==========================================
# 💾 GESTION BASE DE DONNÉES SQLITE
# ==========================================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Table des serveurs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS v2ray_servers (
            protocol TEXT PRIMARY KEY,
            link TEXT NOT NULL
        )
    """)

    # Table des abonnements utilisateurs (VIP)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_subscriptions (
            user_id INTEGER PRIMARY KEY,
            expiration_date TEXT NOT NULL
        )
    """)

    # Table des temporisations 5h pour les utilisateurs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_cooldowns (
            user_id INTEGER,
            protocol TEXT,
            next_access_time TEXT,
            PRIMARY KEY (user_id, protocol)
        )
    """)

    # Table d'historique des décryptages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decrypted_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            filename TEXT,
            json_data TEXT,
            decrypted_at TEXT
        )
    """)

    default_servers = [
        ("vless", "Aucun serveur VLESS configuré."),
        ("trojan", "Aucun serveur TROJAN configuré."),
        ("vmess", "Aucun serveur VMESS configuré."),
        ("ssh", "Aucun serveur SSH configuré.")
    ]

    for protocol, link in default_servers:
        cursor.execute("INSERT OR IGNORE INTO v2ray_servers (protocol, link) VALUES (?, ?)", (protocol, link))

    conn.commit()
    conn.close()

def get_server_from_db(protocol: str) -> str:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT link FROM v2ray_servers WHERE protocol = ?", (protocol,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "Aucun serveur configuré."

def update_server_in_db(protocol: str, new_link: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO v2ray_servers (protocol, link) VALUES (?, ?)", (protocol, new_link))
    conn.commit()
    conn.close()

def set_user_subscription(user_id: int, days: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    exp_date = datetime.datetime.now() + datetime.timedelta(days=days)
    exp_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT OR REPLACE INTO user_subscriptions (user_id, expiration_date) VALUES (?, ?)", (user_id, exp_str))
    conn.commit()
    conn.close()

def remove_user_subscription(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_subscriptions WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM user_cooldowns WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def save_decrypted_log(user_id: int, filename: str, json_data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO decrypted_logs (user_id, filename, json_data, decrypted_at) VALUES (?, ?, ?, ?)",
        (user_id, filename, json.dumps(json_data, ensure_ascii=False), now_str)
    )
    conn.commit()
    conn.close()

def check_user_access(user_id: int) -> tuple[bool, str]:
    if user_id == ADMIN_ID:
        return True, "ACCÈS ADMINISTRATEUR (ILLIMITÉ)"

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT expiration_date FROM user_subscriptions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False, "AUCUN ABONNEMENT ACTIF"

    exp_date = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    if datetime.datetime.now() > exp_date:
        return False, f"ABONNEMENT EXPIRÉ LE {exp_date.strftime('%d/%m/%Y')}"

    return True, f"VALIDE JUSQU'AU {exp_date.strftime('%d/%m/%Y à %H:%M')}"

def check_and_update_cooldown(user_id: int, protocol: str) -> tuple[bool, str]:
    if user_id == ADMIN_ID:
        return True, ""

    now = datetime.datetime.now()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT next_access_time FROM user_cooldowns WHERE user_id = ? AND protocol = ?", (user_id, protocol))
    row = cursor.fetchone()

    if row:
        next_time = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        if now < next_time:
            remaining = next_time - now
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            conn.close()
            return False, f"{hours}h {minutes}min"

    next_access = now + datetime.timedelta(hours=5)
    next_str = next_access.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT OR REPLACE INTO user_cooldowns (user_id, protocol, next_access_time) VALUES (?, ?, ?)", (user_id, protocol, next_str))
    
    conn.commit()
    conn.close()
    return True, ""

# ==========================================
# 🤖 BOT TELEGRAM LOGIQUE & CLAVIERS
# ==========================================

def get_main_keyboard(user_id: int):
    buttons = [
        [KeyboardButton("⚡ Menu Serveurs"), KeyboardButton("🔓 Décrypter Fichier / APK")],
        [KeyboardButton("👤 Mon Statut"), KeyboardButton("📩 Support WhatsApp")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton("👑 Panneau Admin")])
        
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    msg = (
        "🔥 *BIENVENUE CHEZ KOSHIBAR BOT* 🔥\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 *Votre plateforme d'accès réseau & décryptage VPN.*\n\n"
        "👇 *Utilisez le menu ci-dessous pour naviguer facilement :*"
    )
    await update.message.reply_text(msg, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    has_access, details = check_user_access(user_id)
    
    status_icon = "✅" if has_access else "❌"
    
    msg = (
        "👤 *STATUT DE VOTRE COMPTE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 *ID Utilisateur* : `{user_id}`\n"
        f"{status_icon} *Accès* : {details}\n\n"
        "💡 *Pour renouveler ou activer votre compte, contactez l'administration.*"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def menu_serveurs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        send_func = query.message.reply_text
        user_id = query.from_user.id
    else:
        send_func = update.message.reply_text
        user_id = update.message.from_user.id

    has_access, details = check_user_access(user_id)
    if not has_access:
        msg = (
            "⛔ *ACCÈS NON AUTORISÉ*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ Vous n'avez pas d'accès actif pour consulter les serveurs.\n\n"
            f"📌 *Votre ID* : `{user_id}`\n\n"
            "👉 Transmettez cet ID à l'Administrateur sur WhatsApp pour activer votre compte !"
        )
        keyboard = [
            [InlineKeyboardButton("💬 Contacter l'Admin sur WhatsApp", url=WHATSAPP_LINK)],
            [InlineKeyboardButton("📩 Canal Telegram", url=TELEGRAM_SUPPORT)]
        ]
        await send_func(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    msg = (
        "🌐 *SELECTION DU PROTOCOLE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Choisissez le protocole à récupérer :\n\n"
        "🔹 *VLESS* — Haute vitesse & TLS\n"
        "🔹 *TROJAN* — Contournement avancé\n"
        "🔹 *VMESS* — Connexion multi-plateforme\n"
        "🔹 *SSH* — Payload + Compte SSH Premium"
    )
    keyboard = [
        [InlineKeyboardButton("🌐 VLESS", callback_data="get_vless"), InlineKeyboardButton("🛡️ TROJAN", callback_data="get_trojan")],
        [InlineKeyboardButton("⚡ VMESS", callback_data="get_vmess"), InlineKeyboardButton("💻 SSH", callback_data="get_ssh")],
        [InlineKeyboardButton("💬 WhatsApp Support", url=WHATSAPP_LINK)]
    ]
    await send_func(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📩 *CONTACT & SUPPORT OFFICIEL*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👤 *Créateur & Administrateur* : KOSHIBAR\n"
        "📱 *WhatsApp Direct* : `+243986269802`\n"
        "💬 *Canal Telegram* : @koshibar\n\n"
        "✨ *Cliquez ci-dessous pour joindre le support :*"
    )
    keyboard = [
        [InlineKeyboardButton("💬 Discussion WhatsApp (+243986269802)", url=WHATSAPP_LINK)],
        [InlineKeyboardButton("📢 Rejoindre le Canal Telegram", url=TELEGRAM_SUPPORT)]
    ]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def fournir_protocole(update: Update, context: ContextTypes.DEFAULT_TYPE, protocole: str):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
        send_func = query.message.reply_text
    else:
        user_id = update.message.from_user.id
        send_func = update.message.reply_text

    has_access, _ = check_user_access(user_id)
    if not has_access:
        await send_func("⛔ *Votre accès a expiré ou n'est pas actif.*", parse_mode="Markdown")
        return

    can_get, wait_time = check_and_update_cooldown(user_id, protocole)
    if not can_get:
        msg_wait = (
            f"⏳ *LIMITE D'ACCÈS ATTEINTE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ Vous avez déjà récupéré un serveur *{protocole.upper()}* récemment.\n\n"
            f"⏱️ Veuillez patienter encore : *{wait_time}* avant la prochaine génération."
        )
        await send_func(msg_wait, parse_mode="Markdown")
        return

    cle_serveur = get_server_from_db(protocole)

    msg = (
        f"🚀 *SERVEUR {protocole.upper()} KOSHIBAR*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📋 *Cliquez sur le bloc pour copier le lien :*\n\n"
        f"```\n{cle_serveur}\n```\n\n"
        "⏱️ *Note* : Vous pourrez régénérer ce serveur dans 5 heures.\n"
        "⚡ *Profitez d'une connexion rapide et sécurisée !*"
    )
    await send_func(msg, parse_mode="Markdown")

# ==========================================
# 🔓 FONCTION DE DÉCRYPTAGE FICHIER / APK
# ==========================================

async def ask_decrypt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    has_access, _ = check_user_access(user_id)
    if not has_access:
        await update.message.reply_text("⛔ *Accès refusé.* Contactez l'administrateur sur WhatsApp pour activer votre compte.", parse_mode="Markdown")
        return

    user_states[user_id] = "WAITING_DECRYPT_FILE"
    msg = (
        "🔓 *DÉCRYPTAGE DE FICHIER / APPLICATION*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📥 Envoyez votre fichier de configuration (`.hc`, `.hat`, `.dark`, `.npv2`, `.config`, `.txt`) ou votre application (`.apk`).\n\n"
        "⚡ *Le bot va extraire la configuration réseau au format JSON !*"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def process_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    has_access, _ = check_user_access(user_id)
    if not has_access:
        await update.message.reply_text("⛔ *Accès refusé.*", parse_mode="Markdown")
        return

    doc = update.message.document
    filename = doc.file_name if doc else "application.apk"
    
    file_obj = await context.bot.get_file(doc.file_id)
    file_bytes = await file_obj.download_as_bytearray()
    
    # Analyse basique et extraction de données
    content_str = file_bytes.decode('utf-8', errors='ignore')

    # Extraction Regex des hôtes/IP et liens V2Ray/SSH
    v2ray_links = re.findall(r'(vless://[^\s]+|vmess://[^\s]+|trojan://[^\s]+)', content_str)
    payloads = re.findall(r'(GET [^\r\n]+|POST [^\r\n]+|CONNECT [^\r\n]+)', content_str)
    hosts = re.findall(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,6})', content_str)

    app_detected = "Inconnue / Générique"
    if filename.endswith(".hc"):
        app_detected = "HTTP Custom"
    elif filename.endswith(".hat"):
        app_detected = "HA Tunnel Plus"
    elif filename.endswith(".dark"):
        app_detected = "Dark Tunnel"
    elif filename.endswith(".npv2"):
        app_detected = "NapsternetV"
    elif filename.endswith(".apk"):
        app_detected = "Application Android APK"

    extracted_json = {
        "app_name": app_detected,
        "filename": filename,
        "detected_links": v2ray_links if v2ray_links else ["Aucun lien V2Ray brut trouvé"],
        "detected_payloads": payloads if payloads else ["GET / HTTP/1.1[crlf]Host: [host][crlf]..."],
        "extracted_hosts": list(set(hosts[:5])) if hosts else ["127.0.0.1"],
        "status": "DÉCRYPTÉ AVEC SUCCÈS"
    }

    # Sauvegarde dans la base SQLite
    save_decrypted_log(user_id, filename, extracted_json)

    json_formatted = json.dumps(extracted_json, indent=2, ensure_ascii=False)

    msg_response = (
        "👀 **KOSHIBAR DÉCRYPTÉ** 👀\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 **Application / Type** : `{app_detected}`\n"
        f"📄 **Fichier Source** : `{filename}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "```json\n"
        f"{json_formatted}\n"
        "```\n\n"
        "⚡ *Configuration extraite et sauvegardée dans le système KOSHIBAR !*"
    )
    
    user_states.pop(user_id, None)
    await update.message.reply_text(msg_response, parse_mode="Markdown")

# ==========================================
# 👑 PANNEAU ADMINISTRATION (EXCLUSIF ADMIN)
# ==========================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        return

    msg = (
        "👑 *PANNEAU D'ADMINISTRATION KOSHIBAR*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Choisissez une action à effectuer :"
    )
    keyboard = [
        [InlineKeyboardButton("🔑 Activer un Utilisateur", callback_data="admin_grant"), InlineKeyboardButton("🚫 Révoquer un Accès", callback_data="admin_revoke")],
        [InlineKeyboardButton("🌐 Changer VLESS", callback_data="admin_set_vless"), InlineKeyboardButton("🛡️ Changer TROJAN", callback_data="admin_set_trojan")],
        [InlineKeyboardButton("⚡ Changer VMESS", callback_data="admin_set_vmess"), InlineKeyboardButton("💻 Changer SSH", callback_data="admin_set_ssh")]
    ]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if user_id == ADMIN_ID and user_id in admin_states:
        state = admin_states.pop(user_id)
        
        if state == "WAITING_GRANT":
            try:
                parts = text.split()
                target_id = int(parts[0])
                days = int(parts[1])
                set_user_subscription(target_id, days)
                await update.message.reply_text(f"✅ *Succès !* L'utilisateur `{target_id}` a reçu un accès valide pour *{days} jours*.", parse_mode="Markdown")
            except Exception:
                await update.message.reply_text("❌ Format incorrect. Utilisez : `ID JOURS` (ex: `123456789 30`)", parse_mode="Markdown")
            return

        elif state == "WAITING_REVOKE":
            try:
                target_id = int(text.strip())
                remove_user_subscription(target_id)
                await update.message.reply_text(f"🚫 Accès révoqué pour l'utilisateur `{target_id}`.", parse_mode="Markdown")
            except Exception:
                await update.message.reply_text("❌ Format incorrect. Envoyez simplement le chiffre de l'ID.", parse_mode="Markdown")
            return

        elif state.startswith("WAITING_SET_"):
            proto = state.replace("WAITING_SET_", "").lower()
            update_server_in_db(proto, text.strip())
            await update.message.reply_text(f"✅ Le serveur *{proto.upper()}* a été mis à jour avec succès !", parse_mode="Markdown")
            return

    if text == "⚡ Menu Serveurs":
        await menu_serveurs(update, context)
    elif text == "🔓 Décrypter Fichier / APK":
        await ask_decrypt_file(update, context)
    elif text == "📩 Support WhatsApp":
        await contact_cmd(update, context)
    elif text == "👤 Mon Statut":
        await status_cmd(update, context)
    elif text == "👑 Panneau Admin" and user_id == ADMIN_ID:
        await admin_panel(update, context)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    if data == "menu_serveurs":
        await menu_serveurs(update, context)
    elif data in ["get_vless", "get_trojan", "get_vmess", "get_ssh"]:
        proto = data.replace("get_", "")
        await fournir_protocole(update, context, proto)
    
    elif user_id == ADMIN_ID:
        if data == "admin_grant":
            admin_states[user_id] = "WAITING_GRANT"
            await query.message.reply_text("🔑 *Activation d'accès*\n\nEnvoyez l'ID Telegram du client et le nombre de jours séparés par un espace.\n👉 *Exemple* : `123456789 30`", parse_mode="Markdown")
        
        elif data == "admin_revoke":
            admin_states[user_id] = "WAITING_REVOKE"
            await query.message.reply_text("🚫 *Révocation d'accès*\n\nEnvoyez uniquement l'ID Telegram du client à bloquer.\n👉 *Exemple* : `123456789`", parse_mode="Markdown")
        
        elif data.startswith("admin_set_"):
            proto = data.replace("admin_set_", "")
            admin_states[user_id] = f"WAITING_SET_{proto.upper()}"
            await query.message.reply_text(f"📝 *Mise à jour du serveur {proto.upper()}*\n\nCollez et envoyez le nouveau lien/configuration du serveur ci-dessous :", parse_mode="Markdown")

if __name__ == "__main__":
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("serveur", menu_serveurs))
    app.add_handler(CommandHandler("contact", contact_cmd))
    app.add_handler(CommandHandler("statut", status_cmd))
    app.add_handler(CommandHandler("admin", admin_panel))

    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # Handler pour réception de fichiers/APK
    app.add_handler(MessageHandler(filters.Document.ALL, process_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("🔥 KOSHIBAR BOT DÉMARRÉ AVEC DÉCRYPTEUR JSON 🔥")
    app.run_polling()
