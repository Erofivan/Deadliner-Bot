"""Scheduler for sending periodic reminders about deadlines."""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from importance_calculator import calculate_importance_score, get_weight_emoji

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """Handles scheduling and sending reminder notifications."""
    
    def __init__(self, database):
        self.db = database
        self.scheduler = AsyncIOScheduler()
        self.bot = None
        self.tz = ZoneInfo("Europe/Moscow")
    
    def start(self, bot):
        """Start the scheduler with bot instance."""
        self.bot = bot
        
        # Schedule reminder checks based on user settings
        # Check every minute to see who should get notifications  
        self.scheduler.add_job(
            self.check_and_send_notifications,
            trigger='cron',
            minute='*',  # Every minute
            timezone=self.tz,  # Use Moscow timezone
            id="minute_notification_check",
            name="Check and send notifications",
            misfire_grace_time=300  # 5 minutes grace time
        )
        
        self.scheduler.start()
        logger.info("Reminder scheduler started")
    
    async def check_and_send_notifications(self):
        """Check if any users should receive notifications at this time."""
        current_time = datetime.now(self.tz)  # Use Moscow timezone
        current_hour_minute = current_time.strftime('%H:%M')
        current_weekday = current_time.weekday()  # 0 = Monday
        
        logger.info(f"Checking notifications for {current_hour_minute} on weekday {current_weekday} (Moscow time)")
        
        # Get all users with their notification settings
        all_users = self.db.get_all_users_for_notifications()
        logger.info(f"Found {len(all_users)} users with deadlines")
        
        for user_id in all_users:
            settings = self.db.get_user_notification_settings(user_id)
            logger.debug(f"User {user_id} notification settings: times={settings['times']}, days={settings['days']}")
            
            # Check if current time matches user's notification times
            should_notify = False
            for notification_time in settings['times']:
                if notification_time == current_hour_minute and current_weekday in settings['days']:
                    should_notify = True
                    logger.info(f"Should notify user {user_id} at {current_hour_minute}")
                    break
            
            if should_notify:
                await self.send_user_notifications(user_id)
    
    async def send_user_notifications(self, user_id: int):
        """Send notifications to a specific user."""
        try:
            # Get active deadlines for this user
            deadlines = self.db.get_user_deadlines(user_id, include_completed=False)
            
            if not deadlines:
                return  # No deadlines to notify about
            
            # Calculate importance scores and filter for notification
            high_importance_deadlines = []
            urgent_deadlines = []
            
            for deadline in deadlines:
                # Ensure deadline_date has timezone information
                if deadline['deadline_date'].tzinfo is None:
                    deadline['deadline_date'] = deadline['deadline_date'].replace(tzinfo=self.tz)
                    
                importance_score = calculate_importance_score(deadline['weight'], deadline['deadline_date'])
                
                # Send notifications for high importance items (score > 5)
                # or items that are due soon (within 24 hours)
                time_until = deadline['deadline_date'] - datetime.now(self.tz)
                hours_until = time_until.total_seconds() / 3600
                
                if importance_score > 10 or hours_until < 1:
                    urgent_deadlines.append(deadline)
                elif importance_score > 5 or hours_until < 24:
                    high_importance_deadlines.append(deadline)
            
            # Send notifications if there are relevant deadlines
            if urgent_deadlines:
                await self._send_urgent_notification(user_id, urgent_deadlines)
            elif high_importance_deadlines:
                await self._send_regular_notification(user_id, high_importance_deadlines)
            
        except Exception as e:
            logger.error(f"Error sending notifications to user {user_id}: {e}")
    
    async def send_test_notification(self, user_id: int):
        """Send a test notification to verify the system is working."""
        try:
            # Get active deadlines for this user
            deadlines = self.db.get_user_deadlines(user_id, include_completed=False)
            
            if not deadlines:
                return False  # No deadlines to notify about
            
            # For testing, we'll send notification about the most important deadline
            # or the one that's due soonest, regardless of normal filtering criteria
            test_deadlines = []
            
            for deadline in deadlines:
                # Ensure deadline_date has timezone information
                if deadline['deadline_date'].tzinfo is None:
                    deadline['deadline_date'] = deadline['deadline_date'].replace(tzinfo=self.tz)
                test_deadlines.append(deadline)
            
            # Sort by importance score to get the most relevant for testing
            from importance_calculator import calculate_importance_score
            test_deadlines.sort(
                key=lambda d: calculate_importance_score(d['weight'], d['deadline_date']), 
                reverse=True
            )
            
            # Take the top deadline for test notification
            top_deadline = test_deadlines[0]
            await self._send_test_notification_message(user_id, top_deadline)
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending test notification to user {user_id}: {e}")
            return False
    
    async def _send_test_notification_message(self, user_id: int, deadline: dict):
        """Send the actual test notification message."""
        text = "🧪 *ТЕСТОВОЕ УВЕДОМЛЕНИЕ*\n\n"
        text += "✅ Система уведомлений работает правильно!\n\n"
        
        # Get user display settings to use standardized formatting
        display_settings = self.db.get_user_display_settings(user_id)
        
        # Format the deadline using the same method as regular notifications
        formatted_deadline = self.bot.format_deadline_for_display(deadline, display_settings, 1)
        text += "📝 *Пример уведомления с вашим дедлайном:*\n"
        text += formatted_deadline
        
        text += "\n💡 *Примечание:* Это тестовое уведомление. Обычные уведомления приходят согласно вашим настройкам времени и важности дедлайнов."
        
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send test notification to {user_id}: {e}")
    
    async def _send_urgent_notification(self, user_id: int, deadlines: list):
        """Send urgent notification message."""
        text = "🚨 *СРОЧНЫЕ НАПОМИНАНИЯ*\n\n"
        
        # Get user display settings to use standardized formatting
        display_settings = self.db.get_user_display_settings(user_id)
        
        for i, deadline in enumerate(deadlines[:5], 1):  # Limit to 5 most urgent
            # Use the same formatting as "My deadlines"
            formatted_deadline = self.bot.format_deadline_for_display(deadline, display_settings, i)
            text += formatted_deadline
        
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send urgent notification to {user_id}: {e}")
    
    async def _send_regular_notification(self, user_id: int, deadlines: list):
        """Send regular notification message."""
        text = "⏰ *Напоминание о дедлайнах*\n\n"
        
        # Get user display settings to use standardized formatting
        display_settings = self.db.get_user_display_settings(user_id)
        
        for i, deadline in enumerate(deadlines[:3], 1):  # Limit to 3 most important
            # Use the same formatting as "My deadlines"
            formatted_deadline = self.bot.format_deadline_for_display(deadline, display_settings, i)
            text += formatted_deadline
        
        if len(deadlines) > 3:
            text += f"И еще {len(deadlines) - 3} дедлайнов..."
        
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send regular notification to {user_id}: {e}")
    
    async def _send_group_reminders(self, deadline: dict, time_until: timedelta):
        """Send urgent reminders to all groups."""
        groups = self.db.get_all_groups()
        
        if not groups or time_until.total_seconds() > 3600:  # Only for deadlines within 1 hour
            return
        
        weight_emoji = get_weight_emoji(deadline['weight'])
        
        hours = int(time_until.total_seconds() // 3600)
        if hours > 0:
            time_text = f"через {hours} ч."
        else:
            minutes = int(time_until.total_seconds() // 60)
            time_text = f"через {minutes} мин." if minutes > 0 else "ПРЯМО СЕЙЧАС"
        
        message = f"🚨 *СРОЧНОЕ УВЕДОМЛЕНИЕ*\n\n"
        message += f"{weight_emoji} *{deadline['title']}*\n"
        message += f"⏳ {time_text}\n"
        message += f"📅 {deadline['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n"
        
        if deadline['description']:
            message += f"📄 {deadline['description']}"
        
        for group_id in groups:
            try:
                await self.bot.send_message(
                    chat_id=group_id,
                    text=message,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send group reminder to {group_id}: {e}")
    
    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Reminder scheduler stopped")