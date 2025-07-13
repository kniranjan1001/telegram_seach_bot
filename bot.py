from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
from telegram.constants import ChatMemberStatus
from telegram.error import Forbidden, BadRequest, TimedOut, NetworkError, Conflict
import logging
import requests
import os
import asyncio
import random
import signal
import sys
from fuzzywuzzy import process
from pymongo import MongoClient
import threading
import time
from aiohttp import web
import json

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))
JSON_URL = os.getenv('JSON_URL')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')

# MongoDB setup with connection pooling
MONGO_URL = os.getenv('MONGO_URI')
client = MongoClient(MONGO_URL, maxPoolSize=10, minPoolSize=1, maxIdleTimeMS=30000)
db = client['movie_bot']
user_collection = db['users']

# Global variables to track application state
application = None
is_shutting_down = False

# Improved error handler function with better conflict handling
async def error_handler(update: Update, context: CallbackContext) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    # Handle specific errors
    if isinstance(context.error, Forbidden):
        logger.warning(f"Bot was blocked by user {update.effective_user.id if update and update.effective_user else 'unknown'}")
        return
    elif isinstance(context.error, BadRequest):
        logger.warning(f"Bad request: {context.error}")
        return
    elif isinstance(context.error, TimedOut):
        logger.warning(f"Request timed out: {context.error}")
        return
    elif isinstance(context.error, NetworkError):
        logger.warning(f"Network error: {context.error}")
        return
    elif isinstance(context.error, Conflict):
        logger.error(f"Conflict error: {context.error}")
        logger.error("Multiple bot instances detected! Shutting down this instance...")
        # Gracefully shutdown this instance
        global is_shutting_down
        is_shutting_down = True
        return
    
    # For other errors, try to inform the user
    try:
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Sorry, something went wrong. Please try again later."
            )
    except Exception as e:
        logger.error(f"Failed to send error message to user: {e}")

# Function to check if a user is subscribed to the channel
async def is_user_subscribed(user_id: int, context: CallbackContext) -> bool:
    try:
        member_status = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member_status.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        logger.error(f"Error checking subscription status: {e}")
        return False

# Function to fetch movie data from JSON URL with retry logic
def fetch_movie_data():
    urls = [JSON_URL, "https://brown-briana-33.tiiny.site/data-1.json"]
    
    for url in urls:
        if not url:
            continue
            
        for attempt in range(3):  # Retry 3 times
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for URL {url}: {e}")
                if attempt < 2:  # Don't sleep on the last attempt
                    time.sleep(2)  # Use time.sleep instead of asyncio.sleep
    
    logger.error("Failed to fetch movie data from all URLs")
    return {}

# Function to search for the movie in the JSON data
async def search_movie_in_json(movie_name: str):
    try:
        # Fetch movie data from the JSON URL
        movie_data = fetch_movie_data()
        
        if not movie_data:
            return "Sorry, movie database is currently unavailable. Please try again later."

        # Initialize a list to hold button objects
        buttons = []

        # Use fuzzywuzzy to find the closest matches
        movie_names = list(movie_data.keys())
        closest_matches = process.extract(movie_name, movie_names, limit=6)

        if closest_matches:
            # Create buttons for the closest matches
            for match in closest_matches:
                movie_title = match[0]
                movie_url = movie_data[movie_title]
                buttons.append(InlineKeyboardButton(text=movie_title, url=movie_url))

            # Create the inline keyboard markup
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[button] for button in buttons])
            return keyboard
        else:
            return "Oops, couldn't find any matching movies! 😿 \n🔍 Double-check the spelling or try using a more specific movie name.\n💡 Still no luck? Request your movie here @anonyms_middle_man_bot! 🎥✨"
    except Exception as e:
        logger.error(f"Error searching movie data: {e}")
        return "An error😿 occurred while searching for the movie."

# Function to delete the message after a delay
async def delete_message(context: CallbackContext):
    global is_shutting_down
    if is_shutting_down:
        return
        
    job_data = context.job.data
    message_id = job_data['message_id']
    chat_id = job_data['chat_id']
    try:
        logger.info(f"Deleting message {message_id} from chat {chat_id}")
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Message {message_id} deleted successfully.")
    except Exception as e:
        logger.error(f"Failed to delete message {message_id}: {e}")

# Store user ID in MongoDB
async def store_user_id(user_id, username=None, first_name=None):
    try:
        if not user_collection.find_one({"_id": user_id}):
            user_collection.insert_one({
                "_id": user_id,
                "username": username,
                "first_name": first_name
            })
    except Exception as e:
        logger.error(f"Error storing user ID {user_id}: {e}")

