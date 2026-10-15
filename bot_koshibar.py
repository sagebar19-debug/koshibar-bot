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
    
    # Lancement simple sans forcer un timeout de plusieurs heures
    app.run_polling(drop_pending_updates=True)
