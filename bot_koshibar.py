import os
import datetime
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# 🔑 Configuration sécurisée via GitHub Secrets
TOKEN = os.getenv("TELEGRAM_TOKEN", "8939179182:AAFSme_jksnnQ1ckjOZfMWXe6rklInFKMLY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8938252970"))

DB_FILE = "koshibar_v2ray.db"
WHATSAPP_LINK = "https://wa.me/243986269802"
TELEGRAM_SUPPORT = "https://t.me/koshibar"

user_sessions = {}

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

    default_servers = [
        ("vless", "vless://f9473da5-9b8c-4e1a-a2c3-d4e5f6a7b8c9@zain.blogblog.com:443?path=%2FKoshibar&security=tls&encryption=none&insecure=0&host=koshibar-xray-382658896650.us-east4.run.app&type=ws&allowInsecure=0&sni=zain.blogblog.com#%E2%9C%A8%20Koshibar-Xray-GCP%20%E2%9C%A8"),
        ("trojan", "trojan://KOSHIBAR@zain.blogblog.com:443?path=%2Fkoshibar-trojan&security=tls&insecure=0&host=koshibar-325871270558.us-west1.run.app&type=ws&allowInsecure=0&sni=zain.blogblog.com#Koshibar❌"),
        ("vmess", "vmess://eyJhZGQiOiJ6YWluLmJsb2dibG9nLmNvbSIsImFpZCI6IjAiLCJhbHBuIjoiIiwiZnAiOiIiLCJob3N0Ijoia29zaGliYXItdm1lc3MtMzgyNjU4ODk2NjUwLnVzLWVhc3Q0LnJ1bi5hcHAiLCJpZCI6IjExMTExMTExLTExMTEtNDExMS04MTExLTExMTExMTExMTExMSIsImluc2VjdXJlIjoiMCIsIm5ldCI6IndzIiwicGF0aCI6Ii9Lb3NoaWJhci9WbWVzcyIsInBjcyI6IiIsInBvcnQiOiI0NDMiLCJwcyI6Imtvc2hpYmFyIFZtZXNzIiwic2N5IjoiY2hhY2hhMjAtcG9seTEzMDUiLCJzbmkiOiJ6YWluLmJsb2dibG9nLmNvbSIsInRscyI6InRscyIsInR5cGUiOiItLS0iLCJ2IjoiMiIsInZjbiI6IiJ9"),
        ("ssh", "💻 KOSHIBAR 9999 CREDITOS 💻\nHost/IP-Address : 169.58.100.47\nUSUARIO : Koshibar\nPASSWD : Koshibar\nDURACION: 21/09/2026\nLIMITE : 2\n━━━━━━━━━━━━━━━━━━━━━\nGET /app10 HTTP/1.1[crlf]Host: [rotate=koshibar-ssh-503433272017.europe-west1.run.app][crlf]Connection: Upgrade[crlf]User-Agent: [ua][crlf]Upgrade: Websocket[crlf][crlf]❌")
    ]

    for protocol, link in defaultservers:
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

# ==========================================
# 🤖 BOT TELEGRAM LOGIQUE & STYLES
# ==========================================

