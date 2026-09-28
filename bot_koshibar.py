import os
import datetime
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# 🔑 Récupération sécurisée depuis les Secrets GitHub
TOKEN = os.getenv("TELEGRAM_TOKEN", "8939179182:AAFSme_jksnnQ1ckjOZfMWXe6rklInFKMLY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8938252970"))

DB_FILE = "koshibar_v2ray.db"

user_sessions = {}

# ==========================================
# 💾 GESTION BASE DE DONNÉES SQLITE
# ==========================================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS v2ray_servers (
            protocol TEXT PRIMARY KEY,
            link TEXT NOT NULL
        )
    """)

    default_servers = [
        ("vless", "vless://f9473da5-9b8c-4e1a-a2c3-d4e5f6a7b8c9@zain.blogblog.com:443?path=%2FKoshibar&security=tls&encryption=none&insecure=0&host=koshibar-xray-382658896650.us-east4.run.app&type=ws&allowInsecure=0&sni=zain.blogblog.com#%E2%9C%A8%20Koshibar-Xray-GCP%20%E2%9C%A8"),
        ("trojan", "trojan://KOSHIBAR@zain.blogblog.com:443?path=%2Fkoshibar-trojan&security=tls&insecure=0&host=koshibar-325871270558.us-west1.run.app&type=ws&allowInsecure=0&sni=zain.blogblog.com#Koshibar❌"),
        ("vmess", "vmess://eyJhZGQiOiJ6YWluLmJsb2dibG9nLmNvbSIsImFpZCI6IjAiLCJhbHBuIjoiIiwiZnAiOiIiLCJob3N0Ijoia29zaGliYXItdm1lc3MtMzgyNjU4ODk2NjUwLnVzLWVhc3Q0LnJ1bi5hcHAiLCJpZCI6IjExMTExMTExLTExMTEtNDExMS04MTExLTExMTExMTExMTExMSIsImluc2VjdXJlIjoiMCIsIm5ldCI6IndzIiwicGF0aCI6Ii9Lb3NoaWJhci9WbWVzcyIsInBjcyI6IiIsInBvcnQiOiI0NDMiLCJwcyI6Imtvc2hpYmFyIFZtZXNzIiwic2N5IjoiY2hhY2hhMjAtcG9seTEzMDUiLCJzbmkiOiJ6YWluLmJsb2dibG9nLmNvbSIsInRscyI6InRscyIsInR5cGUiOiItLS0iLCJ2IjoiMiIsInZjbiI6IiJ9"),
        ("ssh", "💻 KOSHIBAR 9999 CREDITOS 💻\nHost/IP-Address : 169.58.100.47\nUSUARIO : Koshibar\nPASSWD : Koshibar\nDURACION: 21/09/2026\nLIMITE : 2\n━━━━━━━━━━━━━━━━━━━━━\nGET /app10 HTTP/1.1[crlf]Host: [rotate=koshibar-ssh-503433272017.europe-west1.run.app][crlf]Connection: Upgrade[crlf]User-Agent: [ua][crlf]Upgrade: Websocket[crlf][crlf]❌")
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

# ==========================================
# 🤖 BOT TELEGRAM LOGIQUE
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🔥 **BIENVENUE CHEZ KOSHIBAR BOT** 🔥\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Tape /serveur ou clique sur les boutons ci-dessous :"
    )
    keyboard = [
        [InlineKeyboardButton("⚡ Choisir un serveur", callback_data="menu_serveurs")],
        [InlineKeyboardButton("📩 Plus de contact", url="https://t.me/koshibar")]
    ]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def menu_serveurs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        send_func = query.message.reply_text
    else:
        send_func = update.message.reply_text

    msg = (
        "🔥 **KOSHIBAR BOT - CHOIX DU PROTOCOLE** 🔥\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Choisis le protocole que tu veux utiliser :\n\n"
        "🔹 /Vless - Serveur VLESS\n"
        "🔹 /Trojan - Serveur Trojan\n"
        "🔹 /Vmess - Serveur VMESS\n"
        "🔹 /SSH - Serveur SSH + Payload\n\n"
        "📩 /contact - Rejoindre le canal ou contacter d'urgence"
    )
    keyboard = [
        [InlineKeyboardButton("🌐 VLESS", callback_data="get_vless"), InlineKeyboardButton("🛡️ TROJAN", callback_data="get_trojan")],
        [InlineKeyboardButton("⚡ VMESS", callback_data="get_vmess"), InlineKeyboardButton("💻 SSH", callback_data="get_ssh")],
        [InlineKeyboardButton("📩 Plus de contact", url="https://t.me/koshibar")]
    ]
    await send_func(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def contact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📩 **PLUS DE CONTACT / SUPPORT KOSHIBAR** 📩\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Pour toute question, support ou mise à jour, rejoins notre lien Telegram :\n"
        "👉 https://t.me/koshibar"
    )
    keyboard = [[InlineKeyboardButton("💬 Ouvrir Telegram", url="https://t.me/koshibar")]]
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

    now = datetime.datetime.now()

    # --- VERIFICATION LIMITATION 5 HEURES ---
    # Si l'utilisateur n'est PAS l'administrateur, on applique le contrôle de délai
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
                    f"🔥 **KOSHIBAR BOT** 🔥\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"⚠️ **Ton compte {protocole.upper()} est encore actif !**\n\n"
                    f"⏱️ Temps restant : **{heures}h {minutes}min**\n\n"
                    f"Reviens à la fin du compte à rebours pour le renouveler.",
                    parse_mode="Markdown"
                )
                return
        
        # On enregistre le délai de 5h uniquement pour un utilisateur normal
        user_sessions[user_id][protocole] = now + datetime.timedelta(hours=5)

    # Récupération et envoi du serveur
    cle_serveur = get_server_from_db(protocole)

    msg = (
        f"🔥 **KOSHIBAR BOT** 🔥\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🚀 **Voici ton serveur {protocole.upper()} (Valide 5H) :**\n\n"
        f"```\n{cle_serveur}\n```\n\n"
        f"📋 *Clique sur le bloc de texte pour le copier.*"
    )
    await send_func(msg, parse_mode="Markdown")

async def get_vless_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await fournir_protocole(update, context, "vless")

async def get_trojan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await fournir_protocole(update, context, "trojan")

async def get_vmess_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await fournir_protocole(update, context, "vmess")

async def get_ssh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await fournir_protocole(update, context, "ssh")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "menu_serveurs":
        await menu_serveurs(update, context)
    elif query.data in ["get_vless", "get_trojan", "get_vmess", "get_ssh"]:
        proto = query.data.replace("get_", "")
        await fournir_protocole(update, context, proto)

async def set_server(update: Update, context: ContextTypes.DEFAULT_TYPE, protocole: str):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Seul l'administrateur KOSHIBAR peut modifier les serveurs !")
        return

    if not context.args:
        await update.message.reply_text(f"Exemple d'utilisation : `/set{protocole} ton_texte_ici`", parse_mode="Markdown")
        return

    nouveau_contenu = update.message.text.split(f"/set{protocole}", 1)[1].strip()
    update_server_in_db(protocole, nouveau_contenu)
    
    await update.message.reply_text(f"✅ Le serveur **{protocole.upper()}** a été sauvegardé avec succès dans la base SQLite !", parse_mode="Markdown")

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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("serveur", menu_serveurs))
    app.add_handler(CommandHandler("contact", contact_cmd))
    app.add_handler(CommandHandler("plus_de_contact", contact_cmd))
    app.add_handler(CommandHandler("Vless", get_vless_cmd))
    app.add_handler(CommandHandler("Trojan", get_trojan_cmd))
    app.add_handler(CommandHandler("Vmess", get_vmess_cmd))
    app.add_handler(CommandHandler("SSH", get_ssh_cmd))

    app.add_handler(CommandHandler("setvless", set_vless))
    app.add_handler(CommandHandler("settrojan", set_trojan))
    app.add_handler(CommandHandler("setvmess", set_vmess))
    app.add_handler(CommandHandler("setssh", set_ssh))

    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🔥 KOSHIBAR BOT DÉMARRÉ 🔥")
    app.run_polling()
