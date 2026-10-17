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
        await update.message.reply_text('❌ Envoie d’abord un fichier .apk valide.')
        return True
    if mode == 'pair_config' and ext == '.apk':
        await update.message.reply_text('❌ Envoie maintenant la configuration (pas un APK).')
        return True
        
    # Limitation officielle de l'API Telegram Bot à 20 Mo pour le téléchargement direct
    if document.file_size is None or document.file_size > 20 * 1024 * 1024:
        await update.message.reply_text('❌ Désolé mon frère, Telegram bloque le téléchargement des fichiers de plus de 20 Mo par les bots. Envoie un APK plus petit (moins de 20 Mo).')
        return True
        
    status_msg = await update.message.reply_text('⏳ Téléchargement et décryptage en cours… (Patientez)')
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'input' + ext)
            tgfile = await document.get_file()
            
            await tgfile.download_to_drive(custom_path=path, read_timeout=120, write_timeout=120)
            
            result = await asyncio.to_thread(analyze_file, path, filename)
            report = format_report(result)
            _record(update.effective_user.id, filename, result['type'], report)
            
            try:
                await status_msg.delete()
            except Exception:
                pass
                
            await update.message.reply_text(report)
    except Exception as exc:
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f'❌ Erreur de décryptage : {type(exc).__name__}')
        return True
        
    if mode == 'pair_apk':
        context.user_data['dec_mode'] = 'pair_config'
        await update.message.reply_text('✅ APK analysé. Envoie maintenant le fichier de configuration.')
    else:
        context.user_data.pop('dec_mode', None)
    return True
