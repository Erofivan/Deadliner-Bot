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
                    completed_at TIMESTAMP NULL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Add completed_at column to existing table if it doesn't exist
            try:
                cursor.execute('ALTER TABLE deadlines ADD COLUMN completed_at TIMESTAMP NULL')
            except sqlite3.OperationalError:
                # Column already exists
                pass








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

            # Access codes table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS access_codes (
                    code TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            ''')

            # User display settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_display_settings (
                    user_id INTEGER PRIMARY KEY,
                    show_remaining_time INTEGER DEFAULT 1,
                    show_description INTEGER DEFAULT 1,
                    show_importance INTEGER DEFAULT 1,
                    show_weight INTEGER DEFAULT 1,
                    show_emojis INTEGER DEFAULT 1,
                    show_date INTEGER DEFAULT 1,
                    show_time_tracking INTEGER DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Add show_time_tracking column to existing table if it doesn't exist
            try:
                cursor.execute('ALTER TABLE user_display_settings ADD COLUMN show_time_tracking INTEGER DEFAULT 1')
            except sqlite3.OperationalError:
                # Column already exists
                pass

            # Add sort_preference column to existing table if it doesn't exist
            try:
                cursor.execute('ALTER TABLE user_display_settings ADD COLUMN sort_preference TEXT DEFAULT "importance_desc"')
            except sqlite3.OperationalError:
                # Column already exists
                pass

            conn.commit()

    def add_user(self, user_id: int, username: str = None, first_name: str = None):
        """Add or update user in database."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name)
                VALUES (?, ?, ?)
            ''', (user_id, username, first_name))

            # Initialize default notification settings if not exists
            cursor.execute('''
                INSERT OR IGNORE INTO user_notification_settings (user_id, notification_times, notification_days)
                VALUES (?, ?, ?)
            ''', (user_id, '["10:00", "20:00"]', '[0,1,2,3,4,5,6]'))

            # Initialize default display settings
            cursor.execute('''
                INSERT OR IGNORE INTO user_display_settings 
                (user_id, show_remaining_time, show_description, show_importance, show_weight, show_emojis, show_date, show_time_tracking)
                VALUES (?, 1, 1, 1, 1, 1, 1, 1)
            ''', (user_id,))

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
                SET completed = 1, completed_at = datetime('now')
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
                SET completed = 0, completed_at = NULL
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

    def store_access_code(self, code: str, data: str) -> bool:
        """Store access code with deadline data."""
        from datetime import datetime, timedelta

        # Set expiration to 7 days from now
        expires_at = datetime.now() + timedelta(days=7)

        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO access_codes (code, data, expires_at)
                VALUES (?, ?, ?)
            ''', (code, data, expires_at))
            conn.commit()
            return cursor.rowcount > 0

    def get_access_code_data(self, code: str) -> Optional[str]:
        """Get access code data if it exists and is not expired."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT data FROM access_codes 
                WHERE code = ? AND (expires_at IS NULL OR expires_at > datetime('now'))
            ''', (code,))
            result = cursor.fetchone()
            return result[0] if result else None

    def cleanup_expired_access_codes(self) -> int:
        """Remove expired access codes."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM access_codes 
                WHERE expires_at IS NOT NULL AND expires_at < datetime('now')
            ''')
            conn.commit()
            return cursor.rowcount

    def get_user_display_settings(self, user_id: int) -> Dict:
        """Get display settings for a user."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT show_remaining_time, show_description, show_importance, 
                       show_weight, show_emojis, show_date, show_time_tracking, sort_preference
                FROM user_display_settings 
                WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            if result:
                return {
                    'show_remaining_time': bool(result[0]),
                    'show_description': bool(result[1]),
                    'show_importance': bool(result[2]),
                    'show_weight': bool(result[3]),
                    'show_emojis': bool(result[4]),
                    'show_date': bool(result[5]),
                    'show_time_tracking': bool(result[6]) if len(result) > 6 else True,
                    'sort_preference': result[7] if len(result) > 7 and result[7] else 'importance_desc'
                }
            else:
                # Return default settings
                return {
                    'show_remaining_time': True,
                    'show_description': True,
                    'show_importance': True,
                    'show_weight': True,
                    'show_emojis': True,
                    'show_date': True,
                    'show_time_tracking': True,
                    'sort_preference': 'importance_desc'
                }

    def update_user_display_setting(self, user_id: int, setting: str, value: bool):
        """Update a specific display setting for a user."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            # Ensure user exists in display settings
            cursor.execute('''
                INSERT OR IGNORE INTO user_display_settings 
                (user_id, show_remaining_time, show_description, show_importance, show_weight, show_emojis, show_date, show_time_tracking)
                VALUES (?, 1, 1, 1, 1, 1, 1, 1)
            ''', (user_id,))

            # Update the specific setting
            cursor.execute(f'''
                UPDATE user_display_settings 
                SET {setting} = ?
                WHERE user_id = ?
            ''', (int(value), user_id))
            conn.commit()

    def update_user_sort_preference(self, user_id: int, sort_preference: str):
        """Update sort preference for a user."""
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            # Ensure user exists in display settings
            cursor.execute('''
                INSERT OR IGNORE INTO user_display_settings 
                (user_id, show_remaining_time, show_description, show_importance, show_weight, show_emojis, show_date, show_time_tracking, sort_preference)
                VALUES (?, 1, 1, 1, 1, 1, 1, 1, ?)
            ''', (user_id, sort_preference))

            # Update the sort preference
            cursor.execute('''
                UPDATE user_display_settings 
                SET sort_preference = ?
                WHERE user_id = ?
            ''', (sort_preference, user_id))