def get_main_keyboard():
    # Clavier fixe situé en bas de l'application (Reply Keyboard)
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("⚡ Menu Serveurs"), KeyboardButton("👤 Mon Statut")],
            [KeyboardButton("📩 Contact & Support WhatsApp")]
        ],
        resize_keyboard=True
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "╔══════════════════════════════════╗\n"
        "║     🔥  **BIENVENUE CHEZ KOSHIBAR**  🔥    ║\n"
        "╚══════════════════════════════════╝\n\n"
        "🚀 **Votre plateforme d'accès réseau haut débit.**\n\n"
        "👇 *Utilisez le menu ci-dessous pour naviguer facilement dans le bot :*"
    )
    await update.message.reply_text(msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    has_access, details = check_user_access(user_id)
    
    status_icon = "✅" if has_access else "❌"
    
    msg = (
        "╔══════════════════════════════════╗\n"
        "║      👤 **STATUT DU COMPTE KOSHIBAR**     ║\n"
        "╚══════════════════════════════════╝\n\n"
        f"🆔 **ID Utilisateur** : `{user_id}`\n"
        f"{status_icon} **Accès** : {details}\n\n"
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
            "╔══════════════════════════════════╗\n"
            "║        ⛔ **ACCÈS NON AUTORISÉ**        ║\n"
            "╚══════════════════════════════════╝\n\n"
            "⚠️ Vous n'avez pas d'accès actif pour consulter les serveurs.\n\n"
            f"📌 **Votre ID** : `{user_id}`\n"
            "👉 Transmettez cet ID à l'Administrateur sur WhatsApp pour activer votre accès !"
        )
        keyboard = [
            [InlineKeyboardButton("💬 Contacter l'Admin sur WhatsApp", url=WHATSAPP_LINK)],
            [InlineKeyboardButton("📩 Canal Telegram", url=TELEGRAM_SUPPORT)]
        ]
        await send_func(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    msg = (
        "╔══════════════════════════════════╗\n"
        "║   🌐 **KOSHIBAR - SÉLECTION PROTOCOLE**   ║\n"
        "╚══════════════════════════════════╝\n\n"
        "Choisissez le protocole réseau à télécharger :\n\n"
        "🔹 **VLESS** — Haute vitesse & TLS\n"
        "🔹 **TROJAN** — Contournement avancé\n"
        "🔹 **VMESS** — Connexion multi-plateforme\n"
        "🔹 **SSH** — Payload + Compte SSH Premium"
    )
    keyboard = [
        [InlineKeyboardButton("🌐 VLESS", callback_data="get_vless"), InlineKeyboardButton("🛡️ TROJAN", callback_data="get_trojan")],
        [InlineKeyboardButton("⚡ VMESS", callback_data="get_vmess"), InlineKeyboardButton("💻 SSH", callback_data="get_ssh")],
        [InlineKeyboardButton("💬 WhatsApp Support", url=WHATSAPP_LINK)]
    ]
    await send_func(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "╔══════════════════════════════════╗\n"
        "║    📩 **CONTACT & SUPPORT OFFICIEL**     ║\n"
        "╚══════════════════════════════════╝\n\n"
        "👤 **Créateur & Administrateur** : KOSHIBAR\n"
        "📱 **WhatsApp Direct** : `+243986269802`\n"
        "💬 **Canal Telegram** : @koshibar\n\n"
        "✨ *Cliquez sur les boutons ci-dessous pour joindre l'administration directement :*"
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
        await send_func("⛔ **Votre accès a expiré ou n'est pas actif.**", parse_mode="Markdown")
        return

    now = datetime.datetime.now()

    # --- VERIFICATION LIMITATION 5 HEURES (SEULEMENT POUR UTILISATEUR NORMAL) ---
    if user_id != ADMIN_ID:
        if user_id not in user_sessions:
            user_sessions[user_id] = {}

        if protocole in user_sessions[user_id]:
            expiration = user_sessions[user_id][protocole]
            if now < expiration:
                temps_restant = expiration - now
                heures, reste = divmod(temps_restant.seconds, 3600)
                minutes, _ = divmod(reste, 60)
                
                await send_func(
                    f"⚠️ **Compte encore actif !**\n\n"
                    f"⏱️ Prochaine génération disponible dans : **{heures}h {minutes}min**",
                    parse_mode="Markdown"
                )
                return
        
        user_sessions[user_id][protocole] = now + datetime.timedelta(hours=5)

    cle_serveur = get_server_from_db(protocole)

    msg = (
        "╔══════════════════════════════════╗\n"
        f"║   🚀 **SERVEUR {protocole.upper()} KOSHIBAR**   ║\n"
        "╚══════════════════════════════════╝\n\n"
        "📋 *Cliquez sur le bloc pour copier le lien :*\n\n"
        f"```\n{cle_serveur}\n```\n\n"
        "⚡ *Profitez d'une connexion rapide et sécurisée !*"
    )
    await send_func(msg, parse_mode="Markdown")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "⚡ Menu Serveurs":
        await menu_serveurs(update, context)
    elif text == "📩 Contact & Support WhatsApp":
        await contact_cmd(update, context)
    elif text == "👤 Mon Statut":
        await status_cmd(update, context)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "menu_serveurs":
        await menu_serveurs(update, context)
    elif query.data in ["get_vless", "get_trojan", "get_vmess", "get_ssh"]:
        proto = query.data.replace("get_", "")
        await fournir_protocole(update, context, proto)

# ==========================================
# 👑 COMMANDES ADMINISTRATEUR EXCLUSIVES
# ==========================================

async def grant_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text("💡 **Usage** : `/grant <ID_TELEGRAM> <JOURS>`\nExemple : `/grant 123456789 30`", parse_mode="Markdown")
        return

    try:
        target_id = int(context.args[0])
        days = int(context.args[1])
        set_user_subscription(target_id, days)
        await update.message.reply_text(f"✅ **Succès !** L'utilisateur `{target_id}` a reçu un accès valide pour **{days} jours**.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ L'ID et le nombre de jours doivent être des chiffres.", parse_mode="Markdown")

async def revoke_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("💡 **Usage** : `/revoke <ID_TELEGRAM>`", parse_mode="Markdown")
        return

    try:
        target_id = int(context.args[0])
        remove_user_subscription(target_id)
        await update.message.reply_text(f"🚫 Accès révoqué pour l'utilisateur `{target_id}`.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ L'ID doit être un chiffre.", parse_mode="Markdown")

async def set_server(update: Update, context: ContextTypes.DEFAULT_TYPE, protocole: str):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Seul l'administrateur KOSHIBAR peut modifier les serveurs !")
        return

    if not context.args:
        await update.message.reply_text(f"Exemple : `/set{protocole} votre_serveur_ici`", parse_mode="Markdown")
        return

    nouveau_contenu = update.message.text.split(f"/set{protocole}", 1)[1].strip()
    update_server_in_db(protocole, nouveau_contenu)
    await update.message.reply_text(f"✅ Le serveur **{protocole.upper()}** a été mis à jour avec succès !", parse_mode="Markdown")

async def set_vless(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_server(update, context, "vless")

async def set_trojan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_server(update, context, "trojan")

async def set_vmess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_server(update, context, "vmess")

async def set_ssh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_server(update, context, "ssh")

if __name__ == "__main__":
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers généraux
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("serveur", menu_serveurs))
    app.add_handler(CommandHandler("contact", contact_cmd))
    app.add_handler(CommandHandler("statut", status_cmd))

    # Commandes Admin pour modifier les serveurs
    app.add_handler(CommandHandler("setvless", set_vless))
    app.add_handler(CommandHandler("settrojan", set_trojan))
    app.add_handler(CommandHandler("setvmess", set_vmess))
    app.add_handler(CommandHandler("setssh", set_ssh))

    # Commandes Admin pour gérer les abonnements des utilisateurs
    app.add_handler(CommandHandler("grant", grant_user))
    app.add_handler(CommandHandler("revoke", revoke_user))

    # Gestionnaires de callbacks et boutons texte
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(CommandHandler("Vless", get_vless_cmd if 'get_vless_cmd' in locals() else start))
    app.add_handler(CommandHandler("Trojan", get_trojan_cmd if 'get_trojan_cmd' in locals() else start))
    app.add_handler(CommandHandler("Vmess", get_vmess_cmd if 'get_vmess_cmd' in locals() else start))
    app.add_handler(CommandHandler("SSH", get_ssh_cmd if 'get_ssh_cmd' in locals() else start))

    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("🔥 KOSHIBAR BOT DÉMARRÉ AVEC LE NOUVEAU DESIGN 🔥")
    app.run_polling()
