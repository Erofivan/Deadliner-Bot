"""Importance calculation utilities for deadlines."""
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict


def calculate_importance_score(weight: int, deadline_date: datetime) -> float:
    """
    Рассчитывает приоритет задачи по часовой многофазной формуле срочности.
    Формула крайне чувствительна к задачам, до которых осталось менее 3 дней.
    """
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    if deadline_date.tzinfo is None:
        deadline_date = deadline_date.replace(tzinfo=ZoneInfo("Europe/Moscow"))

    time_delta = deadline_date - now
    hours_remaining = time_delta.total_seconds() / 3600

    if hours_remaining < 0:
        # Просроченные задачи получают огромный приоритет + бонус от веса
        return 100000 + int(weight)
    
    # Чтобы избежать деления на ноль, если осталось меньше часа
    if hours_remaining == 0:
        hours_remaining = 0.001

    try:
        base_weight = int(weight)
    except (ValueError, TypeError):
        base_weight = 5

    # Определение коэффициента в зависимости от зоны (в часах)
    zone_coefficient = 5.0  # 🔵 Зона планирования (> 504 часов)

    if hours_remaining <= 72:
        # 🔴 Критическая зона (<= 3 дней)
        zone_coefficient = 2000.0
    elif hours_remaining <= 504:
        # 🟡 Зона внимания (<= 21 дня)
        zone_coefficient = 200.0
    
    # Формула: Вес * (Коэффициент / (Часы + 1))
    total_score = base_weight * (zone_coefficient / (hours_remaining + 1))

    return round(total_score, 2)


def sort_deadlines_by_importance(deadlines: List[Dict]) -> List[Dict]:
    """
    Sort deadlines by calculated importance score.
    
    Args:
        deadlines: List of deadline dictionaries
        
    Returns:
        Sorted list of deadlines (most important first)
    """
    def get_importance(deadline):
        return calculate_importance_score(
            deadline['weight'], 
            deadline['deadline_date']
        )
    
    return sorted(deadlines, key=get_importance, reverse=True)


def get_importance_description(weight, deadline_date: datetime) -> str:
    """
    Get human-readable description of importance level.
    
    Args:
        weight: Importance weight from 0-10 (can be int or str)
        deadline_date: The deadline date
        
    Returns:
        Description string
    """
    score = calculate_importance_score(weight, deadline_date)
    
    if score >= 25:
        return "🔥 Критически важно"
    elif score >= 15:
        return "🚨 Очень срочно"
    elif score >= 10:
        return "⚡ Срочно"
    elif score >= 7:
        return "⏰ Важно"
    elif score >= 4:
        return "📝 Обычно"
    else:
        return "🔵 Низкий приоритет"


def get_weight_emoji(weight) -> str:
    """Get emoji representation for weight value."""
    try:
        weight_int = int(weight)
    except (ValueError, TypeError):
        weight_int = 5  # Default to medium if conversion fails
    
    if weight_int >= 9:
        return "🔴"  # Critical
    elif weight_int >= 7:
        return "🟠"  # High
    elif weight_int >= 5:
        return "🟡"  # Medium
    elif weight_int >= 3:
        return "🔵"  # Low
    else:
        return "⚪"  # Very low