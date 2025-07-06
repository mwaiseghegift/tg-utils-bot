import asyncio
import io
import re
import time
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    ContextTypes, filters, CallbackQueryHandler
)
from telegram.constants import ParseMode, ChatAction
import httpx
from decouple import config
from utils.FileUploadBot.FileUpload import FileUploadBot
from utils.utils import logger

BOT_TOKEN = config("API_KEY")

# File size limits (in bytes)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB for Telegram
MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10MB for photos

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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information"""
    help_text = """
    📚 **Available Commands:**

    🔸 `/start` - Show welcome message
    🔸 `/help` - Show this help
    🔸 `/info <url>` - Get file information without downloading
    🔸 `/ping` - Check bot status

    📤 **Supported File Types:**
    • **Photos:** JPG, PNG, GIF, WebP, BMP, TIFF
    • **Videos:** MP4, AVI, MOV, MKV, WebM, M4V
    • **Audio:** MP3, WAV, FLAC, OGG, AAC, M4A
    • **Documents:** Any other file type

    ⚠️ **Limitations:**
    • Maximum file size: 2GB
    • Photos: Up to 10MB for best quality
    • Files are streamed directly (no local storage)
    • Progress updates every 2 seconds

    🌐 **Supported URLs:**
    • Direct download links
    • Most file sharing services
    • Public cloud storage links
    • CDN hosted files
    """
    
    await update.message.reply_text(help_text.strip(), parse_mode=ParseMode.MARKDOWN)

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

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check bot status"""
    start_time = time.time()
    msg = await update.message.reply_text("🏓 Pong!")
    end_time = time.time()
    
    response_time = (end_time - start_time) * 1000
    await msg.edit_text(f"🏓 Pong!\n⚡ Response time: {response_time:.0f}ms")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle URL messages with advanced processing"""
    url = update.message.text.strip()
    
    # Validate URL
    if not re.match(r'https?://.+', url):
        await update.message.reply_text("❌ Please send a valid URL starting with http:// or https://")
        return
    
    user_id = update.effective_user.id
    
    # Check if user has active download
    if user_id in bot_instance.active_downloads:
        await update.message.reply_text("⏳ You already have an active download. Please wait for it to complete.")
        return
    
    # Send initial status
    status_msg = await update.message.reply_text("🔍 Analyzing file...")
    bot_instance.active_downloads[user_id] = True
    
    try:
        # Check file info
        info = await bot_instance.check_url_info(url)
        if not info:
            await status_msg.edit_text("❌ Could not access the file. Please check the URL and try again.")
            return
        
        filename = bot_instance.extract_filename_from_url(info['url'])
        file_type = bot_instance.get_file_type(filename, info['content_type'])
        
        # Check file size
        if info['size'] and info['size'] > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"❌ File is too large ({bot_instance.format_file_size(info['size'])})\n"
                f"Maximum allowed: {bot_instance.format_file_size(MAX_FILE_SIZE)}"
            )
            return
        
        # Update status with file info and cancel button
        cancel_keyboard = [[InlineKeyboardButton("❌ Cancel Download", callback_data=f"cancel:{user_id}")]]
        cancel_markup = InlineKeyboardMarkup(cancel_keyboard)
        
        await status_msg.edit_text(
            f"📤 Uploading {file_type}...\n"
            f"📄 {filename}\n"
            f"📏 {bot_instance.format_file_size(info['size']) if info['size'] else 'Unknown size'}",
            reply_markup=cancel_markup
        )
        
        # Send typing action
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT)
        
        # Download and upload file with progress
        await download_with_progress(info['url'], info, filename, file_type, status_msg, update, context, user_id)
    
    except asyncio.TimeoutError:
        await status_msg.edit_text("❌ Upload timeout. The file might be too large or the server is slow.")
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await status_msg.edit_text(f"❌ Upload failed: {str(e)}")
    
    finally:
        # Clean up
        if user_id in bot_instance.active_downloads:
            del bot_instance.active_downloads[user_id]
        # Remove any pending cancel requests
        bot_instance.cancel_requests.discard(user_id)

async def download_with_progress(url, info, filename, file_type, status_msg, update, context, user_id):
    """Download file with progress tracking and cancel support"""
    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream('GET', url) as response:
            if response.status_code != 200:
                await status_msg.edit_text(f"❌ Failed to download file (HTTP {response.status_code})")
                return
            
            file_data = io.BytesIO()
            downloaded = 0
            total_size = info.get('size', 0)
            last_update_time = time.time()
            start_time = time.time()
            
            # Create cancel button
            cancel_keyboard = [[InlineKeyboardButton("❌ Cancel Download", callback_data=f"cancel:{user_id}")]]
            cancel_markup = InlineKeyboardMarkup(cancel_keyboard)
            
            async for chunk in response.aiter_bytes(chunk_size=8192):
                # Check for cancellation first (before processing chunk)
                if user_id in bot_instance.cancel_requests:
                    logger.info(f"Cancellation detected for user {user_id} during download")
                    await status_msg.edit_text(CANCEL_MESSAGE, parse_mode=ParseMode.MARKDOWN)
                    bot_instance.cancel_requests.discard(user_id)
                    return
                
                file_data.write(chunk)
                downloaded += len(chunk)
                
                # Check for cancellation again after writing chunk
                if user_id in bot_instance.cancel_requests:
                    logger.info(f"Cancellation detected for user {user_id} after chunk write")
                    await status_msg.edit_text(CANCEL_MESSAGE, parse_mode=ParseMode.MARKDOWN)
                    bot_instance.cancel_requests.discard(user_id)
                    return
                
                # Update progress every 2 seconds or when download completes
                current_time = time.time()
                if current_time - last_update_time >= 2.0 or downloaded == total_size:
                    last_update_time = current_time
                    
                    if total_size > 0:
                        percentage = (downloaded / total_size) * 100
                        progress_bar = bot_instance.create_progress_bar(percentage)
                        speed = downloaded / (current_time - start_time) if current_time > start_time else 0
                        eta = (total_size - downloaded) / speed if speed > 0 else 0
                        
                        status_text = f"""📤 **Downloading {file_type}...**

                        📄 `{filename}`
                        📏 {bot_instance.format_file_size(downloaded)} / {bot_instance.format_file_size(total_size)}
                        {progress_bar}
                        ⚡ Speed: {bot_instance.format_file_size(speed)}/s
                        ⏱️ ETA: {int(eta)}s remaining"""
                    else:
                        # Unknown size
                        speed = downloaded / (current_time - start_time) if current_time > start_time else 0
                        status_text = f"""📤 **Downloading {file_type}...**

                        📄 `{filename}`
                        📏 {bot_instance.format_file_size(downloaded)} downloaded
                        ⚡ Speed: {bot_instance.format_file_size(speed)}/s
                        📡 Size unknown - streaming..."""
                    
                    try:
                        await status_msg.edit_text(status_text.strip(), parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_markup)
                    except Exception:
                        # Ignore edit errors (rate limiting, etc.)
                        pass
            
            # Check for cancellation before upload
            if user_id in bot_instance.cancel_requests:
                await status_msg.edit_text(CANCEL_MESSAGE, parse_mode=ParseMode.MARKDOWN)
                bot_instance.cancel_requests.discard(user_id)
                return
            
            # Upload phase
            await status_msg.edit_text("📤 **Uploading to Telegram...**\n⚡ Processing file...")
            
            file_data.seek(0)
            input_file = InputFile(file_data, filename=filename)
            
            # Upload based on file type
            caption = f"📄 {filename}\n📏 {bot_instance.format_file_size(len(file_data.getvalue()))}\n🕐 {datetime.now().strftime('%H:%M:%S')}"
            
            if file_type == 'photo' and len(file_data.getvalue()) <= MAX_PHOTO_SIZE:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=input_file,
                    caption=caption,
                    reply_to_message_id=update.message.message_id
                )
            elif file_type == 'video':
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=input_file,
                    caption=caption,
                    reply_to_message_id=update.message.message_id
                )
            elif file_type == 'audio':
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id,
                    audio=input_file,
                    caption=caption,
                    reply_to_message_id=update.message.message_id
                )
            else:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=input_file,
                    caption=caption,
                    reply_to_message_id=update.message.message_id
                )
            
            # Delete status message and send success
            await status_msg.delete()
            
            total_time = time.time() - start_time
            await update.message.reply_text(
                f"✅ **Upload Complete!**\n"
                f"📁 File type: {file_type.title()}\n"
                f"📏 Size: {bot_instance.format_file_size(len(file_data.getvalue()))}\n"
                f"⏱️ Total time: {int(total_time)}s\n"
                f"⚡ Avg speed: {bot_instance.format_file_size(len(file_data.getvalue()) / total_time)}/s"
            )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "help":
        await help_command(update, context)
    elif query.data == "about":
        about_text = """