# Safe message sending function with error handling
async def safe_send_message(update: Update, context: CallbackContext, text: str, reply_markup=None, **kwargs):
    try:
        if update.message:
            return await update.message.reply_text(text=text, reply_markup=reply_markup, **kwargs)
        elif update.callback_query:
            return await update.callback_query.message.reply_text(text=text, reply_markup=reply_markup, **kwargs)
    except Forbidden:
        logger.warning(f"Bot was blocked by user {update.effective_user.id}")
        return None
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None

# Modified function to handle movie search requests
async def search_movie(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_id = user.id
    
    # Store user ID if not already in the database
    await store_user_id(user_id, user.username, user.first_name)

    # Check if user is subscribed to the channel
    if await is_user_subscribed(user_id, context):
        movie_name = update.message.text.strip()
        
        try:
            await context.bot.send_chat_action(chat_id=update.message.chat_id, action='typing')
            
            # Send a creative message with simulated loading
            loading_message = await safe_send_message(update, context, "🔍 Searching the movie vaults... 🍿 Hang tight while we find your movie! 🎬")
            
            if not loading_message:
                return
            
            # Search for the movie in the JSON data
            result = await search_movie_in_json(movie_name)

            if isinstance(result, InlineKeyboardMarkup):
                try:
                    response_message = await loading_message.edit_text(
                        f"Search🔍 results for '{movie_name}' 🍿 :💀Note: Due to copyright issue search result will be deleted after 1 minute.⏳\n ⬇️How to download:- https://t.me/cctuitorial/7 \n🎬 *Request a Movie*: [Here](https://t.me/anonyms_middle_man_bot)", 
                        reply_markup=result,
                        parse_mode='Markdown'
                    )
                    logger.info(f"Scheduling deletion for message {response_message.message_id} in chat {update.message.chat_id} after 60 seconds.")
                    context.job_queue.run_once(delete_message, 60, data={'message_id': response_message.message_id, 'chat_id': update.message.chat_id})
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
            else:
                try:
                    response_message = await loading_message.edit_text(result)
                    logger.info(f"Scheduling deletion for message {response_message.message_id} in chat {update.message.chat_id} after 60 seconds.")
                    context.job_queue.run_once(delete_message, 60, data={'message_id': response_message.message_id, 'chat_id': update.message.chat_id})
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
        except Exception as e:
            logger.error(f"Error in search_movie: {e}")
    else:
        # Prompt user to subscribe to the channel
        message_text = (
            "🎬Bro subscribe below channels first to unlock🔓 access to 3000+ movies & series📺 — then just send the movie name! 🫣"
        )
        
        # Define the buttons
        keyboard = [
            [InlineKeyboardButton("Join Now", url="https://t.me/addlist/ijkMdb6cwtRkYjA1")]
        ]
        await safe_send_message(update, context, message_text, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

# Similarly, modify the /search command handler to include the subscription check
async def search_command(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    # Check if user is subscribed to the channel
    if await is_user_subscribed(user_id, context):
        if context.args:
            movie_name = " ".join(context.args).strip()
            
            try:
                await context.bot.send_chat_action(chat_id=update.message.chat_id, action='typing')
                loading_message = await safe_send_message(update, context, "🔍 Crunching through the movie vault... 🍿 Please hold on while we grab your movie magic! 🎥")
                
                if not loading_message:
                    return
                
                movie_result = await search_movie_in_json(movie_name)

                if isinstance(movie_result, InlineKeyboardMarkup):
                    try:
                        response_message = await loading_message.edit_text(
                            f"Search🔍 results for '{movie_name}' 🍿 :💀Note: Due to copyright issue search result will be deleted after 1 minute.⏳\n⬇️How to download:- https://t.me/cctuitorial/7 \n🎬 *Request a Movie*: [Here](https://t.me/anonyms_middle_man_bot)", 
                            reply_markup=movie_result,
                            parse_mode='Markdown'
                        )
                        logger.info(f"Scheduling deletion for message {response_message.message_id} in chat {update.message.chat_id} after 60 seconds.")
                        context.job_queue.run_once(delete_message, 60, data={'message_id': response_message.message_id, 'chat_id': update.message.chat_id})
                    except Exception as e:
                        logger.error(f"Error editing message: {e}")
                else:
                    try:
                        response_message = await loading_message.edit_text(movie_result)
                        logger.info(f"Scheduling deletion for message {response_message.message_id} in chat {update.message.chat_id} after 60 seconds.")
                        context.job_queue.run_once(delete_message, 60, data={'message_id': response_message.message_id, 'chat_id': update.message.chat_id})
                    except Exception as e:
                        logger.error(f"Error editing message: {e}")
            except Exception as e:
                logger.error(f"Error in search_command: {e}")
        else:
            await safe_send_message(update, context, "Please provide a movie name. Usage: /search <movie_name>")
    else:
        # Prompt user to subscribe to the channel
        message_text = (
            "🎬Bro subscribe below channels first to unlock🔓 access to 3000+ movies & series📺 — then just send the movie name! 🫣"
        )
        
        # Define the buttons
        keyboard = [
            [InlineKeyboardButton("Join Now", url="https://t.me/addlist/ijkMdb6cwtRkYjA1")]
        ]
        await safe_send_message(update, context, message_text, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

# Update the start command to save user IDs
async def start_command(update: Update, context: CallbackContext) -> None:
    if update.message is None:
        return
    
    user = update.message.from_user
    await store_user_id(user.id, user.username, user.first_name)
    
    about_button = InlineKeyboardButton(text="About🧑‍💻", callback_data='about')
    request_movie_button = InlineKeyboardButton(text="Request Movie😇", url='https://t.me/anonyms_middle_man_bot')
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[about_button], [request_movie_button]])
    
    welcome_message = (
       "\tWelcome to the Movie Search Bot! 🎬🍿\n"
       "Search🔍 for your favorite movies easily!\n"
       "Type correct movie🍿 name or use the command:\n"
       "```\n/search <movie_name>\n ie. /search Jungle Cruise Or Simply write movie name - Jungle Cruise```\n"
       "Enjoy your content😎"
    )
    await safe_send_message(update, context, welcome_message, reply_markup=keyboard)

# Function to handle button callbacks
async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == "about":
        about_message = (
            "🤖 *About the Bot*:\n"
            "This bot allows users to search for movies by name.\n"
            "*Developer*: [Harsh](https://t.me/Harsh_Raj1)\n"
            "Use the bot to find movie links and request movies!"
        )
        # Adding a Back button
        back_button = InlineKeyboardButton(text="🔙 Back", callback_data='back_to_start')
        keyboard = InlineKeyboardMarkup([[back_button]])
        
        try:
            await query.edit_message_text(about_message, parse_mode="Markdown", reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error editing message in button_callback: {e}")

    elif query.data == "back_to_start":
        about_button = InlineKeyboardButton(text="About🧑‍💻", callback_data='about')
        request_movie_button = InlineKeyboardButton(text="Request Movie😇", url='https://t.me/anonyms_middle_man_bot')
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[about_button], [request_movie_button]])

        welcome_message = (
            "Welcome to the Movie Search Bot! 🎬🍿\n"
            "Type the movie name directly or use the command:\n"
            "/search <movie_name>\n"
            "or send movie name directly🔍\n"
            "Enjoy your content😎"
        )

        try:
            await query.message.edit_text(welcome_message, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error editing message in button_callback: {e}")

# /broadcast command to send a message to all users (admin only)
async def broadcast_message(update: Update, context: CallbackContext):
    user = update.message.from_user
    if user.id != ADMIN_USER_ID:
        await safe_send_message(update, context, "You are not authorized to use this command.")
        return
    
    if context.args:
        broadcast_text = " ".join(context.args)
        users = user_collection.find({}, {"_id": 1})
        
        sent_count = 0
        for user_doc in users:
            try:
                await context.bot.send_message(chat_id=user_doc['_id'], text=broadcast_text)
                sent_count += 1
            except Forbidden:
                logger.warning(f"Bot was blocked by user {user_doc['_id']}")
                continue
            except Exception as e:
                logger.error(f"Error sending message to user {user_doc['_id']}: {e}")
                continue
        
        await safe_send_message(update, context, f"Broadcast sent to {sent_count} users.")
    else:
        await safe_send_message(update, context, "Usage: /broadcast <message>")

# /userlist command to show the total number of users
async def user_list_command(update: Update, context: CallbackContext):
    user = update.message.from_user
    if user.id != ADMIN_USER_ID:
        await safe_send_message(update, context, "You are not authorized to use this command.")
        return
    
    try:
        user_count = user_collection.count_documents({})
        await safe_send_message(update, context, f"Total registered users: {user_count}")
    except Exception as e:
        logger.error(f"Error getting user count: {e}")
        await safe_send_message(update, context, "Error retrieving user count.")

# Health check endpoint
async def health_check(update: Update, context: CallbackContext):
    await safe_send_message(update, context, "Bot is running healthy! 🟢")

# Signal handler for graceful shutdown
def signal_handler(signum, frame):
    global is_shutting_down
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    is_shutting_down = True

async def clear_existing_instances():
    """Clear any existing bot instances before starting"""
    try:
        bot = Bot(token=BOT_TOKEN)
        # Delete webhook with drop_pending_updates=True to clear any conflicts
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Cleared existing webhook and pending updates")
        
        # Wait a bit to ensure cleanup
        await asyncio.sleep(2)
        
        await bot.close()
        logger.info("Bot cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

async def webhook_handler(request):
    """Handle incoming webhook requests"""
    global is_shutting_down
    try:
        # Check if we're shutting down
        if is_shutting_down:
            return web.Response(text="Shutting down", status=503)
            
        # Get the JSON data from the request
        data = await request.json()
        
        # Create an Update object from the JSON data
        update = Update.de_json(data, application.bot)
        
        # Process the update
        await application.process_update(update)
        
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return web.Response(text="Error", status=500)

async def health_handler(request):
    """Health check endpoint"""
    return web.Response(text="Bot is healthy!", status=200)

async def create_webhook_app():
    """Create aiohttp web application for webhook"""
    app = web.Application()
    
    # Add webhook endpoint
    app.router.add_post(f"/{BOT_TOKEN}", webhook_handler)
    
    # Add health check endpoint
    app.router.add_get("/health", health_handler)
    app.router.add_get("/", health_handler)  # Root endpoint
    
    return app

async def run_bot():
    """Run the bot with proper async handling"""
    global application, is_shutting_down
    
    logger.info("Starting Movie Search Bot...")
    
    # Clear any existing instances first
    await clear_existing_instances()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add error handler
    application.add_error_handler(error_handler)

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    application.add_handler(CommandHandler("userlist", user_list_command))
    application.add_handler(CommandHandler("health", health_check))
    
    # Add message handler for text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_movie))
    
    # Add callback query handler for button presses
    application.add_handler(CallbackQueryHandler(button_callback))

    # Environment variables
    webhook_url = os.environ.get("WEBHOOK_URL")
    port = int(os.environ.get("PORT", 10000))
    
    # For deployment platforms, always start a web server
    # If WEBHOOK_URL is not set, we'll use polling but still serve a health endpoint
    
    try:
        # Initialize the application
        await application.initialize()
        await application.start()
        
        # Always create and start the web server (for health checks and potential webhook)
        app = await create_webhook_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        logger.info(f"Web server started successfully on 0.0.0.0:{port}")
        
        if webhook_url:
            logger.info(f"Starting webhook mode with URL: {webhook_url}")
            
            # Set the webhook URL
            webhook_full_url = f"{webhook_url}/{BOT_TOKEN}"
            await application.bot.set_webhook(url=webhook_full_url)
            logger.info(f"Webhook set to: {webhook_full_url}")
            
            # Keep the server running
            while not is_shutting_down:
                await asyncio.sleep(1)
                
        else:
            # Use polling mode but still keep web server running
            logger.info("Starting polling mode with web server...")
            
            # Start polling with conflict detection
            try:
                await application.updater.start_polling(
                    drop_pending_updates=True,
                    allowed_updates=Update.ALL_TYPES
                )
                
                # Keep the bot running
                logger.info("Bot is running in polling mode with web server... Press Ctrl+C to stop")
                while not is_shutting_down:
                    await asyncio.sleep(1)
                    
            except Conflict as e:
                logger.error(f"Conflict detected in polling mode: {e}")
                logger.error("Another instance is already running!")
                is_shutting_down = True
                
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        raise
    finally:
        logger.info("Shutting down bot...")
        try:
            # Clean shutdown
            if webhook_url:
                await application.bot.delete_webhook()
                
            if application.updater and application.updater.running:
                await application.updater.stop()
                
            if application.running:
                await application.stop()
                
            await application.shutdown()
            logger.info("Bot shutdown completed successfully")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

def main() -> None:
    """Main function to run the bot"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Run the bot
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except SystemExit:
        logger.info("Bot stopped by system signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        logger.info("Bot shutdown complete")

if __name__ == '__main__':
    main()
