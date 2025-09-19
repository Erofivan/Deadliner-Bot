#!/usr/bin/env python3
"""Test script for Deadliner Bot components."""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_database():
    """Test database functionality."""
    print("🗄️  Testing database functionality...")
    
    try:
        from database import Database
        
        # Create test database
        db = Database()
        print("✅ Database initialized")
        
        # Test user operations
        test_user_id = 123456789
        db.add_user(test_user_id, "testuser", "Test User")
        print("✅ User added")
        
        # Test access control
        assert not db.has_access(test_user_id), "User should not have access initially"
        db.grant_access(test_user_id)
        assert db.has_access(test_user_id), "User should have access after granting"
        print("✅ Access control working")
        
        # Test deadline operations
        deadline_date = datetime.now() + timedelta(days=1)
        deadline_id = db.add_deadline(
            test_user_id, 
            "Test Deadline", 
            "This is a test", 
            deadline_date, 
            5  # Use integer weight instead of string
        )
        print(f"✅ Deadline added with ID: {deadline_id}")
        
        # Test retrieving deadlines
        deadlines = db.get_user_deadlines(test_user_id)
        assert len(deadlines) == 1, "Should have one deadline"
        assert deadlines[0]['title'] == "Test Deadline", "Title should match"
        print("✅ Deadline retrieval working")
        
        # Test completion
        success = db.complete_deadline(deadline_id, test_user_id)
        assert success, "Should successfully complete deadline"
        print("✅ Deadline completion working")
        
        # Clean up test database
        os.remove('deadlines.db')
        print("✅ Database test completed successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def test_config():
    """Test configuration loading."""
    print("⚙️  Testing configuration...")
    
    try:
        from config import REMINDER_INTERVALS
        
        assert isinstance(REMINDER_INTERVALS, dict), "REMINDER_INTERVALS should be a dict"
        assert 'urgent' in REMINDER_INTERVALS, "Should have urgent interval"
        print("✅ Configuration test passed")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

def test_scheduler():
    """Test scheduler initialization."""
    print("⏰ Testing scheduler...")
    
    try:
        from scheduler import ReminderScheduler
        from database import Database
        
        db = Database()
        scheduler = ReminderScheduler(db)
        
        assert scheduler.db is not None, "Scheduler should have database reference"
        print("✅ Scheduler initialization test passed")
        
        # Clean up
        if os.path.exists('deadlines.db'):
            os.remove('deadlines.db')
        
        return True
        
    except Exception as e:
        print(f"❌ Scheduler test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Running Deadliner Bot Tests")
    print("=" * 35)
    
    tests = [
        test_config,
        test_database, 
        test_scheduler
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
        print("🎉 All tests passed!")
        return True
    else:
        print("💥 Some tests failed!")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)