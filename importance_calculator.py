"""Importance calculation utilities for deadlines."""
import math
from datetime import datetime, timedelta
from typing import List, Dict


def calculate_importance_score(weight: int, deadline_date: datetime) -> float:
    """
    Calculate importance score based on weight (0-10) and time remaining.
    
    Uses a formula that combines:
    - Base importance from weight (0-10)
    - Time urgency factor that increases exponentially as deadline approaches
    
    Args:
        weight: Importance weight from 0-10 (10 being most important)
        deadline_date: The deadline date
        
    Returns:
        Importance score (higher = more important)
    """
    now = datetime.now()
    time_delta = deadline_date - now
    
    # Convert to hours remaining (can be negative for overdue)
    hours_remaining = time_delta.total_seconds() / 3600
    
    # Base importance from weight (0-10 scale)
    base_importance = weight
    
    # Time urgency factor using exponential decay
    # This makes tasks become much more urgent as deadline approaches
    if hours_remaining > 0:
        # For future deadlines, urgency increases exponentially as time decreases
        # Using formula: urgency = 10 * exp(-hours_remaining / 24)
        # This gives high urgency for tasks due within hours, moderate for days
        urgency_factor = 10 * math.exp(-hours_remaining / 24)
    else:
        # For overdue tasks, add significant penalty
        overdue_hours = abs(hours_remaining)
        urgency_factor = 20 + math.log(1 + overdue_hours)  # Logarithmic increase
    
    # Combine base importance with urgency
    # Weight the base importance more heavily to avoid low-importance tasks
    # from always dominating just because they're urgent
    total_score = (base_importance * 2) + urgency_factor
    
    return total_score


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


def get_importance_description(weight: int, deadline_date: datetime) -> str:
    """
    Get human-readable description of importance level.
    
    Args:
        weight: Importance weight from 0-10
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


def get_weight_emoji(weight: int) -> str:
    """Get emoji representation for weight value."""
    if weight >= 9:
        return "🔴"  # Critical
    elif weight >= 7:
        return "🟠"  # High
    elif weight >= 5:
        return "🟡"  # Medium
    elif weight >= 3:
        return "🔵"  # Low
    else:
        return "⚪"  # Very low