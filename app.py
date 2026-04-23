from aiogram import Bot, Dispatcher
from database.data_manager import DataManager
from config import BOT_TOKEN, ADMIN_ID, ENCRYPTION_KEY

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
data_manager = DataManager(db_path="bot_database.db", admin_id=ADMIN_ID, encryption_key=ENCRYPTION_KEY)
