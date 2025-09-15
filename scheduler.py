"""Scheduler for sending periodic reminders about deadlines."""
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import REMINDER_INTERVALS

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """Handles scheduling and sending reminder notifications."""
    
    def __init__(self, database):
        self.db = database
        self.scheduler = AsyncIOScheduler()
        self.bot = None
    
    def start(self, bot):
        """Start the scheduler with bot instance."""
        self.bot = bot
        
        # Schedule reminders for each weight category
        for weight, interval_minutes in REMINDER_INTERVALS.items():
            self.scheduler.add_job(
                self.send_reminders,
                trigger=IntervalTrigger(minutes=interval_minutes),
                args=[weight],
                id=f"reminders_{weight}",
                name=f"Send {weight} reminders",
                misfire_grace_time=300  # 5 minutes grace time
            )
        
        # Schedule daily summary
        self.scheduler.add_job(
            self.send_daily_summary,
            trigger='cron',
            hour=9,  # 9 AM
            minute=0,
            id="daily_summary",
            name="Send daily summary",
            misfire_grace_time=3600  # 1 hour grace time
        )
        
        self.scheduler.start()
        logger.info("Reminder scheduler started")
    
    async def send_reminders(self, weight: str):
        """Send reminders for deadlines of specific weight."""
        try:
            deadlines = self.db.get_all_active_deadlines()
            now = datetime.now()
            
            for deadline in deadlines:
                if deadline['weight'] != weight:
                    continue
                
                # Calculate time until deadline
                time_until = deadline['deadline_date'] - now
                
                # Skip if deadline is too far in the future or already passed
                if time_until.total_seconds() < 0:
                    continue
                
                # Send reminder based on weight and time remaining
                should_send = self._should_send_reminder(deadline, time_until, weight)
                
                if should_send:
                    await self._send_reminder_message(deadline, time_until)
                    
                    # Also send to groups if deadline is urgent
                    if weight == 'urgent' and time_until.days <= 1:
                        await self._send_group_reminders(deadline, time_until)
        
        except Exception as e:
            logger.error(f"Error sending {weight} reminders: {e}")
    
    def _should_send_reminder(self, deadline: dict, time_until: timedelta, weight: str) -> bool:
        """Determine if a reminder should be sent."""
        hours_until = time_until.total_seconds() / 3600
        days_until = time_until.days
        
        # Different reminder rules based on weight
        if weight == 'urgent':
            # Send if less than 2 days remaining
            return hours_until <= 48
        elif weight == 'important':
            # Send if less than 3 days remaining
            return hours_until <= 72
        elif weight == 'normal':
            # Send if less than 1 week remaining
            return days_until <= 7
        elif weight == 'low':
            # Send if less than 2 weeks remaining
            return days_until <= 14
        
        return False
    
    async def _send_reminder_message(self, deadline: dict, time_until: timedelta):
        """Send reminder message to user."""
        if not self.bot:
            return
        
        user_id = deadline['user_id']
        
        # Format time remaining
        time_text = self._format_time_remaining(time_until)
        
        # Choose emoji and urgency text based on time remaining
        if time_until.days < 0:
            emoji = "🚨"
            urgency = "ПРОСРОЧЕН"
        elif time_until.total_seconds() < 3600:  # Less than 1 hour
            emoji = "🔥"
            urgency = "СРОЧНО"
        elif time_until.days < 1:
            emoji = "⚠️"
            urgency = "СЕГОДНЯ"
        elif time_until.days < 3:
            emoji = "⏰"
            urgency = "СКОРО"
        else:
            emoji = "📅"
            urgency = "НАПОМИНАНИЕ"
        
        weight_emoji = {
            'urgent': '🔴',
            'important': '🟠', 
            'normal': '🟡',
            'low': '🟢'
        }
        
        message = f"{emoji} *{urgency}*\n\n"
        message += f"{weight_emoji[deadline['weight']]} *{deadline['title']}*\n"
        message += f"⏳ {time_text}\n"
        message += f"📅 {deadline['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n"
        
        if deadline['description']:
            message += f"📄 {deadline['description']}\n"
        
        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='Markdown'
            )
            logger.info(f"Sent reminder for deadline {deadline['id']} to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send reminder to user {user_id}: {e}")
    
    async def _send_group_reminders(self, deadline: dict, time_until: timedelta):
        """Send urgent reminders to all groups."""
        if not self.bot:
            return
        
        groups = self.db.get_all_groups()
        time_text = self._format_time_remaining(time_until)
        
        message = f"🚨 *СРОЧНЫЙ ДЕДЛАЙН*\n\n"
        message += f"📝 {deadline['title']}\n"
        message += f"⏳ {time_text}\n"
        message += f"📅 {deadline['deadline_date'].strftime('%d.%m.%Y %H:%M')}\n"
        message += f"👤 @{deadline['username'] or deadline['first_name']}\n"
        
        if deadline['description']:
            message += f"📄 {deadline['description']}\n"
        
        for group_id in groups:
            try:
                await self.bot.send_message(
                    chat_id=group_id,
                    text=message,
                    parse_mode='Markdown'
                )
                logger.info(f"Sent group reminder for deadline {deadline['id']} to group {group_id}")
                
            except Exception as e:
                logger.error(f"Failed to send group reminder to {group_id}: {e}")
    
    async def send_daily_summary(self):
        """Send daily summary to all users."""
        if not self.bot:
            return
        
        try:
            deadlines = self.db.get_all_active_deadlines()
            now = datetime.now()
            
            # Group deadlines by user
            user_deadlines = {}
            for deadline in deadlines:
                user_id = deadline['user_id']
                if user_id not in user_deadlines:
                    user_deadlines[user_id] = []
                user_deadlines[user_id].append(deadline)
            
            # Send summary to each user
            for user_id, user_dls in user_deadlines.items():
                # Filter deadlines that are due soon
                urgent_deadlines = []
                upcoming_deadlines = []
                
                for dl in user_dls:
                    time_until = dl['deadline_date'] - now
                    if time_until.days <= 1:
                        urgent_deadlines.append(dl)
                    elif time_until.days <= 7:
                        upcoming_deadlines.append(dl)
                
                if urgent_deadlines or upcoming_deadlines:
                    await self._send_daily_summary_message(user_id, urgent_deadlines, upcoming_deadlines)
        
        except Exception as e:
            logger.error(f"Error sending daily summary: {e}")
    
    async def _send_daily_summary_message(self, user_id: int, urgent: list, upcoming: list):
        """Send daily summary message to user."""
        message = "🌅 *Ежедневная сводка дедлайнов*\n\n"
        
        if urgent:
            message += "🚨 *Срочные (сегодня-завтра):*\n"
            for dl in urgent:
                time_until = dl['deadline_date'] - datetime.now()
                time_text = self._format_time_remaining(time_until)
                message += f"• {dl['title']} - {time_text}\n"
            message += "\n"
        
        if upcoming:
            message += "📅 *На этой неделе:*\n"
            for dl in upcoming:
                message += f"• {dl['title']} - {dl['deadline_date'].strftime('%d.%m %H:%M')}\n"
            message += "\n"
        
        message += "Удачного дня! 🍀"
        
        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='Markdown'
            )
            logger.info(f"Sent daily summary to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send daily summary to user {user_id}: {e}")
    
    def _format_time_remaining(self, time_until: timedelta) -> str:
        """Format time remaining in human readable format."""
        if time_until.total_seconds() < 0:
            return "просрочено"
        
        days = time_until.days
        hours = time_until.seconds // 3600
        minutes = (time_until.seconds % 3600) // 60
        
        if days > 0:
            if days == 1:
                return f"1 день {hours}ч"
            elif days < 7:
                return f"{days} дней {hours}ч"
            else:
                weeks = days // 7
                remaining_days = days % 7
                if remaining_days > 0:
                    return f"{weeks} нед {remaining_days} дн"
                else:
                    return f"{weeks} недель"
        elif hours > 0:
            return f"{hours}ч {minutes}м"
        else:
            return f"{minutes} минут"
    
    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Reminder scheduler stopped")