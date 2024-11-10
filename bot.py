# main.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
from telegram.constants import ChatMemberStatus
import logging
import requests
import os
from database import save_user_id, load_user_ids, add_user_id, is_user_subscribed, broadcast_message, user_list_command  # Import from database.py

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Your Telegram bot token
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))  # Your Telegram user ID
JSON_URL = os.getenv('JSON_URL')  # URL where your JSON data is stored
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')

# Function to fetch movie data from JSON URL
def fetch_movie_data():
    try:
        response = requests.get(JSON_URL)
        response.raise_for_status()  # Raise an error for bad responses
        return response.json()  # Return the JSON data as a dictionary
    except requests.RequestException as e:
        logger.error(f"Error fetching data from JSON URL: {e}")
        return {}

# Function to search for the movie in the JSON data
async def search_movie_in_json(movie_name: str):
    try:
        movie_data = fetch_movie_data()
        buttons = []
        for key, value in movie_data.items():
            if movie_name.lower() in key.lower():
                buttons.append(InlineKeyboardButton(text=key, url=value))
        
        if buttons:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[button] for button in buttons])
            return keyboard
        else:
            return "Movie not found! 😿 \n👉 Please check the spelling or send the exact name.\n👉 If it's still missing, kindly search @cc_new_movie 🎬"
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

# Modify the /search command handler to include the subscription check
async def search_command(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    if await is_user_subscribed(user_id, context):  # Check subscription using the function from database.py
        if context.args:
            movie_name = " ".join(context.args).strip()
            await context.bot.send_chat_action(chat_id=update.message.chat_id, action='typing')
            loading_message = await update.message.reply_text("🔍 Searching the movie vaults... 🍿 Hang tight while we find your movie! 🎬")
            movie_result = await search_movie_in_json(movie_name)

            if isinstance(movie_result, InlineKeyboardMarkup):
                response_message = await loading_message.edit_text(f"Search 🔍 results for '{movie_name}'🍿: \n\n💀Note: Due to copyright issue move will be deleted after 1 minute.", reply_markup=movie_result)
                logger.info(f"Scheduling deletion for message {response_message.message_id} in chat {update.message.chat_id} after 60 seconds.")
                context.job_queue.run_once(delete_message, 60, context={'message_id': response_message.message_id, 'chat_id': update.message.chat_id})
            else:
                response_message = await loading_message.edit_text(movie_result)
                logger.info(f"Scheduling deletion for message {response_message.message_id} in chat {update.message.chat_id} after 60 seconds.")
                context.job_queue.run_once(delete_message, 60, context={'message_id': response_message.message_id, 'chat_id': update.message.chat_id})
        else:
            await update.message.reply_text("Please provide a movie name. Usage: /search <movie_name>")
    else:
        message_text = "🔔 To access the movie search, please subscribe to our channels first:\n\n ⚝After Subscribing send movie name directly ⌕"
        keyboard = [[InlineKeyboardButton("Join Now", url="https://t.me/addlist/4LAlWDoYvHk2ZDdl")]]
        await update.message.reply_text(text=message_text, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

# Modify the start command to save user IDs
async def start_command(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    await add_user_id(update)  # Use the add_user_id function from database.py
    about_button = InlineKeyboardButton(text="About🧑‍💻", callback_data='about')
    request_movie_button = InlineKeyboardButton(text="Request Movie😇", url='https://t.me/anonyms_middle_man_bot')
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[about_button], [request_movie_button]])
    welcome_message = (
       "\tWelcome to the Movie Search Bot! 🎬🍿\n"
       "Search🔍 for your favorite movies easily!\n"
       "Type correct movie🍿 name or use the command:\n"
       "```\n/search <movie_name>\n ie. /search Jungle Cruise OR Jungle Cruise```\n"
       "Enjoy your content😎"
    )
    await update.message.reply_text(welcome_message, reply_markup=keyboard)

# Modify the /broadcast command to use MongoDB
async def broadcast_command(update: Update, context: CallbackContext):
    await broadcast_message(update, context)  # Call from database.py

# Modify the /userlist command to use MongoDB
async def user_list_command(update: Update, context: CallbackContext):
    await user_list_command(update, context)  # Call from database.py

# Main function to set up the bot
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("userlist", user_list_command))
    
    # Add message handler for text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_movie))
    
    # Add callback query handler for button presses
    application.add_handler(CallbackQueryHandler(button_callback))

    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()
