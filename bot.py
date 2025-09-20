"""Main Deadliner Telegram Bot implementation."""
import logging
import re
import json
import base64
import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

from database import Database
from config import BOT_TOKEN, SECRET_CODE, REMINDER_INTERVALS
from scheduler import ReminderScheduler
from importance_calculator import (
    calculate_importance_score, sort_deadlines_by_importance, 
    get_importance_description, get_weight_emoji
)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(ADD_DEADLINE, ADD_TITLE, ADD_DESCRIPTION, ADD_DATE, ADD_WEIGHT, 
 EDIT_DEADLINE, NOTIFICATION_SETTINGS, SET_NOTIFICATION_TIME, 
 VIEW_COMPLETED, DEADLINE_DETAIL, ENTER_ACCESS_CODE) = range(11)


def format_time_delta(delta: timedelta) -> str:
    """Форматирует timedelta в точную, удобную для чтения строку."""
    is_overdue = delta.total_seconds() < 0
    # Берем абсолютное значение для расчетов
    delta = abs(delta)
    
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days} д.")
    if hours > 0:
        parts.append(f"{hours} ч.")
    # Показываем минуты для точности, если нет часов или дней
    if minutes > 0 or (days == 0 and hours == 0):
        parts.append(f"{minutes} мин.")
    
    if not parts:
        return "(меньше минуты)"

    time_str = " ".join(parts)
    
    if is_overdue:
        return f"**(просрочено на {time_str})**"
    else:
        return f"(осталось {time_str})"
    
