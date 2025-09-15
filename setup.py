#!/usr/bin/env python3
"""Setup script for Deadliner Bot."""
import os
import sys
from pathlib import Path

def create_env_file():
    """Create .env file if it doesn't exist."""
    env_path = Path('.env')
    env_example_path = Path('.env.example')
    
    if not env_path.exists() and env_example_path.exists():
        print("📁 Creating .env file...")
        env_content = env_example_path.read_text()
        env_path.write_text(env_content)
        print("✅ .env file created from .env.example")
        print("⚠️  Please edit .env file and add your BOT_TOKEN and SECRET_CODE")
        return False
    elif not env_path.exists():
        print("❌ No .env file found. Please create one with:")
        print("BOT_TOKEN=your_telegram_bot_token_here")
        print("SECRET_CODE=your_secret_code_here")
        return False
    
    return True

def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 7):
        print("❌ Python 3.7 or higher is required")
        return False
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} is compatible")
    return True

def install_requirements():
    """Install required packages."""
    try:
        import subprocess
        print("📦 Installing requirements...")
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], 
                              check=True, capture_output=True, text=True)
        print("✅ Requirements installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install requirements: {e}")
        print("Please run: pip install -r requirements.txt")
        return False

def main():
    """Main setup function."""
    print("🤖 Deadliner Bot Setup")
    print("=" * 25)
    
    # Check Python version
    if not check_python_version():
        return False
    
    # Install requirements
    if not install_requirements():
        return False
    
    # Create env file
    if not create_env_file():
        return False
    
    print("\n🎉 Setup completed!")
    print("\nNext steps:")
    print("1. Edit .env file with your bot token and secret code")
    print("2. Run: python bot.py")
    print("\nTo get a bot token:")
    print("1. Message @BotFather on Telegram")
    print("2. Use /newbot command")
    print("3. Follow the instructions")
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)