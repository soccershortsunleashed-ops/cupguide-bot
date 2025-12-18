from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "Telegram Monitor"
    PROJECT_VERSION: str = "0.1.0"
    
    # Telegram API
    TELEGRAM_API_ID: Optional[int] = None
    TELEGRAM_API_HASH: Optional[str] = None
    TELEGRAM_PHONE: Optional[str] = None
    
    # LLM
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    MEGALLM_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    
    # WhatsApp
    ENABLE_WHATSAPP_MONITORING: bool = False  # Мониторинг WhatsApp отключен
    
    # Green API
    GREEN_API_INSTANCE_ID: Optional[str] = None
    GREEN_API_API_TOKEN: Optional[str] = None
    GREEN_API_BASE_URL: str = "https://api.green-api.com"
    
    # Paths
    # Go up two levels from config.py (app/core/) to get to project root
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    TELEGRAM_SESSION_PATH: str = os.path.join(BASE_DIR, "session", "user_session")
    CHANNELS_FILE: str = os.path.join(DATA_DIR, "channels.json")
    MESSAGES_FILE: str = os.path.join(DATA_DIR, "messages.json")
    
    # Security
    SECRET_KEY: str = "changeme"
    
    class Config:
        # Use absolute path to .env file in project root
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
        env_file_encoding = 'utf-8'
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields in .env if any

settings = Settings()

# Debug: Check if OPENAI_API_KEY is loaded and manually load if needed
# Use print for early logging before logging is configured
env_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")

if not settings.OPENAI_API_KEY:
    print(f"⚠️ OPENAI_API_KEY not loaded by pydantic. .env file path: {env_file_path}, exists: {os.path.exists(env_file_path)}")
    if os.path.exists(env_file_path):
        try:
            with open(env_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"📄 .env file size: {len(content)} bytes")
                print(f"🔍 Searching for OPENAI_API_KEY in .env...")
                
                # Check if OPENAI_API_KEY exists in content
                if 'OPENAI_API_KEY' in content:
                    print(f"✅ Found 'OPENAI_API_KEY' string in .env file")
                    # Try to manually parse - handle both Windows and Unix line endings
                    lines = content.replace('\r\n', '\n').split('\n')
                    print(f"📝 Total lines in .env: {len(lines)}")
                    
                    found_key = False
                    for i, line in enumerate(lines):
                        line_stripped = line.strip()
                        # Проверяем как обычные, так и закомментированные строки
                        if line_stripped and 'OPENAI_API_KEY' in line_stripped:
                            # Если строка закомментирована, убираем комментарий
                            if line_stripped.startswith('#'):
                                line_stripped = line_stripped[1:].strip()
                                print(f"⚠️ Found commented OPENAI_API_KEY on line {i+1}, uncommenting...")
                            
                            if 'OPENAI_API_KEY' in line_stripped and not line_stripped.startswith('#'):
                                print(f"🔍 Found potential key on line {i+1}: {line_stripped[:50]}...")
                                if '=' in line_stripped:
                                    parts = line_stripped.split('=', 1)
                                    if len(parts) == 2 and parts[0].strip() == 'OPENAI_API_KEY':
                                        key_value = parts[1].strip()
                                        # Remove quotes if present
                                        if key_value.startswith('"') and key_value.endswith('"'):
                                            key_value = key_value[1:-1]
                                        elif key_value.startswith("'") and key_value.endswith("'"):
                                            key_value = key_value[1:-1]
                                        if key_value:
                                            print(f"⚠️ OPENAI_API_KEY found in .env but not loaded by pydantic. Value length: {len(key_value)}")
                                            print(f"🔧 Manually setting OPENAI_API_KEY...")
                                            # Manually set the key
                                            settings.OPENAI_API_KEY = key_value
                                            print(f"✅ OPENAI_API_KEY manually set (length: {len(key_value)})")
                                            found_key = True
                                            break
                    
                    if not found_key:
                        print(f"⚠️ OPENAI_API_KEY string found in .env but could not parse the value")
                        # Try to find any line with OPENAI
                        for i, line in enumerate(lines):
                            if 'OPENAI' in line.upper():
                                print(f"📋 Line {i+1} with OPENAI: {line[:100]}")
                else:
                    print(f"❌ 'OPENAI_API_KEY' not found in .env file content")
                    print(f"💡 РЕШЕНИЕ: Добавьте в .env файл строку:")
                    print(f"   OPENAI_API_KEY=your_openai_api_key_here")
                    print(f"   Или запустите: python setup_openai_key.py")
                    # Show first few lines for debugging
                    lines = content.split('\n')[:10]
                    print(f"📋 First 10 lines of .env:")
                    for i, line in enumerate(lines):
                        print(f"  {i+1}: {line[:80]}")
        except Exception as e:
            print(f"❌ Error reading .env file: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"❌ .env file does not exist at: {env_file_path}")
        print(f"💡 РЕШЕНИЕ: Создайте .env файл и добавьте:")
        print(f"   OPENAI_API_KEY=your_openai_api_key_here")
        print(f"   Или запустите: python setup_openai_key.py")
else:
    print(f"✅ OPENAI_API_KEY loaded successfully (length: {len(settings.OPENAI_API_KEY)})")

# Ensure session and data directories exist
os.makedirs(os.path.dirname(settings.TELEGRAM_SESSION_PATH), exist_ok=True)
os.makedirs(settings.DATA_DIR, exist_ok=True)
