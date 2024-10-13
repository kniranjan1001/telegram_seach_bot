from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
import logging
import requests
import os
from flask import Flask, request

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# URL where your JSON data is stored
JSON_URL = 'https://api.jsonsilo.com/public/e4a0f8e8-47f9-474d-b759-448437c45a0c'
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Ensure to add error handling if the environment variable is not set
if BOT_TOKEN is None:
    raise ValueError("No BOT_TOKEN set for this environment")

# Create Flask app
app = Flask(__name__)

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
            # Group buttons into rows of 1
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[button] for button in buttons])
            return keyboard
        else:
            return "Movie not found😿. Kindly request your movie - [here](https://t.me/anonyms_middle_man_bot)"  # Return a message if no buttons are created
    except Exception as e:
        logger.error(f"Error searching movie data: {e}")
        return "An error😿 occurred while searching for the movie."

# Function to delete the message after a delay
async def delete_message(context: CallbackContext):
    job_data = context.job.context
    message_id = job_data['message_id']
    chat_id = job_data['chat_id']
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Message {message_id} deleted successfully.")
    except Exception as e:
        logger.error(f"Failed to delete message {message_id}: {e}")

# Function to handle movie search requests
async def search_movie(update: Update, context: CallbackContext) -> None:
    # Get the movie name from the user's message
    movie_name = update.message.text.strip()

     # Show 'typing' action to indicate loading
    await context.bot.send_chat_action(chat_id=update.message.chat_id, action='typing')

    # Search for the movie in the JSON data
    result = await search_movie_in_json(movie_name)

    # Send the results as buttons (if found)
    if isinstance(result, InlineKeyboardMarkup):
        response_message = await update.message.reply_text(f"Search🔍 results for '{movie_name}' 🍿 :", reply_markup=result)
        # Schedule message deletion after 1 minute (60 seconds)
        context.job_queue.run_once(delete_message, 60, context={'message_id': response_message.message_id, 'chat_id': update.message.chat_id})
    else:
        await update.message.reply_text(result)  # Send the 'Movie not found' message

# Command to handle '/search <movie_name>'
async def search_command(update: Update, context: CallbackContext) -> None:
    if context.args:
        # Get the movie name from the command arguments
        movie_name = " ".join(context.args).strip()

        # Search for the movie in the JSON data
        movie_result = await search_movie_in_json(movie_name)

        # Send the result back to the user
        if isinstance(movie_result, InlineKeyboardMarkup):
            response_message = await update.message.reply_text(f"Search 🔍 results for '{movie_name}'🍿:", reply_markup=movie_result)
        else:
            response_message = await update.message.reply_text(movie_result)  # Send the 'Movie not found' message

        # Schedule message deletion after 1 minute (60 seconds)
        context.job_queue.run_once(delete_message, 60, context={'message_id': response_message.message_id, 'chat_id': update.message.chat_id})
    else:
        # If no movie name is provided, send a message to the user
        await update.message.reply_text("Please provide a movie name. Usage: /search <movie_name>")

# Function to handle the '/start' command
async def start_command(update: Update, context: CallbackContext) -> None:
    # Create buttons for About, Help, and Request Movie
    about_button = InlineKeyboardButton(text="About🧑‍💻", callback_data='about')
    request_movie_button = InlineKeyboardButton(text="Request Movie😇", url='https://t.me/anonyms_middle_man_bot')

    # Create the inline keyboard markup
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [about_button],  # About and Help in the same row
        [request_movie_button]  # Request Movie in the next row
    ])

    # Send a welcome message and the inline keyboard
    welcome_message = (
       "\tWelcome to the Movie Search Bot! 🎬🍿\n"
       "Search🔍 for your favorite movies easily!\n"
        "Type correct movie🍿 name or use the command:\n"
        "```\n/search <movie_name>\n```\n"
        "Enjoy your content😎"
    )
    await update.message.reply_text(welcome_message, reply_markup=keyboard)

# Function to handle callbacks for About and Help buttons
async def button_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Acknowledge the callback

    if query.data == 'about':
        about_message = (
            "🤖 *About the Bot*:\n"
            "This bot allows users to search for movies by name.\n"
            "*Developer*: [Harsh](https://t.me/Harsh_Raj1)\n"
            "Use the bot to find movie links and request movies!"
        )
        await query.edit_message_text(about_message, parse_mode="Markdown")
    elif query.data == 'help_bot':
        help_message = (
            "🛠️ *Help - Available Commands*:\n"
            "/search <movie_name> - Search for a movie by name.\n"
            "Simply type the name of the movie, and the bot will find the closest matches."
        )
        await query.edit_message_text(help_message, parse_mode="Markdown")
    else:
        await query.edit_message_text("Unknown command. Please try again.")

# Set up webhook route
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    update = request.get_json()
    Application.builder().token(BOT_TOKEN).build().process_update(update)
    return '', 200

def main():
    # Set the webhook URL
    webhook_url = f"https://middleman-k8jr.onrender.com/{BOT_TOKEN}"
    
    # Create the Application and pass your bot's token
    application = Application.builder().token(BOT_TOKEN).build()

    # Add a handler for the '/start' command
    application.add_handler(CommandHandler('start', start_command))

    # Add a handler for the '/search' command
    application.add_handler(CommandHandler('search', search_command))

    # Add a handler for button callbacks
    application.add_handler(CallbackQueryHandler(button_callback))

    # Add a handler for regular text messages (when user sends just a movie name without /search)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_movie))

    # Set the webhook
    application.run_webhook(listen='0.0.0.0', port=int(os.environ.get("PORT", 5000)),webhook_url=webhook_url, url_path=BOT_TOKEN)

if __name__ == '__main__':
    main()
