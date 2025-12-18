from telethon import TelegramClient, errors
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class TelegramService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramService, cls).__new__(cls)
            cls._instance.client = None
        return cls._instance

    async def get_client(self) -> TelegramClient:
        if not self.client:
            if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
                raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set")
            
            self.client = TelegramClient(
                settings.TELEGRAM_SESSION_PATH,
                settings.TELEGRAM_API_ID,
                settings.TELEGRAM_API_HASH
            )
            await self.client.connect()
        return self.client

    async def send_code(self, phone: str):
        client = await self.get_client()
        if await client.is_user_authorized():
            return {"status": "already_authorized"}
        
        try:
            sent = await client.send_code_request(phone)
            return {"phone_code_hash": sent.phone_code_hash, "status": "code_sent"}
        except errors.FloodWaitError as e:
            return {"error": f"Flood wait: {e.seconds} seconds"}
        except Exception as e:
            logger.error(f"Error sending code: {e}")
            raise e

    async def sign_in(self, phone: str, code: str, phone_code_hash: str):
        client = await self.get_client()
        try:
            user = await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            return {"status": "success", "user_id": user.id, "username": user.username}
        except errors.SessionPasswordNeededError:
            return {"status": "password_required"}
        except errors.PhoneCodeInvalidError:
            return {"status": "invalid_code"}
        except Exception as e:
            logger.error(f"Error signing in: {e}")
            raise e

    async def sign_in_password(self, password: str):
        client = await self.get_client()
        try:
            user = await client.sign_in(password=password)
            return {"status": "success", "user_id": user.id}
        except Exception as e:
            logger.error(f"Error signing in with password: {e}")
            raise e

    async def get_status(self):
        try:
            if not self.client:
                return {"connected": False}
            authorized = await self.client.is_user_authorized()
            return {"connected": True, "authorized": authorized}
        except Exception:
            return {"connected": False}

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            self.client = None
            logger.info("Telegram client disconnected")

telegram_service = TelegramService()