🤖 **Advanced File Upload Bot**

    **Version:** 2.0
    **Developer:** Custom Bot
    **Features:** 
    • Zero local storage
    • Smart file type detection
    • Real-time progress tracking
    • Cancel downloads anytime
    • Error handling
    • Multiple format support

    **Tech Stack:**
    • Python 3.8+
    • python-telegram-bot
    • httpx for async HTTP
    • In-memory file processing
        """
        await query.edit_message_text(about_text.strip(), parse_mode=ParseMode.MARKDOWN)
    elif query.data.startswith("upload:"):
        url = query.data[7:]  # Remove "upload:" prefix
        # Simulate URL message for upload
        update.message = query.message
        update.message.text = url
        await handle_url(update, context)
    elif query.data.startswith("cancel:"):
        user_id = int(query.data[7:])  # Remove "cancel:" prefix
        logger.info(f"Cancel request received for user {user_id} by user {query.from_user.id}")
        
        # Check if this user is requesting cancellation
        if query.from_user.id == user_id:
            # Add to cancel requests immediately
            bot_instance.cancel_requests.add(user_id)
            logger.info(f"Added user {user_id} to cancel requests")
            
            # Provide immediate feedback
            await query.edit_message_text(
                "⏹️ **Cancelling Download...**\n"
                "⏳ Stopping operation, please wait...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Also show alert for immediate feedback
            await query.answer("🛑 Download cancellation requested!", show_alert=False)
            
            # Clean up active download status
            if user_id in bot_instance.active_downloads:
                del bot_instance.active_downloads[user_id]
                logger.info(f"Removed user {user_id} from active downloads")
        else:
            await query.answer("❌ You can only cancel your own downloads!", show_alert=True)

# Set up the bot
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Add handlers
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
