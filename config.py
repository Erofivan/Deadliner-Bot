"""Configuration settings for the Deadliner bot."""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
SECRET_CODE = os.getenv('SECRET_CODE', 'deadliner_secret_2024')
DATABASE_PATH = 'deadlines.db'
REMINDER_INTERVALS = {
    'urgent': 30,  # minutes
    'important': 60,  # minutes  
    'normal': 120,  # minutes
    'low': 240  # minutes
}