class DeadlinerBot:
    """Main bot class handling all functionality."""
    
    def __init__(self):
        self.db = Database()
        self.scheduler = ReminderScheduler(self.db)
        self.tz = ZoneInfo("Europe/Moscow")
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler."""
        user = update.effective_user
        self.db.add_user(user.id, user.username, user.first_name)
        
        keyboard = [
            [InlineKeyboardButton("📝 Добавить дедлайн", callback_data="add_deadline")],
            [InlineKeyboardButton("📋 Мои дедлайны", callback_data="list_deadlines")],
            [InlineKeyboardButton("🔔 Уведомления", callback_data="notification_settings")],
            [InlineKeyboardButton("⚙️ Дополнительно", callback_data="advanced_menu")]
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
        
        if update.callback_query:
            await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def advanced_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show advanced options menu."""
        keyboard = [
            [InlineKeyboardButton("🔐 Сгенерировать код доступа", callback_data="generate_access_code")],
            [InlineKeyboardButton("🔑 Ввести код доступа", callback_data="enter_code")],
            [InlineKeyboardButton("📤 Экспорт дедлайнов", callback_data="export_deadlines")],
            [InlineKeyboardButton("🎨 Отображение", callback_data="display_settings")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = "⚙️ *Дополнительные функции:*\n\n"
        text += "🔐 Сгенерировать код доступа - создать код на основе ваших дедлайнов для передачи другим\n"
        text += "🔑 Ввести код доступа - получить дедлайны по коду от другого пользователя\n"
        text += "📤 Экспорт дедлайнов - получить форматированный список для пересылки\n"
        text += "🎨 Отображение - настроить как показываются дедлайны"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
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
• 10 - Критически важно (экзамены, дедлайны проектов)
• 7-9 - Очень важно (рабочие задачи)  
• 4-6 - Средняя важность (лабораторные, домашние дела)
• 1-3 - Низкая важность (хобби, необязательные задачи)
• 0 - Очень низкая важность (идеи, напоминания)

🔔 *Уведомления:*
Настройте время и дни для получения напоминаний

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
        
        # Main menu actions
        if query.data == "main_menu":
            return await self.start(update, context)
        elif query.data == "add_deadline":
            return await self.start_add_deadline(update, context)
        elif query.data == "list_deadlines":
            return await self.list_deadlines(update, context)
        elif query.data == "advanced_menu":
            return await self.advanced_menu(update, context)
        elif query.data == "export_deadlines":
            return await self.export_deadlines(update, context)
        elif query.data == "generate_access_code":
            return await self.generate_access_code(update, context)
        elif query.data == "enter_code":
            return await self.prompt_access_code(update, context)
        elif query.data == "completed_deadlines":
            return await self.completed_deadlines(update, context)
        elif query.data == "notification_settings":
            return await self.notification_settings(update, context)
        
        # Sorting actions
        elif query.data.startswith("sort_"):
            sort_by = query.data.split("_", 1)[1]
            return await self.list_deadlines(update, context, sort_by=sort_by)
        
        # Editing actions
        elif query.data == "edit_deadlines":
            return await self.edit_deadlines(update, context)
        elif query.data == "restore_completed_deadlines":
            return await self.restore_completed_deadlines(update, context)
        elif query.data == "delete_completed_deadlines":
            return await self.delete_completed_deadlines(update, context)
        elif query.data.startswith("detail_"):
            deadline_id = int(query.data.split("_")[1])
            context.user_data['last_view'] = 'detail'
            return await self.deadline_detail(update, context, deadline_id)
        
        # Deadline actions
        elif query.data.startswith("complete_"):
            deadline_id = int(query.data.split("_")[1])
            return await self.complete_deadline(update, context, deadline_id)
        elif query.data.startswith("delete_completed_"):
            deadline_id = int(query.data.split("_")[2])
            return await self.delete_completed_deadline(update, context, deadline_id)
        elif query.data.startswith("delete_"):
            deadline_id = int(query.data.split("_")[1])
            return await self.delete_deadline(update, context, deadline_id)
        elif query.data.startswith("reopen_"):
            deadline_id = int(query.data.split("_")[1])
            return await self.reopen_deadline(update, context, deadline_id)

        
        # Notification settings actions
        elif query.data == "set_notification_times":
            return await self.set_notification_times(update, context)
        elif query.data == "set_notification_days":
            return await self.set_notification_days(update, context)
        elif query.data == "test_notifications":
            return await self.test_notifications(update, context)
        elif query.data == "display_settings":
            return await self.display_settings(update, context)
        elif query.data.startswith("toggle_show_"):
            setting = query.data.split("toggle_")[1]
            return await self.toggle_display_setting(update, context, setting)
        elif query.data.startswith("toggle_day_"):
            day = int(query.data.split("_")[2])
            return await self.toggle_notification_day(update, context, day)
        elif query.data == "save_notification_days":
            return await self.save_notification_days_confirm(update, context)
    
    async def start_add_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start conversation for adding deadline."""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = "📝 Давайте создадим новый дедлайн!\n\nВведите название дедлайна:"

        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
        
        return ADD_TITLE
    
    async def add_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get deadline title."""
        context.user_data['title'] = update.message.text
        
        # keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_title")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📄 Отлично! Теперь введите описание дедлайна "
            "(или отправьте /skip чтобы пропустить):",
            reply_markup=reply_markup
        )
        
        return ADD_DESCRIPTION
    
    async def add_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get deadline description."""
        if update.message.text == "/skip":
            context.user_data['description'] = ""
        else:
            context.user_data['description'] = update.message.text
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_description")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📅 Введите дату и время дедлайна в одном из форматов:\n\n"
            "• 2024-12-31 15:30\n"
            "• 31.12.2024 15:30\n"
            "• завтра 15:30\n"
            "• послезавтра 10:00",
            reply_markup=reply_markup
        )
        
        return ADD_DATE
    
    async def add_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Parse and validate deadline date."""
        date_text = update.message.text.strip().lower()
        
        try:
            deadline_date = self.parse_date(date_text)
            context.user_data['deadline_date'] = deadline_date
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_date")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"📊 Теперь укажите важность дедлайна (число от 0 до 10):\n\n"
                f"📝 Название: {context.user_data['title']}\n"
                f"📅 Дата: {deadline_date.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"🔴 10 - Критически важно\n"
                f"🟠 7-9 - Очень важно\n"
                f"🟡 4-6 - Средняя важность\n"
                f"🔵 1-3 - Низкая важность\n"
                f"⚪ 0 - Очень низкая важность\n\n"
                f"Введите число от 0 до 10:",
                reply_markup=reply_markup
            )
            
            return ADD_WEIGHT
            
        except ValueError as e:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"❌ Не удалось распознать дату: {e}\n\n"
                "Попробуйте еще раз в формате:\n"
                "• 2024-12-31 15:30\n"
                "• 31.12.2024 15:30\n"
                "• завтра 15:30",
                reply_markup=reply_markup
            )
            return ADD_DATE
    
    async def add_weight(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle weight input and save deadline."""
        try:
            weight_text = update.message.text.strip()
            weight = int(weight_text)
            
            if weight < 0 or weight > 10:
                keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "❌ Вес должен быть числом от 0 до 10. Попробуйте еще раз:",
                    reply_markup=reply_markup
                )
                return ADD_WEIGHT
            
            user_id = update.effective_user.id
            title = context.user_data['title']
            description = context.user_data['description']
            deadline_date = context.user_data['deadline_date']
            
            # Save to database
            deadline_id = self.db.add_deadline(
                user_id, title, description, deadline_date, weight
            )
            
            # Clear conversation data
            context.user_data.clear()
            
            weight_emoji = get_weight_emoji(weight)
            importance_desc = get_importance_description(weight, deadline_date)
            
            success_text = (
                f"✅ Дедлайн создан!\n\n"
                f"📝 {title}\n"
                f"📅 {deadline_date.strftime('%d.%m.%Y %H:%M')}\n"
                f"📊 {weight_emoji} Важность: {weight}/10\n"
                f"🎯 {importance_desc}\n"
                f"🆔 ID: {deadline_id}"
            )
            
            if description:
                success_text += f"\n📄 {description}"
            
            keyboard = [
                [InlineKeyboardButton("📋 Мои дедлайны", callback_data="list_deadlines")],
                [InlineKeyboardButton("📝 Добавить еще", callback_data="add_deadline")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(success_text, reply_markup=reply_markup)
            
            return ConversationHandler.END
            
        except ValueError:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ Пожалуйста, введите число от 0 до 10:",
                reply_markup=reply_markup
            )
            return ADD_WEIGHT
    
    def parse_date(self, date_text: str) -> datetime:
        """Parse various date formats."""
        now = datetime.now(self.tz)
        
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
    
    async def list_deadlines(self, update: Update, context: ContextTypes.DEFAULT_TYPE, sort_by: str = 'time_asc'):
        """List user's deadlines with new interface."""
        user_id = update.effective_user.id
        deadlines = self.db.get_user_deadlines(user_id)
        display_settings = self.db.get_user_display_settings(user_id)

        for dl in deadlines:
            if dl['deadline_date'].tzinfo is None:
                dl['deadline_date'] = dl['deadline_date'].replace(tzinfo=self.tz)
        
        if not deadlines:
            text = "📋 У вас пока нет активных дедлайнов.\n\nИспользуйте кнопку ниже для создания нового."
            keyboard = [
                [InlineKeyboardButton("📝 Добавить дедлайн", callback_data="add_deadline")],
                [InlineKeyboardButton("✅ Завершенные", callback_data="completed_deadlines")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
            ]
        else:
            # Sort deadlines based on selected criteria
            if sort_by == 'time_asc':
                # Most urgent first (ascending by remaining time)
                deadlines = sorted(deadlines, key=lambda d: abs((d['deadline_date'] - datetime.now(self.tz)).total_seconds()))
            elif sort_by == 'time_desc':
                # Least urgent first (descending by remaining time)
                deadlines = sorted(deadlines, key=lambda d: abs((d['deadline_date'] - datetime.now(self.tz)).total_seconds()), reverse=True)
            elif sort_by == 'importance_asc':
                # Least important first
                deadlines = sorted(deadlines, key=lambda d: calculate_importance_score(d['weight'], d['deadline_date']))
            elif sort_by == 'importance_desc':
                # Most important first (default from importance calculator)
                deadlines = sort_deadlines_by_importance(deadlines)
            elif sort_by == 'weight_asc':
                # Lowest weight first
                deadlines = sorted(deadlines, key=lambda d: d['weight'])
            elif sort_by == 'weight_desc':
                # Highest weight first
                deadlines = sorted(deadlines, key=lambda d: d['weight'], reverse=True)
            
            text = "📋 *Ваши дедлайны:*\n\n"
            
            # Use display settings to format deadlines
            for i, dl in enumerate(deadlines, 1):
                text += self.format_deadline_for_display(dl, display_settings, i)
            
            # Create 3 sorting buttons with reverse functionality
            time_arrow = "⬆️" if sort_by == 'time_asc' else "⬇️" if sort_by == 'time_desc' else ""
            importance_arrow = "⬆️" if sort_by == 'importance_asc' else "⬇️" if sort_by == 'importance_desc' else ""  
            weight_arrow = "⬆️" if sort_by == 'weight_asc' else "⬇️" if sort_by == 'weight_desc' else ""
            
            # Toggle sort direction on repeated click
            time_callback = "sort_time_desc" if sort_by == 'time_asc' else "sort_time_asc"
            importance_callback = "sort_importance_desc" if sort_by == 'importance_asc' else "sort_importance_asc" 
            weight_callback = "sort_weight_desc" if sort_by == 'weight_asc' else "sort_weight_asc"
            
            keyboard = [
                [
                    InlineKeyboardButton(f"⏰ По времени {time_arrow}", callback_data=time_callback),
                    InlineKeyboardButton(f"🎯 По важности {importance_arrow}", callback_data=importance_callback),
                    InlineKeyboardButton(f"🏷 По весу {weight_arrow}", callback_data=weight_callback)
                ],
                [InlineKeyboardButton("✏️ Редактировать", callback_data="edit_deadlines")],
                [InlineKeyboardButton("✅ Завершенные", callback_data="completed_deadlines")],
                [InlineKeyboardButton("📝 Добавить дедлайн", callback_data="add_deadline")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def edit_deadlines(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show deadlines for editing."""
        user_id = update.effective_user.id
        deadlines = self.db.get_user_deadlines(user_id)
        
        if not deadlines:
            text = "📋 У вас пока нет дедлайнов для редактирования."
            keyboard = [
                [InlineKeyboardButton("📝 Добавить дедлайн", callback_data="add_deadline")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
        else:
            text = "✏️ *Выберите дедлайн для редактирования:*\n\n"
            
            keyboard = []
            for dl in deadlines:
                if dl['deadline_date'].tzinfo is None:
                    dl['deadline_date'] = dl['deadline_date'].replace(tzinfo=self.tz)
                weight_emoji = get_weight_emoji(dl['weight'])
                button_text = f"{weight_emoji} {dl['title']}"
                if len(button_text) > 30:
                    button_text = button_text[:27] + "..."
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"detail_{dl['id']}")])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад к списку", callback_data="list_deadlines")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def deadline_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE, deadline_id: int):
        """Show detailed view of a deadline."""
        user_id = update.effective_user.id
        
        # Get deadline from database
        deadlines = self.db.get_user_deadlines(user_id)
        deadline = next((d for d in deadlines if d['id'] == deadline_id), None)
        if deadline['deadline_date'].tzinfo is None:
            deadline['deadline_date'] = deadline['deadline_date'].replace(tzinfo=self.tz)
        
        if not deadline:
            await update.callback_query.answer("❌ Дедлайн не найден")
            return await self.edit_deadlines(update, context)
        
        time_delta = deadline['deadline_date'] - datetime.now(self.tz)
        days_left = time_delta.days
        hours_left = int(time_delta.total_seconds() // 3600)
        
        # Format time remaining
        if days_left > 1:
            time_left = f"{days_left} н."
        elif days_left == 1:
            time_left = "завтра"
        elif days_left == 0 and hours_left > 0:
            time_left = f"через {hours_left} ч."
        elif days_left == 0 and hours_left >= 0:
            time_left = "сегодня"
        else:
            overdue_hours = abs(hours_left)
            if overdue_hours < 24:
                time_left = f"**просрочено {overdue_hours} ч.**"
            else:
                overdue_days = abs(days_left)
                time_left = f"**просрочено {overdue_days} д.**"
        
        weight_emoji = get_weight_emoji(deadline['weight'])
        importance_desc = get_importance_description(deadline['weight'], deadline['deadline_date'])
        
        text = f"📋 *Детали дедлайна:*\n\n"
        text += f"📝 **{deadline['title']}**\n"
        text += f"📅 {deadline['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n"
        text += f"⏰ {time_left}\n"
        text += f"📊 {weight_emoji} Важность: {deadline['weight']}/10\n"
        text += f"🎯 {importance_desc}\n"
        
        if deadline['description']:
            text += f"📄 {deadline['description']}\n"
        
        text += f"🆔 ID: {deadline['id']}"
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Завершить", callback_data=f"complete_{deadline_id}"),
                InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{deadline_id}")
            ],
            [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{deadline_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="edit_deadlines")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def completed_deadlines(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show completed deadlines."""
        user_id = update.effective_user.id
        completed = self.db.get_completed_deadlines(user_id)
        
        if not completed:
            text = "✅ У вас пока нет завершенных дедлайнов."
        else:
            text = "✅ *Завершенные дедлайны:*\n\n"
            
            for i, dl in enumerate(completed, 1):
                weight_emoji = get_weight_emoji(dl['weight'])
                text += f"{i}. {weight_emoji} <s>{dl['title']}</s>\n"
                text += f"   📅 {dl['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n"
                text += f"   📊 Важность: {dl['weight']}/10\n"
                if dl['description']:
                    text += f"   📄 {dl['description'][:50]}{'...' if len(dl['description']) > 50 else ''}\n"
                text += "\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Восстановить", callback_data="restore_completed_deadlines")],
            [InlineKeyboardButton("🗑️ Удалить", callback_data="delete_completed_deadlines")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    
    async def restore_completed_deadlines(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show completed deadlines for restoring."""
        user_id = update.effective_user.id
        completed = self.db.get_completed_deadlines(user_id)
        
        if not completed:
            text = "✅ У вас пока нет завершенных дедлайнов."
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="completed_deadlines")]]
        else:
            text = "🔄 *Выберите дедлайн для восстановления:*\n\n"
            
            keyboard = []
            for dl in completed:
                if dl['deadline_date'].tzinfo is None:
                    dl['deadline_date'] = dl['deadline_date'].replace(tzinfo=self.tz)
                weight_emoji = get_weight_emoji(dl['weight'])
                button_text = f"{weight_emoji} {dl['title']}"
                if len(button_text) > 30:
                    button_text = button_text[:27] + "..."
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"reopen_{dl['id']}")])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="completed_deadlines")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def delete_completed_deadlines(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show completed deadlines for deletion."""
        user_id = update.effective_user.id
        completed = self.db.get_completed_deadlines(user_id)
        
        if not completed:
            text = "✅ У вас пока нет завершенных дедлайнов."
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="completed_deadlines")]]
        else:
            text = "🗑️ *Выберите дедлайн для удаления:*\n\n"
            text += "⚠️ *Внимание:* Удаленные дедлайны нельзя будет восстановить!\n\n"
            
            keyboard = []
            for dl in completed:
                if dl['deadline_date'].tzinfo is None:
                    dl['deadline_date'] = dl['deadline_date'].replace(tzinfo=self.tz)
                weight_emoji = get_weight_emoji(dl['weight'])
                button_text = f"{weight_emoji} {dl['title']}"
                if len(button_text) > 30:
                    button_text = button_text[:27] + "..."
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_completed_{dl['id']}")])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="completed_deadlines")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def reopen_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE, deadline_id: int):
        """Reopen a completed deadline."""
        user_id = update.effective_user.id
        
        if self.db.reopen_deadline(deadline_id, user_id):
            await update.callback_query.answer("🔄 Дедлайн восстановлен!")
            await self.restore_completed_deadlines(update, context)
        else:
            await update.callback_query.answer("❌ Не удалось восстановить дедлайн")

    async def delete_completed_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE, deadline_id: int):
        """Delete a completed deadline permanently."""
        user_id = update.effective_user.id
        
        if self.db.delete_deadline(deadline_id, user_id):
            await update.callback_query.answer("🗑️ Дедлайн удален!")
            await self.delete_completed_deadlines(update, context)
        else:
            await update.callback_query.answer("❌ Не удалось удалить дедлайн")
    
    async def notification_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show notification settings."""
        user_id = update.effective_user.id
        settings = self.db.get_user_notification_settings(user_id)
        
        times_str = ", ".join(settings['times']) if settings['times'] else "не настроено"
        
        # Convert day numbers to day names
        day_names = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС']
        active_days = [day_names[day] for day in settings['days'] if 0 <= day <= 6]
        days_str = ", ".join(active_days) if active_days else "не выбрано"
        
        text = f"🔔 *Настройки уведомлений:*\n\n"
        text += f"⏰ Время: {times_str}\n"
        text += f"📅 Дни: {days_str}\n\n"
        text += "Настройте когда вы хотите получать уведомления о ваших дедлайнах."
        
        keyboard = [
            [InlineKeyboardButton("⏰ Настроить время", callback_data="set_notification_times")],
            [InlineKeyboardButton("📅 Настроить дни", callback_data="set_notification_days")],
            [InlineKeyboardButton("🧪 Тест уведомлений", callback_data="test_notifications")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def set_notification_times(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt user to set notification times."""
        text = ("⏰ *Настройка времени уведомлений*\n\n"
                "Введите время получения уведомлений в формате HH:MM, "
                "разделенное запятыми.\n\n"
                "*Примеры:*\n"
                "• 10:00\n"
                "• 10:00, 20:00\n"
                "• 09:30, 14:00, 21:00\n\n"
                "Введите время:")
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="notification_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        return SET_NOTIFICATION_TIME
    
    async def save_notification_times(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Save notification times from user input."""
        try:
            user_id = update.effective_user.id
            times_text = update.message.text.strip()
            
            # Parse times
            time_strings = [t.strip() for t in times_text.split(',')]
            valid_times = []
            
            for time_str in time_strings:
                # Validate time format
                if ':' not in time_str:
                    raise ValueError(f"Неверный формат времени: {time_str}")
                
                parts = time_str.split(':')
                if len(parts) != 2:
                    raise ValueError(f"Неверный формат времени: {time_str}")
                
                hour, minute = int(parts[0]), int(parts[1])
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    raise ValueError(f"Неверное время: {time_str}")
                
                formatted_time = f"{hour:02d}:{minute:02d}"
                valid_times.append(formatted_time)
            
            if not valid_times:
                raise ValueError("Не указано ни одного времени")
            
            # Get current settings and update times
            settings = self.db.get_user_notification_settings(user_id)
            self.db.update_user_notification_settings(user_id, valid_times, settings['days'])
            
            await update.message.reply_text(
                f"✅ Время уведомлений сохранено: {', '.join(valid_times)}\n\n"
                "Возвращаемся к настройкам..."
            )
            
            # Return to notification settings
            context.user_data.clear()
            await self.notification_settings(update, context)
            
            return ConversationHandler.END
            
        except ValueError as e:
            await update.message.reply_text(
                f"❌ {str(e)}\n\n"
                "Попробуйте еще раз. Используйте формат HH:MM (например: 10:00, 20:30)"
            )
            return SET_NOTIFICATION_TIME
        except Exception as e:
            logger.error(f"Error saving notification times: {e}")
            await update.message.reply_text("❌ Произошла ошибка при сохранении")
            return ConversationHandler.END
    
    async def set_notification_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show day selection interface."""
        user_id = update.effective_user.id
        settings = self.db.get_user_notification_settings(user_id)
        
        day_names = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС']
        selected_days = settings['days']
        
        text = "📅 *Настройка дней уведомлений*\n\nВыберите дни недели:\n\n"
        
        keyboard = []
        for i, day_name in enumerate(day_names):
            is_selected = i in selected_days
            button_text = f"✅ {day_name}" if is_selected else f"◻️ {day_name}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"toggle_day_{i}")])
        
        keyboard.append([
            InlineKeyboardButton("💾 Сохранить", callback_data="save_notification_days"),
            InlineKeyboardButton("🔙 Назад", callback_data="notification_settings")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def toggle_notification_day(self, update: Update, context: ContextTypes.DEFAULT_TYPE, day: int):
        """Toggle a day in notification settings."""
        user_id = update.effective_user.id
        settings = self.db.get_user_notification_settings(user_id)
        
        if day in settings['days']:
            settings['days'].remove(day)
        else:
            settings['days'].append(day)
        
        # Save updated settings
        self.db.update_user_notification_settings(user_id, settings['times'], settings['days'])
        
        # Update interface
        await self.set_notification_days(update, context)
    
    async def save_notification_days_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirm saving notification days."""
        user_id = update.effective_user.id
        settings = self.db.get_user_notification_settings(user_id)
        
        day_names = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС']
        selected_day_names = [day_names[day] for day in settings['days']]
        
        await update.callback_query.answer(
            f"✅ Дни сохранены: {', '.join(selected_day_names)}"
        )
        await self.notification_settings(update, context)
    
    async def test_notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a test notification to verify the system is working."""
        user_id = update.effective_user.id
        
        try:
            # Get user's deadlines to include in test
            deadlines = self.db.get_user_deadlines(user_id, include_completed=False)
            
            if deadlines:
                # Use scheduler to send actual notification
                await self.scheduler.send_user_notifications(user_id)
                text = "🧪 *Тест уведомлений выполнен!*\n\n"
                text += "✅ Тестовое уведомление отправлено на основе ваших текущих дедлайнов.\n\n"
                text += f"🕐 Время: {datetime.now(self.tz).strftime('%H:%M')} (МСК)\n"
                text += f"📅 День недели: {datetime.now(self.tz).weekday()}\n\n"
                text += "Если уведомление не пришло, проверьте настройки времени и дней."
            else:
                text = "🧪 *Тест уведомлений*\n\n"
                text += "❌ У вас нет активных дедлайнов для тестирования.\n\n"
                text += f"🕐 Текущее время: {datetime.now(self.tz).strftime('%H:%M')} (МСК)\n"
                text += f"📅 День недели: {datetime.now(self.tz).weekday()}\n\n"
                text += "Создайте дедлайн и попробуйте тест снова."
                
        except Exception as e:
            logger.error(f"Error testing notifications: {e}")
            text = "❌ *Ошибка при тестировании уведомлений*\n\n"
            text += "Проверьте настройки и попробуйте позже."
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="notification_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    def format_deadline_for_display(self, deadline: Dict, settings: Dict, index: int = None) -> str:
        """Format a deadline according to user display settings."""
        dl = deadline.copy()
        if dl['deadline_date'].tzinfo is None:
            dl['deadline_date'] = dl['deadline_date'].replace(tzinfo=self.tz)
        
        time_delta = dl['deadline_date'] - datetime.now(self.tz)
        time_left = format_time_delta(time_delta)
        
        # Start with basic structure
        result = ""
        
        # Add index if provided
        if index is not None:
            result += f"{index}. "
        
        # Add emoji if enabled
        if settings['show_emojis']:
            weight_emoji = get_weight_emoji(dl['weight'])
            result += f"{weight_emoji} "
        
        # Add title (always shown)
        if time_delta <= timedelta(0):
            result += f"***{dl['title']}***"
        else:
            result += dl['title']
        
        # Add remaining time if enabled
        if settings['show_remaining_time']:
            result += f" {time_left}"
        
        result += "\n"
        
        # Add date if enabled
        if settings['show_date']:
            result += f"   📅 {dl['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n"
        
        # Add importance/weight if enabled
        if settings['show_importance'] or settings['show_weight']:
            if settings['show_weight']:
                result += f"   📊 Важность: {dl['weight']}/10\n"
        
        # Add description if enabled and exists
        if settings['show_description'] and dl['description']:
            result += f"   📄 {dl['description'][:50]}{'...' if len(dl['description']) > 50 else ''}\n"
        
        result += "\n"
        return result

    async def display_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show display configuration settings with example."""
        user_id = update.effective_user.id
        settings = self.db.get_user_display_settings(user_id)
        
        # Create example deadlines
        example_deadlines = [
            {
                'title': 'Сдать курсовую работу',
                'description': 'Написать и оформить курсовую работу по базам данных',
                'deadline_date': datetime.now(self.tz) + timedelta(days=2, hours=3),
                'weight': 9
            },
            {
                'title': 'Купить продукты',
                'description': 'Молоко, хлеб, масло для завтрака',
                'deadline_date': datetime.now(self.tz) + timedelta(hours=5),
                'weight': 4
            },
            {
                'title': 'Встреча с клиентом',
                'description': 'Презентация нового проекта в офисе',
                'deadline_date': datetime.now(self.tz) + timedelta(days=1, hours=10),
                'weight': 7
            }
        ]
        
        # Format example deadlines with current settings
        example_text = ""
        for i, dl in enumerate(example_deadlines, 1):
            example_text += self.format_deadline_for_display(dl, settings, i)
        
        text = "🎨 *Настройки отображения дедлайнов*\n\n"
        text += "*Пример того, как выглядят ваши дедлайны:*\n\n"
        text += example_text
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        text += "*Настройте отображение:*"
        
        keyboard = [
            [
                InlineKeyboardButton(
                    f"⏰ Оставшееся время {'✅' if settings['show_remaining_time'] else '❌'}",
                    callback_data="toggle_show_remaining_time"
                )
            ],
            [
                InlineKeyboardButton(
                    f"📄 Описание {'✅' if settings['show_description'] else '❌'}",
                    callback_data="toggle_show_description"
                )
            ],
            [
                InlineKeyboardButton(
                    f"📊 Важность {'✅' if settings['show_importance'] else '❌'}",
                    callback_data="toggle_show_importance"
                ),
                InlineKeyboardButton(
                    f"🏷 Вес {'✅' if settings['show_weight'] else '❌'}",
                    callback_data="toggle_show_weight"
                )
            ],
            [
                InlineKeyboardButton(
                    f"😊 Смайлики {'✅' if settings['show_emojis'] else '❌'}",
                    callback_data="toggle_show_emojis"
                ),
                InlineKeyboardButton(
                    f"📅 Дата {'✅' if settings['show_date'] else '❌'}",
                    callback_data="toggle_show_date"
                )
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="advanced_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def toggle_display_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE, setting: str):
        """Toggle a display setting and refresh the interface."""
        user_id = update.effective_user.id
        current_settings = self.db.get_user_display_settings(user_id)
        
        # Toggle the setting
        new_value = not current_settings[setting]
        self.db.update_user_display_setting(user_id, setting, new_value)
        
        # Refresh the display settings interface
        await self.display_settings(update, context)

    async def start_edit_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start conversation for editing deadline weight."""
        query = update.callback_query
        deadline_id = int(query.data.split("_")[1])
        return await self.edit_deadline_weight(update, context, deadline_id)
    
    async def edit_deadline_weight(self, update: Update, context: ContextTypes.DEFAULT_TYPE, deadline_id: int):
        """Start editing a deadline's weight."""
        user_id = update.effective_user.id
        
        # Get deadline from database
        deadlines = self.db.get_user_deadlines(user_id)
        deadline = next((d for d in deadlines if d['id'] == deadline_id), None)
        
        if not deadline:
            await update.callback_query.answer("❌ Дедлайн не найден")
            return await self.edit_deadlines(update, context)
        
        context.user_data['edit_deadline_id'] = deadline_id
        
        weight_emoji = get_weight_emoji(deadline['weight'])
        
        text = (f"✏️ *Редактирование дедлайна*\n\n"
                f"📝 **{deadline['title']}**\n"
                f"📅 {deadline['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n"
                f"📊 Текущая важность: {weight_emoji} {deadline['weight']}/10\n\n"
                f"Введите новую важность (число от 0 до 10):")
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"detail_{deadline_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        return EDIT_DEADLINE
    
    async def save_deadline_weight(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Save the edited deadline weight."""
        try:
            weight_text = update.message.text.strip()
            weight = int(weight_text)
            
            if weight < 0 or weight > 10:
                deadline_id = context.user_data.get('edit_deadline_id')
                keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"detail_{deadline_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "❌ Вес должен быть числом от 0 до 10. Попробуйте еще раз:",
                    reply_markup=reply_markup
                )
                return EDIT_DEADLINE
            
            user_id = update.effective_user.id
            deadline_id = context.user_data.get('edit_deadline_id')
            
            if not deadline_id:
                await update.message.reply_text("❌ Ошибка: дедлайн не найден")
                return ConversationHandler.END
            
            # Update deadline weight
            success = self.db.update_deadline(deadline_id, user_id, weight=weight)
            
            if success:
                weight_emoji = get_weight_emoji(weight)
                keyboard = [[InlineKeyboardButton("📋 К деталям", callback_data=f"detail_{deadline_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"✅ Важность изменена на {weight_emoji} {weight}/10",
                    reply_markup=reply_markup
                )
                
                # Clear conversation data
                context.user_data.clear()
            else:
                await update.message.reply_text("❌ Не удалось изменить важность")
                context.user_data.clear()
            
            return ConversationHandler.END
            
        except ValueError:
            deadline_id = context.user_data.get('edit_deadline_id')
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=f"detail_{deadline_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ Пожалуйста, введите число от 0 до 10:",
                reply_markup=reply_markup
            )
            return EDIT_DEADLINE

    async def edit_deadline_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle back button during deadline editing."""
        query = update.callback_query
        if query.data.startswith("detail_"):
            deadline_id = int(query.data.split("_")[1])
            context.user_data.clear()  # Clear conversation data
            return await self.deadline_detail(update, context, deadline_id)
        return ConversationHandler.END

    async def add_deadline_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle back button during add deadline conversation."""
        context.user_data.clear()  # Clear conversation data
        await self.start(update, context)
        return ConversationHandler.END

    async def complete_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE, deadline_id: int):
        """Mark deadline as completed."""
        user_id = update.effective_user.id
        
        if self.db.complete_deadline(deadline_id, user_id):
            await update.callback_query.answer("✅ Дедлайн отмечен как выполненный!")
            # Return to edit view if coming from detail view, otherwise to list
            callback_data = update.callback_query.data
            if 'detail' in context.user_data.get('last_view', ''):
                await self.edit_deadlines(update, context)
            else:
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
            # Sort by importance for export
            deadlines = sort_deadlines_by_importance(deadlines)
            
            text = "📤 *Экспорт дедлайнов:*\n\n"
            text += "```\n"
            text += "🗓 СПИСОК ДЕДЛАЙНОВ\n"
            text += "=" * 25 + "\n\n"
            
            for i, dl in enumerate(deadlines, 1):
                weight_emoji = get_weight_emoji(dl['weight'])
                importance_desc = get_importance_description(dl['weight'], dl['deadline_date'])
                
                text += f"{i}. {dl['title']}\n"
                text += f"   📅 {dl['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n"
                text += f"   📊 {weight_emoji} Важность: {dl['weight']}/10\n"
                text += f"   🎯 {importance_desc.replace('🔥 ', '').replace('🚨 ', '').replace('⚡ ', '').replace('⏰ ', '').replace('📝 ', '').replace('🔵 ', '')}\n"
                if dl['description']:
                    text += f"   📄 {dl['description']}\n"
                text += "\n"
            
            text += "=" * 25 + "\n"
            text += f"Сгенерировано ботом @DeadlinerBot\n"
            text += f"Дата: {datetime.now(self.tz).strftime('%d.%m.%Y %H:%M')}\n"
            text += "```\n\n"
            text += "Вы можете скопировать и переслать это сообщение!"
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="advanced_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def generate_access_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate access code based on user's deadlines."""
        user_id = update.effective_user.id
        deadlines = self.db.get_user_deadlines(user_id)
        
        if not deadlines:
            text = "❌ У вас нет дедлайнов для создания кода доступа."
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="advanced_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text, reply_markup=reply_markup)
            return
        
        # Prepare deadline data for encoding
        deadline_data = []
        for dl in deadlines:
            if dl['completed']:
                continue  # Skip completed deadlines
            
            deadline_info = {
                'title': dl['title'],
                'description': dl['description'] or '',
                'deadline_date': dl['deadline_date'].isoformat() if hasattr(dl['deadline_date'], 'isoformat') else str(dl['deadline_date']),
                'weight': dl['weight']
            }
            deadline_data.append(deadline_info)
        
        if not deadline_data:
            text = "❌ У вас нет активных дедлайнов для создания кода доступа."
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="advanced_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text, reply_markup=reply_markup)
            return
        
        # Create the access code
        try:
            # Convert to JSON and encode
            json_data = json.dumps(deadline_data, ensure_ascii=False)
            encoded_data = base64.b64encode(json_data.encode('utf-8')).decode('ascii')
            
            # Create a readable access code (first 12 chars of hash + length info)
            data_hash = hashlib.md5(json_data.encode('utf-8')).hexdigest()[:12].upper()
            code_length = len(encoded_data)
            access_code = f"DL{data_hash}{code_length:04d}"
            
            # Store the full data for later retrieval
            self.db.store_access_code(access_code, encoded_data)
            
            text = f"🔐 *Код доступа создан!*\n\n"
            text += f"**Ваш код:** `{access_code}`\n\n"
            text += f"📊 Экспортировано дедлайнов: {len(deadline_data)}\n"
            text += f"🕐 Код создан: {datetime.now(self.tz).strftime('%d.%m.%Y %H:%M')}\n\n"
            text += "🔄 *Как использовать:*\n"
            text += "1. Скопируйте код выше\n"
            text += "2. Передайте его другому пользователю\n"
            text += "3. Он сможет импортировать ваши дедлайны через \"Ввести код доступа\"\n\n"
            text += "⚠️ *Внимание:* Код содержит все ваши активные дедлайны!"
            
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="advanced_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
        except Exception as e:
            logger.error(f"Error generating access code: {e}")
            text = "❌ Не удалось создать код доступа. Попробуйте позже."
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="advanced_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def prompt_access_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt user to enter access code for importing deadlines."""
        text = "🔑 *Импорт дедлайнов по коду*\n\n"
        text += "Введите код доступа, полученный от другого пользователя.\n\n"
        text += "**Формат кода:** DL + 12 символов + 4 цифры\n"
        text += "**Пример:** `DLA1B2C3D4E5F012`\n\n"
        text += "⚠️ *Внимание:* Дедлайны будут добавлены к вашим существующим, а не заменят их."
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="advanced_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        return ENTER_ACCESS_CODE

    async def import_deadlines_from_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Import deadlines from access code."""
        access_code = update.message.text.strip().upper()
        user_id = update.effective_user.id
        
        # Validate code format
        if not access_code.startswith('DL') or len(access_code) != 18:
            await update.message.reply_text(
                "❌ Неверный формат кода. Код должен начинаться с 'DL' и содержать 16 символов после него.\n\n"
                "**Пример:** `DLA1B2C3D4E5F012`"
            )
            return ENTER_ACCESS_CODE
        
        try:
            # Get stored data
            encoded_data = self.db.get_access_code_data(access_code)
            
            if not encoded_data:
                await update.message.reply_text(
                    "❌ Код доступа не найден или уже недействителен.\n\n"
                    "Убедитесь, что код введен правильно и попробуйте еще раз."
                )
                return ENTER_ACCESS_CODE
            
            # Decode the data
            json_data = base64.b64decode(encoded_data.encode('ascii')).decode('utf-8')
            deadline_data = json.loads(json_data)
            
            # Import deadlines
            imported_count = 0
            for dl_info in deadline_data:
                try:
                    # Parse deadline date
                    deadline_date = datetime.fromisoformat(dl_info['deadline_date'])
                    if deadline_date.tzinfo is None:
                        deadline_date = deadline_date.replace(tzinfo=self.tz)
                    
                    # Add deadline to user's account
                    self.db.add_deadline(
                        user_id=user_id,
                        title=dl_info['title'],
                        description=dl_info['description'],
                        deadline_date=deadline_date,
                        weight=dl_info['weight']
                    )
                    imported_count += 1
                    
                except Exception as e:
                    logger.error(f"Error importing deadline: {e}")
                    continue
            
            if imported_count > 0:
                text = f"✅ *Импорт успешно завершен!*\n\n"
                text += f"📊 Импортировано дедлайнов: {imported_count}\n"
                text += f"🕐 Время импорта: {datetime.now(self.tz).strftime('%d.%m.%Y %H:%M')}\n\n"
                text += "🔍 Посмотреть новые дедлайны можно в разделе \"Мои дедлайны\"."
                
                keyboard = [
                    [InlineKeyboardButton("📋 Мои дедлайны", callback_data="list_deadlines")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
                ]
            else:
                text = "❌ Не удалось импортировать дедлайны. Возможно, они повреждены."
                keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="advanced_menu")]]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Error importing deadlines from code: {e}")
            await update.message.reply_text(
                "❌ Не удалось обработать код доступа. Убедитесь, что код введен правильно."
            )
            return ENTER_ACCESS_CODE

    async def prompt_secret_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt user to enter secret code."""
        text = "🔑 Введите секретный код для получения доступа к редактированию дедлайнов:"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="advanced_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
        
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
                    
                    for dl in deadlines:  # Show max 10 deadlines
                        if dl['deadline_date'].tzinfo is None:
                            dl['deadline_date'] = dl['deadline_date'].replace(tzinfo=self.tz)
                        days_left = (dl['deadline_date'] - datetime.now(self.tz)).days
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
    
    async def add_deadline_back_to_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Возврат к шагу ввода названия."""
        # Просто вызываем функцию, которая начинает диалог
        await self.start_add_deadline(update, context)
        return ADD_TITLE

    async def add_deadline_back_to_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Возврат к шагу ввода описания."""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_title")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            "📄 Отлично! Теперь введите описание дедлайна "
            "(или отправьте /skip чтобы пропустить):",
            reply_markup=reply_markup
        )
        return ADD_DESCRIPTION
        
    async def add_deadline_back_to_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Возврат к шагу ввода даты."""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_description")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            "📅 Введите дату и время дедлайна в одном из форматов:\n\n"
            "• 2024-12-31 15:30\n"
            "• 31.12.2024 15:30\n"
            "• завтра 15:30\n"
            "• послезавтра 10:00",
            reply_markup=reply_markup
        )
        return ADD_DATE


def main():
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables!")
        return
    
    bot = DeadlinerBot()
    
    # Build application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add conversation handler for adding deadlines
    # Add conversation handler for adding deadlines
    add_deadline_conv = ConversationHandler(
        entry_points=[
            CommandHandler('add', bot.start_add_deadline),
            CallbackQueryHandler(bot.start_add_deadline, pattern="^add_deadline$")
        ],
        states={
            ADD_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.add_title),
                CallbackQueryHandler(bot.add_deadline_back, pattern="^main_menu$")
            ],
            ADD_DESCRIPTION: [
                MessageHandler(filters.TEXT, bot.add_description),
                CallbackQueryHandler(bot.add_deadline_back_to_title, pattern="^back_to_title$")
            ],
            ADD_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.add_date),
                CallbackQueryHandler(bot.add_deadline_back_to_description, pattern="^back_to_description$")
            ],
            ADD_WEIGHT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.add_weight),
                CallbackQueryHandler(bot.add_deadline_back_to_date, pattern="^back_to_date$")
            ]
        },
        fallbacks=[CommandHandler('cancel', bot.cancel)]
    )
    
    # Add conversation handler for notification times
    notification_time_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(bot.set_notification_times, pattern="^set_notification_times$")
        ],
        states={
            SET_NOTIFICATION_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.save_notification_times)]
        },
        fallbacks=[CommandHandler('cancel', bot.cancel)]
    )
    
    # Add conversation handler for deadline editing
    edit_deadline_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(bot.start_edit_deadline, pattern=r"^edit_\d+$")
        ],
        states={
            EDIT_DEADLINE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.save_deadline_weight),
                CallbackQueryHandler(bot.edit_deadline_back, pattern="^detail_")
            ]
        },
        fallbacks=[CommandHandler('cancel', bot.cancel)]
    )
    
    # Add conversation handler for access code import
    access_code_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(bot.prompt_access_code, pattern="^enter_code$")
        ],
        states={
            ENTER_ACCESS_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.import_deadlines_from_code),
                CallbackQueryHandler(bot.advanced_menu, pattern="^advanced_menu$")
            ]
        },
        fallbacks=[CallbackQueryHandler(bot.advanced_menu, pattern="^advanced_menu$")]
    )
    
    # Add handlers
    application.add_handler(CommandHandler('start', bot.start))
    application.add_handler(CommandHandler('help', bot.help_command))
    application.add_handler(CommandHandler('list', bot.list_deadlines))
    application.add_handler(CommandHandler('export', bot.export_deadlines))
    application.add_handler(CommandHandler('code', bot.prompt_secret_code))
    application.add_handler(add_deadline_conv)
    application.add_handler(notification_time_conv)
    application.add_handler(edit_deadline_conv)
    application.add_handler(access_code_conv)
    application.add_handler(CallbackQueryHandler(bot.button_handler))
    application.add_handler(MessageHandler(filters.TEXT, bot.check_secret_code), group=1)
    application.add_handler(MessageHandler(filters.ALL, bot.handle_group_message), group=2)
    
    # Start scheduler
    bot.scheduler.start(application.bot)
    
    logger.info("Bot started successfully!")
    application.run_polling()


if __name__ == '__main__':
    main()