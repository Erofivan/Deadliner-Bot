"""Database operations for the Deadliner bot."""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from config import DATABASE_PATH


class Database:
    """Handles all database operations for deadlines and users."""
    
    def __init__(self):
        self.init_db()
    
    def init_db(self):
        """Initialize database tables."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    has_access INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Deadlines table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS deadlines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    title TEXT NOT NULL,
                    description TEXT,
                    deadline_date TIMESTAMP NOT NULL,
                    weight INTEGER NOT NULL DEFAULT 5,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Add user_notification_settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_notification_settings (
                    user_id INTEGER PRIMARY KEY,
                    notification_times TEXT DEFAULT '[]',
                    notification_days TEXT DEFAULT '[0,1,2,3,4,5,6]',
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Groups table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None):
        """Add or update user in database."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name)
                VALUES (?, ?, ?)
            ''', (user_id, username, first_name))
            conn.commit()
    
    def grant_access(self, user_id: int):
        """Grant access to a user."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET has_access = 1 WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
    
    def has_access(self, user_id: int) -> bool:
        """Check if user has access."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT has_access FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return bool(result and result[0])
    
    def add_deadline(self, user_id: int, title: str, description: str, 
                    deadline_date: datetime, weight: int) -> int:
        """Add a new deadline."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO deadlines (user_id, title, description, deadline_date, weight)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, title, description, deadline_date, weight))
            conn.commit()
            return cursor.lastrowid
    
    def get_user_deadlines(self, user_id: int, include_completed: bool = False) -> List[Dict]:
        """Get all deadlines for a user."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT id, title, description, deadline_date, weight, created_at, completed
                FROM deadlines
                WHERE user_id = ?
            '''
            
            if not include_completed:
                query += ' AND completed = 0'
            
            query += ' ORDER BY deadline_date ASC'
            
            cursor.execute(query, (user_id,))
            rows = cursor.fetchall()
            
            deadlines = []
            for row in rows:
                deadlines.append({
                    'id': row[0],
                    'title': row[1],
                    'description': row[2],
                    'deadline_date': datetime.fromisoformat(row[3]),
                    'weight': row[4],
                    'created_at': datetime.fromisoformat(row[5]),
                    'completed': bool(row[6])
                })
            
            return deadlines
    
    def get_all_active_deadlines(self) -> List[Dict]:
        """Get all active deadlines for reminders."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT d.id, d.user_id, d.title, d.description, d.deadline_date, d.weight,
                       u.username, u.first_name
                FROM deadlines d
                JOIN users u ON d.user_id = u.user_id
                WHERE d.completed = 0 AND d.deadline_date > datetime('now')
                ORDER BY d.deadline_date ASC
            ''')
            
            rows = cursor.fetchall()
            deadlines = []
            
            for row in rows:
                deadlines.append({
                    'id': row[0],
                    'user_id': row[1],
                    'title': row[2],
                    'description': row[3],
                    'deadline_date': datetime.fromisoformat(row[4]),
                    'weight': row[5],
                    'username': row[6],
                    'first_name': row[7]
                })
            
            return deadlines
    
    def complete_deadline(self, deadline_id: int, user_id: int) -> bool:
        """Mark a deadline as completed."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE deadlines 
                SET completed = 1 
                WHERE id = ? AND user_id = ?
            ''', (deadline_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_deadline(self, deadline_id: int, user_id: int) -> bool:
        """Delete a deadline."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM deadlines 
                WHERE id = ? AND user_id = ?
            ''', (deadline_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def add_group(self, chat_id: int, title: str = None):
        """Add group to database."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO groups (chat_id, title)
                VALUES (?, ?)
            ''', (chat_id, title))
            conn.commit()
    
    def get_all_groups(self) -> List[int]:
        """Get all group chat IDs."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT chat_id FROM groups')
            return [row[0] for row in cursor.fetchall()]
    
    def get_user_notification_settings(self, user_id: int) -> Dict:
        """Get notification settings for a user."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT notification_times, notification_days 
                FROM user_notification_settings 
                WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            if result:
                return {
                    'times': json.loads(result[0]),
                    'days': json.loads(result[1])
                }
            else:
                # Return default settings
                return {
                    'times': ['10:00', '20:00'],
                    'days': [0, 1, 2, 3, 4, 5, 6]  # All days
                }
    
    def update_user_notification_settings(self, user_id: int, times: List[str], days: List[int]):
        """Update notification settings for a user."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO user_notification_settings 
                (user_id, notification_times, notification_days)
                VALUES (?, ?, ?)
            ''', (user_id, json.dumps(times), json.dumps(days)))
            conn.commit()
    
    def update_deadline(self, deadline_id: int, user_id: int, title: str = None, 
                       description: str = None, deadline_date: datetime = None, 
                       weight: int = None) -> bool:
        """Update a deadline."""
        updates = []
        params = []
        
        if title is not None:
            updates.append('title = ?')
            params.append(title)
        if description is not None:
            updates.append('description = ?')
            params.append(description)
        if deadline_date is not None:
            updates.append('deadline_date = ?')
            params.append(deadline_date)
        if weight is not None:
            updates.append('weight = ?')
            params.append(weight)
        
        if not updates:
            return False
        
        params.extend([deadline_id, user_id])
        
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                UPDATE deadlines 
                SET {', '.join(updates)}
                WHERE id = ? AND user_id = ?
            ''', params)
            conn.commit()
            return cursor.rowcount > 0
    
    def get_completed_deadlines(self, user_id: int) -> List[Dict]:
        """Get completed deadlines for a user."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, description, deadline_date, weight, created_at, completed
                FROM deadlines
                WHERE user_id = ? AND completed = 1
                ORDER BY completed DESC
            ''', (user_id,))
            
            deadlines = []
            for row in cursor.fetchall():
                deadlines.append({
                    'id': row[0],
                    'title': row[1],
                    'description': row[2],
                    'deadline_date': datetime.fromisoformat(row[3]),
                    'weight': row[4],
                    'created_at': datetime.fromisoformat(row[5]) if row[5] else None,
                    'completed': bool(row[6])
                })
            
            return deadlines
    
    def reopen_deadline(self, deadline_id: int, user_id: int) -> bool:
        """Reopen a completed deadline."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE deadlines 
                SET completed = 0 
                WHERE id = ? AND user_id = ?
            ''', (deadline_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_all_users_for_notifications(self) -> List[int]:
        """Get all user IDs that have deadlines."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT user_id 
                FROM deadlines 
                WHERE completed = 0
            ''')
            return [row[0] for row in cursor.fetchall()]