"""Gestion Telegram des analyses, réservées aux abonnés autorisés."""
import asyncio
import datetime
import os
import sqlite3
import tempfile
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TimedOut, NetworkError, BadRequest
from vpn_analyzer import analyze_file, format_report, MAX_BYTES

DB_FILE = 'koshibar_v2ray.db'


def init_decrypt_db():
    with sqlite3.connect(DB_FILE) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS decrypt_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            report TEXT NOT NULL,
            created_at TEXT NOT NULL
        )''')


def _record(user_id, filename, file_type, report):
    with sqlite3.connect(DB_FILE) as db:
        db.execute('INSERT INTO decrypt_history (user_id,filename,file_type,report,created_at) VALUES (?,?,?,?,?)',
                   (user_id, filename, file_type, report, datetime.datetime.now(datetime.timezone.utc).isoformat()))


def keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📱 Analyser APK', callback_data='dec_apk')],
        [InlineKeyboardButton('📱📁 APK + configuration', callback_data='dec_pair')],
        [InlineKeyboardButton('📜 Mes analyses', callback_data='dec_mine')],
        [InlineKeyboardButton('❌ Annuler', callback_data='dec_cancel')]
    ])


async def menu(update, context, check_access):
    ok, details = check_access(update.effective_user.id)
    if not ok:
        await update.effective_message.reply_text(f'⛔ Accès refusé : {details}\n🆔 ID : {update.effective_user.id}')
        return
    await update.effective_message.reply_text('🔓 KOSHIBAR VPN ANALYZER\nChoisis ton mode :', reply_markup=keyboard())


async def callback(update, context, check_access):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'dec_cancel':
        context.user_data.pop('dec_mode', None)
        await query.message.reply_text('❌ Analyse annulée.')
        return
    ok, details = check_access(query.from_user.id)
    if not ok:
        await query.message.reply_text(f'⛔ Accès refusé : {details}')
        return
    if data == 'dec_apk':
        context.user_data['dec_mode'] = 'apk'
        await query.message.reply_text('📱 Envoie un document .apk (20 Mo maximum).')
    elif data == 'dec_pair':
        context.user_data['dec_mode'] = 'pair_apk'
        await query.message.reply_text('📱 Envoie d’abord le fichier .apk, puis sa configuration.')
    elif data == 'dec_mine':
        with sqlite3.connect(DB_FILE) as db:
            rows = db.execute('SELECT filename,created_at FROM decrypt_history WHERE user_id=? ORDER BY id DESC LIMIT 10',
                              (query.from_user.id,)).fetchall()
        msg = '📜 MES ANALYSES\n\n' + ('\n'.join(f'📁 {name[:70]} — {date[:16]} UTC' for name, date in rows) if rows else 'Aucune analyse.')
        await query.message.reply_text(msg[:3900])


async def handle_document(update, context, check_access, admin_id):
    mode = context.user_data.get('dec_mode')
    if not mode:
        return False
    ok, details = check_access(update.effective_user.id)
    if not ok:
        context.user_data.pop('dec_mode', None)
        await update.message.reply_text(f'⛔ Accès refusé : {details}')
        return True
    document = update.message.document
    filename = (document.file_name or 'fichier.bin')[:120]
    ext = os.path.splitext(filename)[1].lower()
    if mode in ('apk', 'pair_apk') and ext != '.apk':
        await update.message.reply_text('❌ Envoie d’abord un fichier .apk.')
        return True
    if mode == 'pair_config' and ext == '.apk':
        await update.message.reply_text('❌ Envoie maintenant la configuration (pas un APK).')
        return True
    if document.file_size is None or document.file_size > MAX_BYTES:
        await update.message.reply_text('❌ Taille inconnue ou supérieure à 20 Mo.')
        return True
    await update.message.reply_text('⏳ Téléchargement et analyse statique en cours…')
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'input' + ext)
            tgfile = None
            for attempt in range(3):
                try:
                    tgfile = await document.get_file(read_timeout=60, write_timeout=60, connect_timeout=30, pool_timeout=30)
                    await tgfile.download_to_drive(custom_path=path, read_timeout=120, write_timeout=120, connect_timeout=30, pool_timeout=30)
                    break
                except (TimedOut, NetworkError):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 * (attempt + 1))
            result = await asyncio.to_thread(analyze_file, path, filename)
            report = format_report(result)
            _record(update.effective_user.id, filename, result['type'], report)
            await update.message.reply_text(report)
            if update.effective_user.id != admin_id:
                try:
                    await context.bot.send_message(admin_id, f'🔔 Analyse VPN\n👤 ID : {update.effective_user.id}\n📁 {filename}\n📊 Consulte le panneau admin.')
                except Exception:
                    pass
    except BadRequest as exc:
        if 'too big' in str(exc).lower():
            await update.message.reply_text('❌ Telegram refuse le téléchargement de ce fichier : limite de 20 Mo de l’API Bot standard. Un serveur Bot API local ou un lien externe pris en charge est nécessaire pour les gros APK.')
        else:
            await update.message.reply_text('❌ Telegram a refusé ce fichier. Vérifie son format et réessaie.')
        return True
    except (TimedOut, NetworkError):
        await update.message.reply_text('❌ Délai Telegram dépassé après 3 tentatives. Réessaie plus tard ou vérifie la connexion du serveur.')
        return True
    except Exception as exc:
        await update.message.reply_text(f'❌ Analyse impossible : {type(exc).__name__}.')
        return True
    if mode == 'pair_apk':
        context.user_data['dec_mode'] = 'pair_config'
        await update.message.reply_text('✅ APK analysé. Envoie maintenant le fichier de configuration pour une deuxième analyse.')
    else:
        context.user_data.pop('dec_mode', None)
    return True


async def admin_history(update, context, admin_id):
    if update.effective_user.id != admin_id:
        return
    with sqlite3.connect(DB_FILE) as db:
        rows = db.execute('SELECT id,user_id,filename FROM decrypt_history ORDER BY id DESC LIMIT 15').fetchall()
    if not rows:
        await update.effective_message.reply_text('📊 Aucun rapport enregistré.')
        return
    keys = [[InlineKeyboardButton(f'#{rid} • {uid} • {name[:22]}', callback_data=f'dec_history_{rid}')]
            for rid, uid, name in rows]
    await update.effective_message.reply_text('👑 HISTORIQUE DES ANALYSES', reply_markup=InlineKeyboardMarkup(keys))


async def admin_report(update, context, admin_id):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != admin_id:
        return
    try:
        rid = int(query.data.removeprefix('dec_history_'))
    except ValueError:
        return
    with sqlite3.connect(DB_FILE) as db:
        row = db.execute('SELECT user_id,report FROM decrypt_history WHERE id=?', (rid,)).fetchone()
    await query.message.reply_text(f'👤 ID : {row[0]}\n\n{row[1][:3500]}' if row else 'Rapport introuvable.')
