"""Réception des fichiers VPN, accès par abonnement et historique admin."""
import asyncio
import datetime
import os
import sqlite3
import tempfile
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, TimedOut, NetworkError
from vpn_analyzer import analyze_file, format_report, EXTENSIONS, FORMAT_LIST, MAX_BYTES

DB_FILE = 'koshibar_v2ray.db'
WELCOME = ('🔓 KOSHIBAR VPN ANALYZER\n\n'
           '👋 Welcome to KOSHIBAR DECODEZ 👁\n\n'
           '🤖 Utilisable en privé ou dans un groupe.\n'
           '📂 Supported formats:\n' + FORMAT_LIST +
           '\n\n📥 Send your file to decode.\n'
           '⚠️ Analyse des données accessibles ; le déchiffrement propriétaire n’est pas garanti.')


def init_decrypt_db():
    with sqlite3.connect(DB_FILE) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS decrypt_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            report TEXT NOT NULL,
            created_at TEXT NOT NULL)''')


def _record(uid, name, extension, report):
    with sqlite3.connect(DB_FILE) as db:
        db.execute('INSERT INTO decrypt_history (user_id,filename,file_type,report,created_at) VALUES (?,?,?,?,?)',
                   (uid, name, extension, report, datetime.datetime.now(datetime.timezone.utc).isoformat()))


async def menu(update, context, check_access):
    ok, details = check_access(update.effective_user.id)
    if not ok:
        await update.effective_message.reply_text(f'⛔ Accès refusé : {details}\n🆔 ID : {update.effective_user.id}')
        return
    context.user_data['dec_mode'] = 'config'
    await update.effective_message.reply_text(WELCOME, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('📜 Mes analyses', callback_data='dec_mine')],
        [InlineKeyboardButton('❌ Annuler', callback_data='dec_cancel')]]))


async def callback(update, context, check_access):
    query = update.callback_query
    await query.answer()
    if query.data == 'dec_cancel':
        context.user_data.pop('dec_mode', None)
        await query.message.reply_text('❌ Analyse annulée.')
        return
    ok, details = check_access(query.from_user.id)
    if not ok:
        await query.message.reply_text(f'⛔ {details}')
        return
    if query.data == 'dec_mine':
        with sqlite3.connect(DB_FILE) as db:
            rows = db.execute('SELECT filename,created_at FROM decrypt_history WHERE user_id=? ORDER BY id DESC LIMIT 10',
                              (query.from_user.id,)).fetchall()
        await query.message.reply_text('📜 MES ANALYSES\n' + ('\n'.join(f'📁 {name[:65]} — {date[:16]} UTC' for name,date in rows) if rows else 'Aucune analyse.'))


async def handle_document(update, context, check_access, admin_id):
    doc = update.message.document
    name = (doc.file_name or 'inconnu')[:120]
    ext = os.path.splitext(name)[1].lower()
    if ext not in EXTENSIONS:
        if context.user_data.get('dec_mode'):
            await update.message.reply_text('❌ Format non autorisé. Envoie un fichier de la liste affichée.')
            return True
        return False
    ok, details = check_access(update.effective_user.id)
    if not ok:
        await update.message.reply_text(f'⛔ Accès refusé : {details}\n🆔 {update.effective_user.id}')
        return True
    if doc.file_size is None or doc.file_size > MAX_BYTES:
        await update.message.reply_text('❌ Taille trop grande ou inconnue. Limite de téléchargement Bot API standard : 20 Mo. Essaie un fichier plus petit.')
        return True
    await update.message.reply_text('🔍 Analyse du fichier VPN en cours…')
    try:
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'config' + ext)
            for attempt in range(3):
                try:
                    tgfile = await doc.get_file(read_timeout=90, connect_timeout=30)
                    await tgfile.download_to_drive(custom_path=path, read_timeout=120, connect_timeout=30)
                    break
                except (TimedOut, NetworkError):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 * (attempt + 1))
            result = await asyncio.to_thread(analyze_file, path)
        report = format_report(result)
        _record(update.effective_user.id, name, ext, report)
        await update.message.reply_text(f'📄 {name}\n\n{report}'[:4000])
        if update.effective_user.id != admin_id:
            try:
                await context.bot.send_message(admin_id, f'🔔 Analyse VPN\n🆔 Utilisateur : {update.effective_user.id}\n📁 {name}\n📊 Historique disponible dans le panneau admin.')
            except (BadRequest, TimedOut, NetworkError):
                pass
    except BadRequest as exc:
        await update.message.reply_text('❌ Telegram refuse le fichier (taille ou téléchargement). ' + str(exc)[:100])
    except (TimedOut, NetworkError):
        await update.message.reply_text('❌ Téléchargement expiré après 3 essais. Réessaie dans quelques instants.')
    except (ValueError, OSError) as exc:
        await update.message.reply_text(f'❌ Analyse impossible : {str(exc)[:180]}')
    return True


async def admin_history(update, context, admin_id):
    if update.effective_user.id != admin_id:
        return
    with sqlite3.connect(DB_FILE) as db:
        rows = db.execute('SELECT id,user_id,filename FROM decrypt_history ORDER BY id DESC LIMIT 15').fetchall()
    if not rows:
        await update.effective_message.reply_text('📊 Aucun historique.')
        return
    keys = [[InlineKeyboardButton(f'#{rid} | {uid} | {name[:25]}', callback_data=f'dec_history_{rid}')]
            for rid,uid,name in rows]
    await update.effective_message.reply_text('👑 HISTORIQUE DES ANALYSES', reply_markup=InlineKeyboardMarkup(keys))


async def admin_report(update, context, admin_id):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != admin_id:
        return
    try:
        rid = int(query.data.rsplit('_', 1)[1])
    except ValueError:
        return
    with sqlite3.connect(DB_FILE) as db:
        row = db.execute('SELECT user_id,filename,report FROM decrypt_history WHERE id=?', (rid,)).fetchone()
    if row:
        await query.message.reply_text(f'👑 Utilisateur : {row[0]}\n📁 {row[1]}\n\n{row[2]}'[:4000])
