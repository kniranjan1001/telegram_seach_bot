from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
from telegram.constants import ChatMemberStatus
from telegram.error import Forbidden, BadRequest, TimedOut, NetworkError
import logging
import requests
import os
import asyncio
import random
from fuzzywuzzy import process
from pymongo import MongoClient

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Your Telegram bot token
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))  # Your Telegram user ID
JSON_URL = os.getenv('JSON_URL')  # URL where your JSON data is stored
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')

# MongoDB setup
MONGO_URL = os.getenv('MONGO_URI')
client = MongoClient(MONGO_URL)
db = client['movie_bot']
user_collection = db['users']

# A global set to store unique user IDs
user_ids = set()

# Error handler function
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

# Function to check if a user is subscribed to the channel
async def is_user_subscribed(user_id: int, context: CallbackContext) -> bool:
    try:
        member_status = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member_status.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        logger.error(f"Error checking subscription status: {e}")
        return False

# Function to fetch movie data from JSON URL
def fetch_movie_data():
    try:
        response = requests.get(JSON_URL)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        try:
            response = requests.get("https://brown-briana-33.tiiny.site/data-1.json")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error fetching data: {e}")
            return {}

# Function to search for the movie in the JSON data
async def search_movie_in_json(movie_name: str):
    try:
        # Fetch movie data from the JSON URL
        movie_data = fetch_movie_data()

        # Initialize a list to hold button objects
        buttons = []

        # Use fuzzywuzzy to find the closest matches
        movie_names = list(movie_data.keys())
        closest_matches = process.extract(movie_name, movie_names, limit=6)  # Limit to top 6 matches

        if closest_matches:
            # Create buttons for the closest matches
            for match in closest_matches:
                movie_title = match[0]  # The matched movie title
                movie_url = movie_data[movie_title]  # The associated URL from JSON data
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
        return  # If there's no message, just return and do nothing
    
    user = update.message.from_user  # This will now safely access 'from_user'
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
        # Send the same message as /start
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

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    webhook_url = f"https://middleman-k8jr.onrender.com/{BOT_TOKEN}"

    # Add error handler
    application.add_error_handler(error_handler)

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    application.add_handler(CommandHandler("userlist", user_list_command))
    
    # Add message handler for text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_movie))
    
    # Add callback query handler for button presses
    application.add_handler(CallbackQueryHandler(button_callback))

    # Set the webhook
    application.run_webhook(listen='0.0.0.0', port=int(os.environ.get("PORT", 5000)), webhook_url=webhook_url, url_path=BOT_TOKEN)

if __name__ == '__main__':
    main()
