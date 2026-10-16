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
    
    # Boucle de sécurité anti-conflit robuste
    while True:
        try:
            app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
        except telegram.error.Conflict:
            print("⚠️ Conflit détecté (autre instance active). Attente de 15 secondes...")
            time.sleep(15)
        except Exception as e:
            print(f"⚠️ Erreur inattendue : {e}. Redémarrage dans 10 secondes...")
            time.sleep(10)
