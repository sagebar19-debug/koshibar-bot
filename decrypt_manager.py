"""Gestion Telegram des décryptages directs de fichiers VPN."""
import asyncio
import datetime
import os
import sqlite3
import tempfile
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from vpn_analyzer import analyze_file, format_report, MAX_BYTES

DB_FILE = 'koshibar_v2ray.db'

# Liste des formats pris en charge pour l'affichage de bienvenue
SUPPORTED_FORMATS_TEXT = """👋 Welcome to KOSHIBAR DECODEZ 👁

🤖 Add this bot to your grp to help in decryption there! And you can use it personally too!

📂 Supported formats:
[EHI] - .ehi, .ehil
[HC] - .hc
[NPVT] - .npvt, .npvtsub, .npv4
[DARK] - .dark
[SSC] - .ssc
[EV2RAY] - .v2
[HTTP TWEAK] - .ht , httptweak://
[SIP] - .sip
[HAT] - .hat
[NETMOD] - .nm
[OPENTUNNEL] - .tnl
[SLIPNET] - .slipnet
[TLS] - .tls
[LINKLAYER] - .lnk
[MINA] - .mina, .oc
[SANDOK] - Extensions multiples (.aura, .bcl, .dark, etc.)
[RENZ] - .tcx, .7net, .ihome, etc.
[PRINCE] - .apnalite, .bdnet, etc.
[STARK] - .stk
[ZIV] - .ziv
[WYR] - .wyr
[INT] - .int
[EUT] - .eut
[NOOBDEV] - .maya, .roy, .ar

📥 Send your file to decode."""


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


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE, check_access):
    ok, details = check_access(update.effective_user.id)
    if not ok:
        await update.effective_message.reply_text(f'⛔ Accès refusé : {details}\n🆔 ID : {update.effective_user.id}')
        return
    
    # Active directement le mode décryptage global sans demander de choisir une option
    context.user_data['dec_mode'] = 'direct_file'
    
    msg = f"🔓 KOSHIBAR VPN ANALYZER\nFichier autorisé :\n\n{SUPPORTED_FORMATS_TEXT}"
    await update.effective_message.reply_text(msg)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE, check_access):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'dec_cancel':
        context.user_data.pop('dec_mode', None)
        await query.message.reply_text('❌ Opération annulée.')
        return
    ok, details = check_access(query.from_user.id)
    if not ok:
        await query.message.reply_text(f'⛔ Accès refusé : {details}')
        return


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE, check_access, admin_id):
    # Désormais, dès que l'utilisateur clique sur "DÉCRYPTAGE VPN", le mode est actif et il peut envoyer son fichier directement
    ok, details = check_access(update.effective_user.id)
    if not ok:
        await update.message.reply_text(f'⛔ Accès refusé : {details}')
        return True
        
    document = update.message.document
    if not document:
        return False
        
    filename = (document.file_name or 'config.bin')[:120]
    
    if document.file_size is None or document.file_size > 20 * 1024 * 1024:
        await update.message.reply_text('❌ Fichier trop volumineux (limite de 20 Mo de l’API Telegram).')
        return True
        
    status_msg = await update.message.reply_text('⏳ Décryptage et extraction des serveurs en cours…')
    try:
        with tempfile.TemporaryDirectory() as directory:
            ext = os.path.splitext(filename)[1].lower()
            if not ext:
                ext = '.bin'
            path = os.path.join(directory, 'config' + ext)
            
            tgfile = await document.get_file(read_timeout=60, write_timeout=60)
            await tgfile.download_to_drive(custom_path=path, read_timeout=120, write_timeout=120)
            
            # Analyse et décodage complet du fichier VPN
            result = await asyncio.to_thread(analyze_file, path, filename)
            report = format_report(result)
            _record(update.effective_user.id, filename, result['type'], report)
            
            try:
                await status_msg.delete()
            except Exception:
                pass
                
            await update.message.reply_text(report)
            
            if update.effective_user.id != admin_id:
                try:
                    await context.bot.send_message(admin_id, f'🔔 Décodage VPN\n👤 ID : {update.effective_user.id}\n📁 {filename}')
                except Exception:
                    pass
    except Exception as exc:
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f'❌ Erreur lors du décryptage : {type(exc).__name__}')
        return True
        
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
    await update.effective_message.reply_text('👑 HISTORIQUE DES DÉCRYPTAGES', reply_markup=InlineKeyboardMarkup(keys))


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
