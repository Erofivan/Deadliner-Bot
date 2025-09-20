#!/usr/bin/env python3
"""
Test script for the new editing functionality.
Tests the new 4-button editing flow.
"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from bot import DeadlinerBot
from database import Database
from unittest.mock import AsyncMock, MagicMock

def test_editing_flow():
    """Test the new editing flow."""
    print("🧪 Testing new editing flow...")
    
    try:
        # Initialize bot
        bot = DeadlinerBot()
        
        # Test that new functions exist
        assert hasattr(bot, 'show_edit_options'), "show_edit_options function exists"
        assert hasattr(bot, 'start_edit_title'), "start_edit_title function exists"
        assert hasattr(bot, 'start_edit_description'), "start_edit_description function exists"
        assert hasattr(bot, 'start_edit_date'), "start_edit_date function exists"
        assert hasattr(bot, 'start_edit_weight_only'), "start_edit_weight_only function exists"
        
        print("✅ All new editing functions exist")
        
        # Test database operations work
        db = Database()
        user_id = 12345
        
        # Add test user and deadline
        db.add_user(user_id, "testuser", "Test User")
        db.grant_access(user_id)
        
        # Add test deadline
        test_date = datetime.now() + timedelta(days=1)
        deadline_id = db.add_deadline(user_id, "Test Deadline", "Test Description", test_date, 5)
        
        print(f"✅ Test deadline created with ID: {deadline_id}")
        
        # Test individual updates
        success = db.update_deadline(deadline_id, user_id, title="Updated Title")
        assert success, "Title update should succeed"
        
        success = db.update_deadline(deadline_id, user_id, description="Updated Description") 
        assert success, "Description update should succeed"
        
        success = db.update_deadline(deadline_id, user_id, weight=8)
        assert success, "Weight update should succeed"
        
        success = db.update_deadline(deadline_id, user_id, deadline_date=test_date + timedelta(hours=2))
        assert success, "Date update should succeed"
        
        print("✅ Individual field updates work correctly")
        
        # Test display settings
        settings = db.get_user_display_settings(user_id)
        assert isinstance(settings, dict), "Display settings should be a dict"
        assert 'show_emojis' in settings, "Should have emoji setting"
        
        print("✅ Display settings retrieval works")
        
        # Clean up test data
        os.remove('deadlines.db')
        
        print("✅ All editing flow tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Editing flow test failed: {e}")
        return False

def test_scheduler_imports():
    """Test that scheduler imports work."""
    print("🧪 Testing scheduler imports...")
    
    try:
        from scheduler import ReminderScheduler
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        print("✅ Scheduler and Telegram imports work")
        return True
        
    except Exception as e:
        print(f"❌ Scheduler import test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Running New Features Tests")
    print("=" * 35)
    
    tests = [
        test_editing_flow,
        test_scheduler_imports
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
    
    print("=" * 35)
    print(f"✅ Tests passed: {passed}")
    print(f"❌ Tests failed: {failed}")
    
    if failed == 0:
        print("🎉 All new feature tests passed!")
        return True
    else:
        print("💥 Some tests failed!")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)