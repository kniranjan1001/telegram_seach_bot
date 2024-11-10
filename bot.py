from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
from telegram.constants import ChatMemberStatus
import logging
import requests
import os
import asyncio

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Your Telegram bot token
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))  # Your Telegram user ID
JSON_URL = os.getenv('JSON_URL')  # URL where your JSON data is stored
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')

# A global set to store unique user IDs
user_ids = set()

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
        response.raise_for_status()  # Raise an error for bad responses
        return response.json()  # Return the JSON data as a dictionary
    except requests.RequestException as e:
        logger.error(f"Error fetching data from JSON URL: {e}")
        return {}

# Function to search for the movie in the JSON data
async def search_movie_in_json(movie_name: str):
    try:
        # Fetch movie data from the JSON URL
        movie_data = fetch_movie_data()

        # Initialize a list to hold button objects
        buttons = []

        # Iterate through movie data and create buttons
        for key, value in movie_data.items():
            if movie_name.lower() in key.lower():
                buttons.append(InlineKeyboardButton(text=key, url=value))

        # Create the inline keyboard markup
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

# Function to store user IDs
async def add_user_id(update: Update):
    user_id = update.message.chat_id
    if user_id not in user_ids:
        user_ids.add(user_id)
        logger.info(f"New user added: {user_id}")

# Modified function to handle movie search requests
async def search_movie(update: Update, context: CallbackContext) -> None:
    await add_user_id(update)
    user_id = update.message.from_user.id

    # Check if user is subscribed to the channel
    if await is_user_subscribed(user_id, context):
        movie_name = update.message.text.strip()
        await context.bot.send_chat_action(chat_id=update.message.chat_id, action='typing')

        # Send a creative message with simulated loading
        loading_message = await update.message.reply_text("🔍 Searching the movie vaults... 🍿 Hang tight while we find your movie! 🎬")

        # Search for the movie in the JSON data
        result = await search_movie_in_json(movie_name)

        if isinstance(result, InlineKeyboardMarkup):
            response_message = await loading_message.edit_text(f"Search🔍 results for '{movie_name}' 🍿 :💀Note: Due to copyright issue search result will be deleted after 1 minute.", reply_markup=result)
            logger.info(f"Scheduling deletion for message {response_message.message_id} in chat {update.message.chat_id} after 60 seconds.")
            context.job_queue.run_once(delete_message, 60, data={'message_id': response_message.message_id, 'chat_id': update.message.chat_id})
        else:
            response_message = await loading_message.edit_text(result)
            logger.info(f"Scheduling deletion for message {response_message.message_id} in chat {update.message.chat_id} after 60 seconds.")
            context.job_queue.run_once(delete_message, 60, context={'message_id': response_message.message_id, 'chat_id': update.message.chat_id})
    else:
        # Prompt user to subscribe to the channel
         # Prompt user to subscribe to the channel
        message_text = (
        "🔔 To access the movie search, please subscribe to our channels first:\n\n ⚝After Subscribing send movie name directly ⌕"
        )
        
        # Define the buttons
        keyboard = [
            [InlineKeyboardButton("Join Now", url="https://t.me/addlist/4LAlWDoYvHk2ZDdl")]
        ]
        await update.message.reply_text(text=message_text,reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

# Similarly, modify the /search command handler to include the subscription check
async def search_command(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    # Check if user is subscribed to the channel
    if await is_user_subscribed(user_id, context):
        if context.args:
            movie_name = " ".join(context.args).strip()
            await context.bot.send_chat_action(chat_id=update.message.chat_id, action='typing')
            loading_message = await update.message.reply_text("🔍 Crunching through the movie vault... 🍿 Please hold on while we grab your movie magic! 🎥")
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
        # Prompt user to subscribe to the channel
        message_text = (
        "🔔 To access the movie search, please subscribe to our channels first:\n\n ⚝After Subscribing send movie name directly ⌕"
        )
        
        # Define the buttons
        keyboard = [
            [InlineKeyboardButton("Join Now", url="https://t.me/addlist/4LAlWDoYvHk2ZDdl")]
        ]
        await update.message.reply_text(text=message_text,reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
# Update the start command to save user IDs
async def start_command(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    save_user_id(user_id)  # Save user ID to file
    about_button = InlineKeyboardButton(text="About🧑‍💻", callback_data='about')
    request_movie_button = InlineKeyboardButton(text="Request Movie😇", url='https://t.me/anonyms_middle_man_bot')
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[about_button], [request_movie_button]])
    welcome_message = (
       "\tWelcome to the Movie Search Bot! 🎬🍿\n"
       "Search🔍 for your favorite movies easily!\n"
       "Type correct movie🍿 name or use the command:\n"
       "```\n/search <movie_name>\n "\search Jungle Cruise" Or Simply write movie name - Jungle Cruise```\n"
       "Enjoy your content😎"
    )
    await update.message.reply_text(welcome_message, reply_markup=keyboard)
    
# Function to handle button callbacks
async def button_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == 'about':
        about_message = (
            "🤖 *About the Bot*:\n"
            "This bot allows users to search for movies by name.\n"
            "*Developer*: [Harsh](https://t.me/Harsh_Raj1)\n"
            "Use the bot to find movie links and request movies!"
        )
        await query.edit_message_text(about_message, parse_mode="Markdown")

# Modify the broadcast function to use user IDs from the file
async def broadcast_message(update: Update, context: CallbackContext):
    if update.message.chat_id == ADMIN_USER_ID:
        message = " ".join(context.args)
        if message:
            user_ids = load_user_ids()  # Load user IDs from file
            for user_id in user_ids:
                try:
                    await context.bot.send_message(chat_id=user_id, text=message)
                except Exception as e:
                    logger.error(f"Failed to send message to {user_id}: {e}")
            await update.message.reply_text("Message broadcasted to all users!")
        else:
            await update.message.reply_text("Please provide a message to broadcast.")
    else:
        await update.message.reply_text("Unauthorized! Only the admin can use this command.")



# Update the user list function to show users from the file
async def user_list_command(update: Update, context: CallbackContext):
    if update.message.chat_id == ADMIN_USER_ID:
        user_ids = load_user_ids()  # Load user IDs from file
        user_list = "\n".join(map(str, user_ids))
        await update.message.reply_text(f"List of connected users:\n{user_list or 'No users connected.'}\nTotal count: {len(user_ids)}")
    else:
        await update.message.reply_text("Unauthorized! Only the admin can use this command.")

# Function to add user ID to a file without duplicates
def save_user_id(user_id):
    with open("record.txt", "a+") as file:
        file.seek(0)
        existing_ids = set(file.read().splitlines())
        if str(user_id) not in existing_ids:
            file.write(f"{user_id}\n")
            logger.info(f"New user added to file: {user_id}")


# Function to load all user IDs from the file
def load_user_ids():
    try:
        with open("users.txt", "r") as file:
            return set(map(int, file.read().splitlines()))  # Convert to integer set for use in broadcasting
    except FileNotFoundError:
        return set()

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    webhook_url = f"https://middleman-k8jr.onrender.com/{BOT_TOKEN}"

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
