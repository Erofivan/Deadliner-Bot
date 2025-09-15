"""Main Deadliner Telegram Bot implementation."""
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

from database import Database
from config import BOT_TOKEN, SECRET_CODE, REMINDER_INTERVALS
from scheduler import ReminderScheduler

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
ADD_DEADLINE, ADD_TITLE, ADD_DESCRIPTION, ADD_DATE, ADD_WEIGHT = range(5)

class DeadlinerBot:
    """Main bot class handling all functionality."""
    
    def __init__(self):
        self.db = Database()
        self.scheduler = ReminderScheduler(self.db)
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler."""
        user = update.effective_user
        self.db.add_user(user.id, user.username, user.first_name)
        
        keyboard = [
            [InlineKeyboardButton("📝 Добавить дедлайн", callback_data="add_deadline")],
            [InlineKeyboardButton("📋 Мои дедлайны", callback_data="list_deadlines")],
            [InlineKeyboardButton("📤 Экспорт дедлайнов", callback_data="export_deadlines")],
            [InlineKeyboardButton("🔑 Ввести код доступа", callback_data="enter_code")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = f"Привет, {user.first_name}! 👋\n\n"
        welcome_text += "Я помогу тебе управлять дедлайнами. Вот что я умею:\n\n"
        welcome_text += "📝 Создавать дедлайны с весом важности\n"
        welcome_text += "📋 Показывать список активных дедлайнов\n"
        welcome_text += "⏰ Присылать напоминания\n"
        welcome_text += "📤 Экспортировать дедлайны для пересылки\n"
        welcome_text += "🔑 Делиться доступом через секретный код\n\n"
        welcome_text += "Выбери действие:"
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command handler."""
        help_text = """
🤖 *Команды бота:*

/start - Главное меню
/help - Показать это сообщение  
/add - Добавить новый дедлайн
/list - Показать список дедлайнов
/export - Экспорт дедлайнов
/code - Ввести секретный код

📝 *Добавление дедлайна:*
Используй команду /add или кнопку в меню

📊 *Веса важности:*
• 🔴 urgent - Срочно (напоминания каждые 30 мин)
• 🟠 important - Важно (каждый час)  
• 🟡 normal - Обычно (каждые 2 часа)
• 🟢 low - Несрочно (каждые 4 часа)

📅 *Форматы даты:*
• 2024-12-31 15:30
• 31.12.2024 15:30
• завтра 15:30
• послезавтра 10:00

🔑 *Секретный код:*
Позволяет получить доступ к редактированию дедлайнов
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button presses."""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        if query.data == "add_deadline":
            return await self.start_add_deadline(update, context)
        elif query.data == "list_deadlines":
            return await self.list_deadlines(update, context)
        elif query.data == "export_deadlines":
            return await self.export_deadlines(update, context)
        elif query.data == "enter_code":
            return await self.prompt_secret_code(update, context)
        elif query.data.startswith("complete_"):
            deadline_id = int(query.data.split("_")[1])
            return await self.complete_deadline(update, context, deadline_id)
        elif query.data.startswith("delete_"):
            deadline_id = int(query.data.split("_")[1])
            return await self.delete_deadline(update, context, deadline_id)
    
    async def start_add_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start conversation for adding deadline."""
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "📝 Давайте создадим новый дедлайн!\n\n"
                "Введите название дедлайна:"
            )
        else:
            await update.message.reply_text(
                "📝 Давайте создадим новый дедлайн!\n\n"
                "Введите название дедлайна:"
            )
        
        return ADD_TITLE
    
    async def add_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get deadline title."""
        context.user_data['title'] = update.message.text
        
        await update.message.reply_text(
            "📄 Отлично! Теперь введите описание дедлайна "
            "(или отправьте /skip чтобы пропустить):"
        )
        
        return ADD_DESCRIPTION
    
    async def add_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get deadline description."""
        if update.message.text == "/skip":
            context.user_data['description'] = ""
        else:
            context.user_data['description'] = update.message.text
        
        await update.message.reply_text(
            "📅 Введите дату и время дедлайна в одном из форматов:\n\n"
            "• 2024-12-31 15:30\n"
            "• 31.12.2024 15:30\n"
            "• завтра 15:30\n"
            "• послезавтра 10:00"
        )
        
        return ADD_DATE
    
    async def add_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Parse and validate deadline date."""
        date_text = update.message.text.strip().lower()
        
        try:
            deadline_date = self.parse_date(date_text)
            context.user_data['deadline_date'] = deadline_date
            
            keyboard = [
                [InlineKeyboardButton("🔴 Срочно", callback_data="weight_urgent")],
                [InlineKeyboardButton("🟠 Важно", callback_data="weight_important")],
                [InlineKeyboardButton("🟡 Обычно", callback_data="weight_normal")],
                [InlineKeyboardButton("🟢 Несрочно", callback_data="weight_low")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"📊 Выберите важность дедлайна:\n\n"
                f"📝 Название: {context.user_data['title']}\n"
                f"📅 Дата: {deadline_date.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Веса определяют частоту напоминаний:",
                reply_markup=reply_markup
            )
            
            return ADD_WEIGHT
            
        except ValueError as e:
            await update.message.reply_text(
                f"❌ Не удалось распознать дату: {e}\n\n"
                "Попробуйте еще раз в формате:\n"
                "• 2024-12-31 15:30\n"
                "• 31.12.2024 15:30\n"
                "• завтра 15:30"
            )
            return ADD_DATE
    
    async def add_weight(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Save deadline with selected weight."""
        query = update.callback_query
        await query.answer()
        
        weight = query.data.split("_")[1]  # Extract weight from callback_data
        
        user_id = query.from_user.id
        title = context.user_data['title']
        description = context.user_data['description']
        deadline_date = context.user_data['deadline_date']
        
        # Save to database
        deadline_id = self.db.add_deadline(
            user_id, title, description, deadline_date, weight
        )
        
        # Clear conversation data
        context.user_data.clear()
        
        weight_emoji = {
            'urgent': '🔴',
            'important': '🟠', 
            'normal': '🟡',
            'low': '🟢'
        }
        
        success_text = (
            f"✅ Дедлайн создан!\n\n"
            f"📝 {title}\n"
            f"📅 {deadline_date.strftime('%d.%m.%Y %H:%M')}\n"
            f"📊 {weight_emoji[weight]} {weight.title()}\n"
            f"🆔 ID: {deadline_id}"
        )
        
        if description:
            success_text += f"\n📄 {description}"
        
        keyboard = [
            [InlineKeyboardButton("📋 Мои дедлайны", callback_data="list_deadlines")],
            [InlineKeyboardButton("📝 Добавить еще", callback_data="add_deadline")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(success_text, reply_markup=reply_markup)
        
        return ConversationHandler.END
    
    def parse_date(self, date_text: str) -> datetime:
        """Parse various date formats."""
        now = datetime.now()
        
        # Handle relative dates
        if "завтра" in date_text:
            base_date = now + timedelta(days=1)
            time_part = date_text.replace("завтра", "").strip()
        elif "послезавтра" in date_text:
            base_date = now + timedelta(days=2)
            time_part = date_text.replace("послезавтра", "").strip()
        else:
            time_part = date_text
            base_date = None
        
        # Parse time
        time_match = re.search(r'(\d{1,2})[:.]\s*(\d{2})', time_part)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            
            # Validate time
            if hour > 23:
                hour = 23
            if minute > 59:
                minute = 59
        else:
            hour, minute = 12, 0  # Default time
        
        if base_date:
            # For relative dates, use the base date with parsed time
            return base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Parse absolute dates
        date_patterns = [
            r'(\d{4})-(\d{1,2})-(\d{1,2})',  # YYYY-MM-DD
            r'(\d{1,2})\.(\d{1,2})\.(\d{4})',  # DD.MM.YYYY
            r'(\d{1,2})/(\d{1,2})/(\d{4})',   # DD/MM/YYYY
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, date_text)
            if match:
                if pattern.startswith(r'(\d{4})'):  # YYYY-MM-DD
                    year, month, day = map(int, match.groups())
                else:  # DD.MM.YYYY or DD/MM/YYYY
                    day, month, year = map(int, match.groups())
                
                try:
                    return datetime(year, month, day, hour, minute)
                except ValueError:
                    continue
        
        raise ValueError("Неверный формат даты")
    
    async def list_deadlines(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List user's deadlines."""
        user_id = update.effective_user.id
        deadlines = self.db.get_user_deadlines(user_id)
        
        if not deadlines:
            text = "📋 У вас пока нет активных дедлайнов.\n\nИспользуйте /add для создания нового."
            keyboard = [[InlineKeyboardButton("📝 Добавить дедлайн", callback_data="add_deadline")]]
        else:
            text = "📋 *Ваши дедлайны:*\n\n"
            
            weight_emoji = {'urgent': '🔴', 'important': '🟠', 'normal': '🟡', 'low': '🟢'}
            
            for i, dl in enumerate(deadlines, 1):
                days_left = (dl['deadline_date'] - datetime.now()).days
                hours_left = (dl['deadline_date'] - datetime.now()).seconds // 3600
                
                time_left = ""
                if days_left > 0:
                    time_left = f"({days_left}д.)"
                elif days_left == 0:
                    time_left = f"(сегодня, {hours_left}ч.)"
                else:
                    time_left = "(просрочено)"
                
                text += f"{i}. {weight_emoji[dl['weight']]} *{dl['title']}* {time_left}\n"
                text += f"   📅 {dl['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n"
                if dl['description']:
                    text += f"   📄 {dl['description']}\n"
                text += f"   🆔 ID: {dl['id']}\n\n"
            
            # Create inline keyboard for actions
            keyboard = []
            for dl in deadlines[:5]:  # Show buttons for first 5 deadlines
                keyboard.append([
                    InlineKeyboardButton(f"✅ Завершить {dl['id']}", callback_data=f"complete_{dl['id']}"),
                    InlineKeyboardButton(f"🗑 Удалить {dl['id']}", callback_data=f"delete_{dl['id']}")
                ])
            
            keyboard.append([InlineKeyboardButton("📝 Добавить дедлайн", callback_data="add_deadline")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def complete_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE, deadline_id: int):
        """Mark deadline as completed."""
        user_id = update.effective_user.id
        
        if self.db.complete_deadline(deadline_id, user_id):
            await update.callback_query.answer("✅ Дедлайн отмечен как выполненный!")
            await self.list_deadlines(update, context)
        else:
            await update.callback_query.answer("❌ Не удалось завершить дедлайн")
    
    async def delete_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE, deadline_id: int):
        """Delete deadline."""
        user_id = update.effective_user.id
        
        if self.db.delete_deadline(deadline_id, user_id):
            await update.callback_query.answer("🗑 Дедлайн удален!")
            await self.list_deadlines(update, context)
        else:
            await update.callback_query.answer("❌ Не удалось удалить дедлайн")
    
    async def export_deadlines(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Export deadlines in shareable format."""
        user_id = update.effective_user.id
        deadlines = self.db.get_user_deadlines(user_id)
        
        if not deadlines:
            text = "📤 У вас нет дедлайнов для экспорта."
        else:
            text = "📤 *Экспорт дедлайнов:*\n\n"
            text += "```\n"
            text += "🗓 СПИСОК ДЕДЛАЙНОВ\n"
            text += "=" * 25 + "\n\n"
            
            weight_names = {'urgent': 'СРОЧНО', 'important': 'ВАЖНО', 'normal': 'ОБЫЧНО', 'low': 'НЕСРОЧНО'}
            
            for i, dl in enumerate(deadlines, 1):
                text += f"{i}. {dl['title']}\n"
                text += f"   📅 {dl['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n"
                text += f"   📊 {weight_names[dl['weight']]}\n"
                if dl['description']:
                    text += f"   📄 {dl['description']}\n"
                text += "\n"
            
            text += "=" * 25 + "\n"
            text += f"Сгенерировано ботом @DeadlinerBot\n"
            text += f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            text += "```\n\n"
            text += "Вы можете скопировать и переслать это сообщение!"
        
        keyboard = [[InlineKeyboardButton("📋 Назад к списку", callback_data="list_deadlines")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def prompt_secret_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt user to enter secret code."""
        text = "🔑 Введите секретный код для получения доступа к редактированию дедлайнов:"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        
        context.user_data['awaiting_code'] = True
    
    async def check_secret_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check if entered code matches secret code."""
        if context.user_data.get('awaiting_code'):
            entered_code = update.message.text.strip()
            
            if entered_code == SECRET_CODE:
                user_id = update.effective_user.id
                self.db.grant_access(user_id)
                
                await update.message.reply_text(
                    "✅ Доступ предоставлен! Теперь вы можете создавать и редактировать дедлайны."
                )
            else:
                await update.message.reply_text(
                    "❌ Неверный код доступа. Попробуйте еще раз."
                )
            
            context.user_data['awaiting_code'] = False
    
    async def handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages in groups."""
        chat = update.effective_chat
        
        if chat.type in ['group', 'supergroup']:
            # Add group to database
            self.db.add_group(chat.id, chat.title)
            
            # Check if bot was mentioned or command was used
            if update.message.text and ('/deadlines' in update.message.text or '@' in update.message.text):
                deadlines = self.db.get_all_active_deadlines()
                
                if deadlines:
                    text = "📋 *Активные дедлайны:*\n\n"
                    
                    weight_emoji = {'urgent': '🔴', 'important': '🟠', 'normal': '🟡', 'low': '🟢'}
                    
                    for dl in deadlines[:10]:  # Show max 10 deadlines
                        days_left = (dl['deadline_date'] - datetime.now()).days
                        time_left = f"({days_left}д.)" if days_left > 0 else "(сегодня)"
                        
                        text += f"{weight_emoji[dl['weight']]} *{dl['title']}* {time_left}\n"
                        text += f"📅 {dl['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n\n"
                    
                    await update.message.reply_text(text, parse_mode='Markdown')
                else:
                    await update.message.reply_text("📋 Нет активных дедлайнов.")
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel current conversation."""
        context.user_data.clear()
        await update.message.reply_text("❌ Действие отменено.")
        return ConversationHandler.END


def main():
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables!")
        return
    
    bot = DeadlinerBot()
    
    # Build application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add conversation handler for adding deadlines
    add_deadline_conv = ConversationHandler(
        entry_points=[
            CommandHandler('add', bot.start_add_deadline),
            CallbackQueryHandler(bot.start_add_deadline, pattern="^add_deadline$")
        ],
        states={
            ADD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.add_title)],
            ADD_DESCRIPTION: [MessageHandler(filters.TEXT, bot.add_description)],
            ADD_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.add_date)],
            ADD_WEIGHT: [CallbackQueryHandler(bot.add_weight, pattern="^weight_")]
        },
        fallbacks=[CommandHandler('cancel', bot.cancel)]
    )
    
    # Add handlers
    application.add_handler(CommandHandler('start', bot.start))
    application.add_handler(CommandHandler('help', bot.help_command))
    application.add_handler(CommandHandler('list', bot.list_deadlines))
    application.add_handler(CommandHandler('export', bot.export_deadlines))
    application.add_handler(CommandHandler('code', bot.prompt_secret_code))
    application.add_handler(add_deadline_conv)
    application.add_handler(CallbackQueryHandler(bot.button_handler))
    application.add_handler(MessageHandler(filters.TEXT, bot.check_secret_code), group=1)
    application.add_handler(MessageHandler(filters.ALL, bot.handle_group_message), group=2)
    
    # Start scheduler
    bot.scheduler.start(application.bot)
    
    logger.info("Bot started successfully!")
    application.run_polling()


if __name__ == '__main__':
    main()