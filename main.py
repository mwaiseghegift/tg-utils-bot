
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    ContextTypes, filters, CallbackQueryHandler
)
from telegram.constants import ParseMode
from decouple import config
from utils.FileUploadBot.FileUpload import FileUploadBot
from utils.FileUploadBot.utils import (
    ping_command, help_command, handle_callback, handle_url
)
from utils.constants import (
    MAX_FILE_SIZE
)

BOT_TOKEN = config("API_KEY")

# Messages
CANCEL_MESSAGE = "❌ **Download Cancelled**\n🗑️ Operation stopped by user"

bot_instance = FileUploadBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command with rich welcome message"""
    welcome_text = """
        🚀 **Advanced File Upload Bot**

        📤 **What I can do:**
        • Upload files directly to Telegram from any URL
        • Support for photos, videos, audio, and documents
        • Smart file type detection
        • Real-time progress tracking with download speed
        • Cancel downloads anytime with one click
        • File size validation (up to 2GB)
        • No local storage - files stream directly to Telegram

        📋 **How to use:**
        • Send me any direct file URL
        • I'll analyze it and upload it optimally
        • Use /info <url> to check file details first
        • Use /help for more commands

        💡 **Pro tip:** I work with direct download links, file sharing services, and most public URLs!
    """
    
    keyboard = [
        [InlineKeyboardButton("📖 Help", callback_data="help"),
         InlineKeyboardButton("ℹ️ About", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text.strip(),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get file information without downloading"""
    if not context.args:
        await update.message.reply_text("❌ Please provide a URL after the command.\nExample: `/info https://example.com/file.jpg`", parse_mode=ParseMode.MARKDOWN)
        return
    
    url = context.args[0]
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Please provide a valid URL starting with http:// or https://")
        return
    
    status_msg = await update.message.reply_text("🔍 Analyzing URL...")
    
    info = await bot_instance.check_url_info(url)
    if not info:
        await status_msg.edit_text("❌ Could not analyze the URL. It might be invalid or inaccessible.")
        return
    
    filename = bot_instance.extract_filename_from_url(info['url'])
    file_type = bot_instance.get_file_type(filename, info['content_type'])
    
    info_text = f"""
    📋 **File Information**

    📄 **Name:** `{filename}`
    🗂️ **Type:** {file_type.title()}
    📊 **MIME:** `{info['content_type']}`
    📏 **Size:** {bot_instance.format_file_size(info['size']) if info['size'] else 'Unknown'}
    🌐 **URL:** `{info['url'][:50]}{'...' if len(info['url']) > 50 else ''}`

    {'✅ Ready to upload!' if not info['size'] or info['size'] <= MAX_FILE_SIZE else '❌ File too large (>50MB)'}
    """
    
    keyboard = []
    if not info['size'] or info['size'] <= MAX_FILE_SIZE:
        keyboard.append([InlineKeyboardButton("📤 Upload Now", callback_data=f"upload:{url}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    await status_msg.edit_text(info_text.strip(), parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("info", info_command))
app.add_handler(CommandHandler("ping", ping_command))
app.add_handler(CallbackQueryHandler(handle_callback))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

print("🚀 Advanced File Upload Bot is running...")
print("📤 Features: Smart upload, progress tracking, multiple formats")
print("💾 Zero local storage - all files streamed directly to Telegram")
app.run_polling()
