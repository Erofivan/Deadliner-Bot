#!/usr/bin/env python3
"""Simple test without external dependencies."""
import os
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

def test_basic_database():
    """Test basic database operations without external deps."""
    print("🗄️  Testing basic database operations...")
    
    try:
        # Create test database
        conn = sqlite3.connect('test_deadlines.db')
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                has_access INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                deadline_date TIMESTAMP NOT NULL,
                weight TEXT NOT NULL DEFAULT 'normal',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Test operations
        cursor.execute('INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)', 
                      (123, 'testuser', 'Test User'))
        
        deadline_date = (datetime.now() + timedelta(days=1)).isoformat()
        cursor.execute('''
            INSERT INTO deadlines (user_id, title, description, deadline_date, weight)
            VALUES (?, ?, ?, ?, ?)
        ''', (123, 'Test Deadline', 'Test Description', deadline_date, 'normal'))
        
        # Verify data
        cursor.execute('SELECT COUNT(*) FROM users WHERE user_id = 123')
        user_count = cursor.fetchone()[0]
        assert user_count == 1, "Should have one user"
        
        cursor.execute('SELECT COUNT(*) FROM deadlines WHERE user_id = 123')
        deadline_count = cursor.fetchone()[0]
        assert deadline_count == 1, "Should have one deadline"
        
        conn.close()
        os.remove('test_deadlines.db')
        
        print("✅ Basic database test passed")
        return True
        
    except Exception as e:
        print(f"❌ Basic database test failed: {e}")
        if os.path.exists('test_deadlines.db'):
            os.remove('test_deadlines.db')
        return False

def test_date_parsing():
    """Test date parsing logic."""
    print("📅 Testing date parsing...")
    
    try:
        import re
        
        def parse_date_simple(date_text: str) -> datetime:
            """Simplified date parsing for testing."""
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
                hour, minute = 12, 0
            
            if base_date:
                return base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Parse absolute dates
            date_patterns = [
                r'(\d{4})-(\d{1,2})-(\d{1,2})',  # YYYY-MM-DD
                r'(\d{1,2})\.(\d{1,2})\.(\d{4})', # DD.MM.YYYY
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, date_text)
                if match:
                    if pattern.startswith(r'(\d{4})'):
                        year, month, day = map(int, match.groups())
                    else:
                        day, month, year = map(int, match.groups())
                    
                    return datetime(year, month, day, hour, minute)
            
            raise ValueError("Invalid date format")
        
        # Test cases
        test_cases = [
            "завтра 15:30",
            "послезавтра 10:00", 
            "2024-12-31 15:30",
            "31.12.2024 15:30"
        ]
        
        for test_case in test_cases:
            result = parse_date_simple(test_case)
            assert isinstance(result, datetime), f"Should return datetime for {test_case}"
        
        print("✅ Date parsing test passed")
        return True
        
    except Exception as e:
        print(f"❌ Date parsing test failed: {e}")
        return False

def test_file_structure():
    """Test that all required files exist."""
    print("📁 Testing file structure...")
    
    required_files = [
        'bot.py',
        'database.py', 
        'scheduler.py',
        'config.py',
        'requirements.txt',
        'setup.py',
        '.env.example',
        'README.md'
    ]
    
    try:
        for filename in required_files:
            filepath = Path(filename)
            assert filepath.exists(), f"Missing required file: {filename}"
        
        print("✅ File structure test passed")
        return True
        
    except Exception as e:
        print(f"❌ File structure test failed: {e}")
        return False

def main():
    """Run basic tests."""
    print("🧪 Running Basic Deadliner Bot Tests")
    print("=" * 40)
    
    tests = [
        test_file_structure,
        test_basic_database,
        test_date_parsing
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            failed += 1
        print()
    
    print("=" * 40)
    print(f"✅ Tests passed: {passed}")
    print(f"❌ Tests failed: {failed}")
    
    if failed == 0:
        print("🎉 All basic tests passed!")
        print("\nNext steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Set up .env file with bot token")
        print("3. Run: python bot.py")
        return True
    else:
        print("💥 Some tests failed!")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)