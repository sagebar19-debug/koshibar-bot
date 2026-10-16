"""KOSHIBAR BOT : serveurs, abonnements, fichiers et analyse VPN."""
import os
import datetime
import sqlite3
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from decrypt_manager import init_decrypt_db, menu as decrypt_menu, callback as decrypt_callback, handle_document as decrypt_document, admin_history, admin_report

TOKEN = os.environ['TELEGRAM_TOKEN']
ADMIN_ID = int(os.environ['ADMIN_ID'])
DB_FILE = 'koshibar_v2ray.db'
WHATSAPP_LINK = 'https://wa.me/243986269802'
TELEGRAM_SUPPORT = 'https://t.me/koshibar'
PROTOCOLS = ('vless', 'trojan', 'vmess', 'ssh')
admin_states = {}


def init_db():
    with sqlite3.connect(DB_FILE) as db:
        db.execute('CREATE TABLE IF NOT EXISTS v2ray_servers (protocol TEXT PRIMARY KEY, link TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS user_subscriptions (user_id INTEGER PRIMARY KEY, expiration_date TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS user_cooldowns (user_id INTEGER, protocol TEXT, next_access_time TEXT, PRIMARY KEY(user_id,protocol))')
        db.execute('CREATE TABLE IF NOT EXISTS uploaded_files (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT NOT NULL, file_name TEXT NOT NULL, description TEXT)')
        for proto in PROTOCOLS:
            db.execute('INSERT OR IGNORE INTO v2ray_servers (protocol,link) VALUES (?,?)', (proto, f'Aucun serveur {proto.upper()} configuré.'))


def check_user_access(uid):
    if uid == ADMIN_ID:
        return True, 'ACCÈS ADMINISTRATEUR ILLIMITÉ'
    with sqlite3.connect(DB_FILE) as db:
        row = db.execute('SELECT expiration_date FROM user_subscriptions WHERE user_id=?', (uid,)).fetchone()
    if not row:
        return False, 'AUCUN ABONNEMENT ACTIF'
    exp = datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
    if datetime.datetime.now() >= exp:
        return False, f'ABONNEMENT EXPIRÉ LE {exp:%d/%m/%Y}'
    return True, f'VALIDE JUSQU’AU {exp:%d/%m/%Y à %H:%M}'


def set_subscription(uid, days):
    if days < 1 or days > 3650:
        raise ValueError('Durée autorisée : 1 à 3650 jours')
    exp = datetime.datetime.now() + datetime.timedelta(days=days)
    with sqlite3.connect(DB_FILE) as db:
        db.execute('INSERT OR REPLACE INTO user_subscriptions VALUES (?,?)', (uid, exp.strftime('%Y-%m-%d %H:%M:%S')))


