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
        
        # Also check for group notifications (e.g., at specific times like 10:00)
        if current_hour_minute in ['10:00', '16:00', '20:00'] and current_weekday in range(7):  # Daily at specific times
            await self.check_and_send_group_notifications()
    
    async def send_user_notifications(self, user_id: int):
        """Send notifications to a specific user."""
        try:
            # Use the bot's unified method to get the exact same content as "My deadlines"
            deadline_content = self.bot.generate_deadline_list_text(user_id, include_header=False)
            
            if deadline_content == "Дедлайнов нет":
                return  # No deadlines to notify about
            
            # Send notification with exact same format as "My deadlines"
            await self._send_notification(user_id, deadline_content)
            
        except Exception as e:
            logger.error(f"Error sending notifications to user {user_id}: {e}")
    
    async def check_and_send_group_notifications(self):
        """Check and send notifications for group deadlines."""
        try:
            # Get all groups
            groups = self.db.get_all_groups()
            logger.info(f"Checking {len(groups)} groups for deadline notifications")
            
            for group_id in groups:
                await self.send_group_notifications(group_id)
                
        except Exception as e:
            logger.error(f"Error checking group notifications: {e}")
    
    async def send_group_notifications(self, group_id: int):
        """Send notifications to a specific group."""
        try:
            # Get group deadlines
            deadlines = self.db.get_group_deadlines(group_id)
            
            if not deadlines:
                return  # No deadlines to notify about
            
            # Filter to only upcoming deadlines (within next 7 days)
            current_time = datetime.now(self.tz)
            upcoming_deadlines = []
            
            for deadline in deadlines:
                if deadline['deadline_date'].tzinfo is None:
                    deadline['deadline_date'] = deadline['deadline_date'].replace(tzinfo=self.tz)
                
                time_until = deadline['deadline_date'] - current_time
                if 0 <= time_until.total_seconds() <= 7 * 24 * 3600:  # Within 7 days
                    upcoming_deadlines.append(deadline)
            
            if not upcoming_deadlines:
                return  # No upcoming deadlines
            
            # Format deadline content similar to the bot's format
            deadline_content = self._format_group_deadlines(upcoming_deadlines)
            
            # Send notification to group
            await self._send_group_notification(group_id, deadline_content)
            
        except Exception as e:
            logger.error(f"Error sending notifications to group {group_id}: {e}")
    
    def _format_group_deadlines(self, deadlines):
        """Format group deadlines for notification display."""
        from importance_calculator import get_weight_emoji
        
        text = ""
        current_time = datetime.now(self.tz)
        
        # Sort by deadline date
        deadlines.sort(key=lambda x: x['deadline_date'])
        
        for i, deadline in enumerate(deadlines[:5], 1):  # Show max 5 deadlines
            time_delta = deadline['deadline_date'] - current_time
            days_left = time_delta.days
            
            if days_left > 0:
                time_left = f"({days_left} д.)"
            elif days_left == 0:
                time_left = "(сегодня)"
            else:
                time_left = f"**(просрочено {abs(days_left)} д.)**"
            
            weight_emoji = get_weight_emoji(deadline['weight'])
            text += f"{i}. {weight_emoji} *{deadline['title']}* {time_left}\n"
            text += f"📅 {deadline['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n\n"
        
        return text
    
    async def _send_group_notification(self, group_id: int, deadline_content: str):
        """Send notification message to group."""
        text = "📋 *Напоминание о дедлайнах группы*\n\n"
        text += deadline_content
        
        try:
            await self.bot.send_message(
                chat_id=group_id,
                text=text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send group notification to {group_id}: {e}")
    
    async def send_test_notification(self, user_id: int):
        """Send a test notification to verify the system is working."""
        try:
            # Use the bot's unified method to get the exact same content as "My deadlines"
            deadline_content = self.bot.generate_deadline_list_text(user_id, include_header=False)
            
            if deadline_content == "Дедлайнов нет":
                return False  # No deadlines to notify about
            
            # Send test notification with exact same content as regular notifications
            await self._send_test_notification_message(user_id, deadline_content)
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending test notification to user {user_id}: {e}")
            return False
    
    async def _send_test_notification_message(self, user_id: int, deadline_content: str):
        """Send the actual test notification message."""
        text = "🧪 *ТЕСТОВОЕ УВЕДОМЛЕНИЕ*\n\n"
        text += "✅ Система уведомлений работает правильно!\n\n"
        text += deadline_content
        
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
    
    async def _send_notification(self, user_id: int, deadline_content: str):
        """Send notification message using the unified format."""
        text = "⏰ *Напоминание о дедлайнах*\n\n"
        text += deadline_content
        
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
            logger.error(f"Failed to send notification to {user_id}: {e}")
    
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