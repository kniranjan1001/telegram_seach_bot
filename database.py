# database.py
from pymongo import MongoClient
import os
import logging

# Set up MongoDB connection
MONGO_URI = os.getenv('MONGO_URI')  # MongoDB URI from environment variable
client = MongoClient(MONGO_URI)
db = client['movie_bot']  # Database name
users_collection = db['users']  # Collection for storing user data

logger = logging.getLogger(__name__)

# Function to save user ID to MongoDB
def save_user_id(user_id):
    if users_collection.count_documents({"user_id": user_id}) == 0:
        users_collection.insert_one({"user_id": user_id})
        logger.info(f"New user added to MongoDB: {user_id}")
    else:
        logger.info(f"User {user_id} already exists in MongoDB.")

# Function to load all user IDs from MongoDB
def load_user_ids():
    user_ids = [user['user_id'] for user in users_collection.find()]
    return set(user_ids)

# Function to check if a user is subscribed to the channel
async def is_user_subscribed(user_id: int, context):
    try:
        member_status = await context.bot.get_chat_member(os.getenv('CHANNEL_USERNAME'), user_id)
        return member_status.status in ['member', 'administrator', 'owner']
    except Exception as e:
        logger.error(f"Error checking subscription status: {e}")
        return False

# Function to add user ID to MongoDB
async def add_user_id(update):
    user_id = update.message.chat_id
    save_user_id(user_id)
    logger.info(f"New user added: {user_id}")

# Function to handle broadcasting message to all users in MongoDB
async def broadcast_message(update, context):
    if update.message.chat_id == int(os.getenv('ADMIN_USER_ID')):
        message = " ".join(context.args)
        if message:
            user_ids = load_user_ids()  # Load user IDs from MongoDB
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

# Function to list all users in MongoDB
async def user_list_command(update, context):
    if update.message.chat_id == int(os.getenv('ADMIN_USER_ID')):
        user_ids = load_user_ids()  # Load user IDs from MongoDB
        user_list = "\n".join(map(str, user_ids))
        await update.message.reply_text(f"List of connected users:\n{user_list or 'No users connected.'}\nTotal count: {len(user_ids)}")
    else:
        await update.message.reply_text("Unauthorized! Only the admin can use this command.")