def cooldown(uid, proto):
    if uid == ADMIN_ID:
        return True, ''
    now = datetime.datetime.now()
    with sqlite3.connect(DB_FILE) as db:
        row = db.execute('SELECT next_access_time FROM user_cooldowns WHERE user_id=? AND protocol=?', (uid, proto)).fetchone()
        if row:
            future = datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
            if now < future:
                minutes = int((future-now).total_seconds() // 60) + 1
                return False, f'{minutes//60}h {minutes%60}min'
        next_time = (now + datetime.timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')
        db.execute('INSERT OR REPLACE INTO user_cooldowns VALUES (?,?,?)', (uid, proto, next_time))
    return True, ''


def main_keyboard(uid):
    buttons = [
        [KeyboardButton('⚡ Menu Serveurs'), KeyboardButton('📁 Fichiers / Configs')],
        [KeyboardButton('🔓 DÉCRYPTAGE VPN')],
        [KeyboardButton('👤 Mon Statut'), KeyboardButton('📩 Contact & Support WhatsApp')]
    ]
    if uid == ADMIN_ID:
        buttons.append([KeyboardButton('👑 Panneau Admin')])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('🔥 BIENVENUE CHEZ KOSHIBAR BOT 🔥\n🚀 Serveurs VPN, SSH, fichiers et analyse APK.\n👇 Choisis une option.', reply_markup=main_keyboard(update.effective_user.id))


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, details = check_user_access(update.effective_user.id)
    await update.effective_message.reply_text(f'👤 MON STATUT\n🆔 ID : {update.effective_user.id}\n{"✅" if ok else "❌"} {details}')


async def servers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, details = check_user_access(update.effective_user.id)
    if not ok:
        await update.effective_message.reply_text(f'⛔ Accès refusé : {details}\n🆔 ID : {update.effective_user.id}\nContact : {WHATSAPP_LINK}')
        return
    buttons = [
        [InlineKeyboardButton('🌐 VLESS', callback_data='get_vless'), InlineKeyboardButton('🛡️ TROJAN', callback_data='get_trojan')],
        [InlineKeyboardButton('⚡ VMESS', callback_data='get_vmess'), InlineKeyboardButton('💻 SSH', callback_data='get_ssh')]
    ]
    await update.effective_message.reply_text('🌐 CHOISIS TON PROTOCOLE', reply_markup=InlineKeyboardMarkup(buttons))


async def send_protocol(update, context, proto):
    ok, details = check_user_access(update.effective_user.id)
    if not ok:
        await update.effective_message.reply_text(f'⛔ {details}')
        return
    with sqlite3.connect(DB_FILE) as db:
        row = db.execute('SELECT link FROM v2ray_servers WHERE protocol=?', (proto,)).fetchone()
    link = row[0] if row else 'Aucun serveur configuré.'
    if link.startswith('Aucun serveur'):
        await update.effective_message.reply_text(link)
        return
    allowed, wait = cooldown(update.effective_user.id, proto)
    if not allowed:
        await update.effective_message.reply_text(f'⏳ {proto.upper()} : réessaie dans {wait}.')
        return
    await update.effective_message.reply_text(f'🚀 SERVEUR {proto.upper()} KOSHIBAR\n\n{link[:3800]}\n\n⏱️ Prochain accès dans 5 heures.')


async def files_menu(update, context):
    ok, details = check_user_access(update.effective_user.id)
    if not ok:
        await update.effective_message.reply_text(f'⛔ {details}')
        return
    with sqlite3.connect(DB_FILE) as db:
        rows = db.execute('SELECT id,file_name FROM uploaded_files ORDER BY id DESC LIMIT 40').fetchall()
    if not rows:
        await update.effective_message.reply_text('📁 Aucun fichier disponible.')
        return
    keys = [[InlineKeyboardButton(f'📄 {name[:45]}', callback_data=f'dl_file_{rid}')] for rid, name in rows]
    await update.effective_message.reply_text('📁 FICHIERS / CONFIGS', reply_markup=InlineKeyboardMarkup(keys))


async def contact(update, context):
    keys = [[InlineKeyboardButton('💬 WhatsApp', url=WHATSAPP_LINK)], [InlineKeyboardButton('📢 Telegram', url=TELEGRAM_SUPPORT)]]
    await update.effective_message.reply_text('📩 SUPPORT KOSHIBAR', reply_markup=InlineKeyboardMarkup(keys))


async def admin_panel(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    keys = [
        [InlineKeyboardButton('🔑 Activer utilisateur', callback_data='admin_grant'), InlineKeyboardButton('🚫 Révoquer accès', callback_data='admin_revoke')],
        [InlineKeyboardButton('📁 Ajouter fichier', callback_data='admin_add_file')],
        [InlineKeyboardButton('🌐 VLESS', callback_data='admin_set_vless'), InlineKeyboardButton('🛡️ TROJAN', callback_data='admin_set_trojan')],
        [InlineKeyboardButton('⚡ VMESS', callback_data='admin_set_vmess'), InlineKeyboardButton('💻 SSH', callback_data='admin_set_ssh')],
        [InlineKeyboardButton('📊 HISTORIQUE DES ANALYSES', callback_data='admin_decrypt_history')]
    ]
    await update.effective_message.reply_text('👑 PANNEAU ADMIN KOSHIBAR', reply_markup=InlineKeyboardMarkup(keys))


async def documents(update, context):
    uid = update.effective_user.id
    if uid == ADMIN_ID and admin_states.get(uid) == 'WAITING_FILE':
        doc = update.message.document
        with sqlite3.connect(DB_FILE) as db:
            db.execute('INSERT INTO uploaded_files (file_id,file_name,description) VALUES (?,?,?)', (doc.file_id, (doc.file_name or 'config')[:200], ''))
        admin_states.pop(uid, None)
        await update.message.reply_text('✅ Fichier ajouté à la liste.')
        return
    if await decrypt_document(update, context, check_user_access, ADMIN_ID):
        return
    await update.message.reply_text('📁 Pour analyser un APK, clique d’abord sur 🔓 DÉCRYPTAGE VPN.')


async def texts(update, context):
    uid = update.effective_user.id
    msg = update.message.text.strip()
    if uid == ADMIN_ID and uid in admin_states:
        state = admin_states[uid]
        try:
            if state == 'WAITING_GRANT':
                parts = msg.split()
                if len(parts) != 2:
                    raise ValueError('Format : ID JOURS')
                target, days = map(int, parts)
                set_subscription(target, days)
                reply = f'✅ Utilisateur {target} activé pour {days} jours.'
            elif state == 'WAITING_REVOKE':
                target = int(msg)
                with sqlite3.connect(DB_FILE) as db:
                    db.execute('DELETE FROM user_subscriptions WHERE user_id=?', (target,))
                    db.execute('DELETE FROM user_cooldowns WHERE user_id=?', (target,))
                reply = f'🚫 Accès révoqué pour {target}.'
            elif state.startswith('WAITING_SET_'):
                proto = state.replace('WAITING_SET_', '').lower()
                if not msg or proto not in PROTOCOLS:
                    raise ValueError('Configuration invalide')
                with sqlite3.connect(DB_FILE) as db:
                    db.execute('INSERT OR REPLACE INTO v2ray_servers VALUES (?,?)', (proto, msg))
                reply = f'✅ Serveur {proto.upper()} mis à jour.'
            else:
                return
        except (ValueError, IndexError) as exc:
            await update.message.reply_text(f'❌ {exc}. Réessaie ou utilise /annuler.')
            return
        admin_states.pop(uid, None)
        await update.message.reply_text(reply)
        return
    if msg == '⚡ Menu Serveurs':
        await servers(update, context)
    elif msg == '📁 Fichiers / Configs':
        await files_menu(update, context)
    elif msg == '🔓 DÉCRYPTAGE VPN':
        await decrypt_menu(update, context, check_user_access)
    elif msg == '👤 Mon Statut':
        await status(update, context)
    elif msg == '📩 Contact & Support WhatsApp':
        await contact(update, context)
    elif msg == '👑 Panneau Admin':
        await admin_panel(update, context)


async def cancel(update, context):
    admin_states.pop(update.effective_user.id, None)
    context.user_data.pop('dec_mode', None)
    await update.effective_message.reply_text('❌ Opération annulée.')


async def callbacks(update, context):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    if data.startswith('dec_history_'):
        await admin_report(update, context, ADMIN_ID)
        return
    if data.startswith('dec_'):
        await decrypt_callback(update, context, check_user_access)
        return
    await query.answer()
    if data == 'admin_decrypt_history':
        await admin_history(update, context, ADMIN_ID)
    elif data == 'menu_serveurs':
        await servers(update, context)
    elif data.startswith('get_') and data[4:] in PROTOCOLS:
        await send_protocol(update, context, data[4:])
    elif data.startswith('dl_file_'):
        ok, details = check_user_access(uid)
        if not ok:
            await query.message.reply_text(f'⛔ {details}')
            return
        try:
            rid = int(data[8:])
        except ValueError:
            return
        with sqlite3.connect(DB_FILE) as db:
            row = db.execute('SELECT file_id,file_name FROM uploaded_files WHERE id=?', (rid,)).fetchone()
        if row:
            await context.bot.send_document(chat_id=uid, document=row[0], caption=f'📄 {row[1][:150]}')
        else:
            await query.message.reply_text('❌ Fichier introuvable.')
    elif uid == ADMIN_ID:
        prompts = {
            'admin_grant': ('WAITING_GRANT', '🔑 Envoie ID JOURS, exemple : 123456789 30'),
            'admin_revoke': ('WAITING_REVOKE', '🚫 Envoie l’ID Telegram à révoquer.'),
            'admin_add_file': ('WAITING_FILE', '📁 Envoie le fichier à ajouter.')
        }
        for proto in PROTOCOLS:
            prompts[f'admin_set_{proto}'] = (f'WAITING_SET_{proto.upper()}', f'📝 Envoie la nouvelle configuration {proto.upper()}.')
        if data in prompts:
            admin_states[uid], prompt = prompts[data]
            await query.message.reply_text(prompt)


def main():
    init_db()
    init_decrypt_db()
    app = ApplicationBuilder().token(TOKEN).build()
    for command, handler in [('start', start), ('serveur', servers), ('fichiers', files_menu), ('contact', contact), ('statut', status), ('admin', admin_panel), ('decrypt', decrypt_menu_command), ('annuler', cancel)]:
        app.add_handler(CommandHandler(command, handler))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.Document.ALL, documents))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, texts))
    print('🔥 KOSHIBAR BOT DÉMARRÉ 🔥')
    
    # Gestion anti-conflit et reconnexion automatique en cas de double instance
    while True:
        try:
            app.run_polling(drop_pending_updates=True)
        except Exception as e:
            print(f"⚠️ Alerte bot : {e}. Nouvelle tentative dans 10 secondes...")
            time.sleep(10)


async def decrypt_menu_command(update, context):
    await decrypt_menu(update, context, check_user_access)


if __name__ == '__main__':
    main()
