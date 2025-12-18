import aiohttp
import logging
from typing import Optional, List
from app.core.config import settings

logger = logging.getLogger(__name__)

class GreenApiService:
    def __init__(self):
        self.base_url = settings.GREEN_API_BASE_URL
        self.instance_id = settings.GREEN_API_INSTANCE_ID
        self.api_token = settings.GREEN_API_API_TOKEN

    def _get_url(self, method: str) -> str:
        return f"{self.base_url}/waInstance{self.instance_id}/{method}/{self.api_token}"

    async def send_message(self, chat_id: str, message: str) -> dict:
        """
        Send a text message to a chat (phone number or group ID).
        chat_id: Phone number (e.g., '79001234567', '+7 900 123-45-67') or Group ID.
                 Phone numbers will be sanitized (digits only) and '@c.us' appended.
                 If it's a group, it should already have '@g.us'.
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        # Format chat_id
        if '@' not in chat_id:
            # Sanitize phone number: remove all non-digit characters
            clean_phone = ''.join(filter(str.isdigit, chat_id))
            chat_id = f"{clean_phone}@c.us"

        url = self._get_url("sendMessage")
        payload = {
            "chatId": chat_id,
            "message": message
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Green API Error: {response.status} - {error_text}")
                    raise Exception(f"Failed to send message: {error_text}")
                
                return await response.json()

    async def send_to_group(self, group_name: str, message: str) -> dict:
        """
        Send a message to all contacts in a specific group.
        """
        from app.services.contact_service import contact_service
        
        contacts = await contact_service.get_contacts()
        target_contacts = [c for c in contacts if c.group == group_name]
        
        if not target_contacts:
            return {"status": "warning", "message": f"No contacts found in group '{group_name}'"}

        results = {
            "total": len(target_contacts),
            "sent": 0,
            "failed": 0,
            "errors": []
        }

        for contact in target_contacts:
            try:
                # Assuming contact.phone is the chat_id (clean phone number)
                await self.send_message(contact.phone, message)
                results["sent"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"{contact.name} ({contact.phone}): {str(e)}")

        return results

    async def get_contact_info(self, contact_id: str) -> dict:
        """
        Get contact information from WhatsApp.
        contact_id can be a phone number (e.g., "79001234567") or a contact ID (e.g., "214237649621159@c.us")
        Returns: {"name": "Contact Name", "avatar": "url", "exists": True/False}
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        # If it's already a full chat ID (has @), use it directly
        # Otherwise, treat as phone number and convert to @c.us
        if '@' in contact_id:
            # Already a full chat ID (phone@c.us or contact_id@c.us)
            chat_id = contact_id
        else:
            # Sanitize phone number and convert to @c.us
            clean_phone = ''.join(filter(str.isdigit, contact_id))
            chat_id = f"{clean_phone}@c.us"

        url = self._get_url("getContactInfo")
        payload = {"chatId": chat_id}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.debug(f"Green API getContactInfo for {chat_id}: {response.status} - {error_text}")
                    return {"exists": False, "name": None, "avatar": None}
                
                data = await response.json()
                name = data.get("name") or data.get("contactName") or None
                whatsapp_id = data.get("chatId") or chat_id  # WhatsApp ID (может быть phone@c.us или contact_id@c.us)
                
                # Извлекаем все доступные данные
                import json
                products_json = None
                if data.get("products") and isinstance(data.get("products"), list):
                    products_json = json.dumps(data.get("products"), ensure_ascii=False)
                
                # Преобразуем lastSeen из timestamp в datetime, если есть
                last_seen = None
                if data.get("lastSeen"):
                    try:
                        from datetime import datetime
                        if isinstance(data.get("lastSeen"), (int, float)):
                            last_seen = datetime.fromtimestamp(data.get("lastSeen"))
                    except:
                        pass
                
                # Log full response for debugging (only if name is missing or looks like a phone number)
                if not name or (name.isdigit() and len(name) >= 10):
                    logger.info(f"Green API getContactInfo response for {chat_id}: {data}")
                
                return {
                    "exists": True,
                    "name": name,
                    "contactName": data.get("contactName"),
                    "avatar": data.get("avatar", None),
                    "whatsapp_id": whatsapp_id,
                    "email": data.get("email"),
                    "category": data.get("category"),
                    "description": data.get("description"),
                    "isBusiness": data.get("isBusiness", False),
                    "lastSeen": last_seen,
                    "products": products_json,  # JSON строка со списком продуктов
                    "isArchive": data.get("isArchive", False),
                    "isDisappearing": data.get("isDisappearing", False),
                    "isMute": data.get("isMute", False),
                    "messageExpiration": data.get("messageExpiration", 0),
                    "muteExpiration": data.get("muteExpiration")
                }

    async def check_whatsapp(self, phone: str) -> dict:
        """
        Check if a phone number is registered on WhatsApp.
        Returns: {"exists": True/False, "phoneNumber": str}
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        # Sanitize phone number
        clean_phone = ''.join(filter(str.isdigit, phone))
        
        url = self._get_url("checkWhatsapp")
        payload = {"phoneNumber": int(clean_phone)}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.debug(f"Green API checkWhatsapp for {clean_phone}: {response.status} - {error_text}")
                    return {"exists": False, "phoneNumber": clean_phone}
                
                data = await response.json()
                exists = data.get("existsWhatsapp", False)
                return {
                    "exists": exists,
                    "phoneNumber": clean_phone
                }

    async def get_avatar(self, phone: str) -> Optional[str]:
        """
        Download contact avatar and save to static/avatars.
        Returns: local file path relative to static folder (e.g., '/static/avatars/79001234567.jpg')
        """
        import os
        import aiofiles
        from pathlib import Path
        from app.core.config import settings

        if not self.instance_id or not self.api_token:
            logger.error("Green API credentials not configured")
            return None

        # Sanitize phone number
        clean_phone = ''.join(filter(str.isdigit, phone))
        chat_id = f"{clean_phone}@c.us"

        url = self._get_url("getAvatar")
        payload = {"chatId": chat_id}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to get avatar info for {phone}: status {response.status}")
                        return None
                    
                    data = await response.json()
                    avatar_url = data.get("urlAvatar")
                    
                    if not avatar_url:
                        logger.info(f"No avatar URL returned for {phone}")
                        return None

                    logger.info(f"Downloading avatar for {phone} from {avatar_url}")

                    # Download avatar image
                    async with session.get(avatar_url) as img_response:
                        if img_response.status != 200:
                            logger.warning(f"Failed to download avatar image: status {img_response.status}")
                            return None
                        
                        # Save to static/avatars using absolute path
                        avatars_dir = Path(settings.BASE_DIR) / "app" / "static" / "avatars"
                        avatars_dir.mkdir(parents=True, exist_ok=True)
                        
                        file_path = avatars_dir / f"{clean_phone}.jpg"
                        
                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(await img_response.read())
                        
                        logger.info(f"Successfully saved avatar to {file_path}")
                        
                        # Return relative URL
                        return f"/static/avatars/{clean_phone}.jpg"
        except Exception as e:
            logger.error(f"Error in get_avatar for {phone}: {e}")
            return None

    async def get_chat_history(self, chat_id: str, count: int = 100) -> List[dict]:
        """
        Get chat history for a contact or group from WhatsApp.
        chat_id can be a phone number (will be converted to @c.us) or group ID (@g.us)
        Returns list of messages with: text, timestamp, type, sender
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        # If it's already a full chat ID (has @), use it directly
        # Otherwise, treat as phone number and convert to @c.us
        if '@' in chat_id:
            # Already a full chat ID (phone@c.us or group@g.us)
            full_chat_id = chat_id
        else:
            # Sanitize phone number and convert to @c.us
            clean_phone = ''.join(filter(str.isdigit, chat_id))
            full_chat_id = f"{clean_phone}@c.us"

        url = self._get_url("getChatHistory")
        payload = {
            "chatId": full_chat_id,
            "count": count
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Green API Error getting chat history for {full_chat_id}: {response.status} - {error_text}")
                    return []
                
                data = await response.json()
                
                # Green API returns messages in array
                # But sometimes it might be wrapped in an object
                if isinstance(data, list):
                    messages = data
                elif isinstance(data, dict):
                    # Check if messages are in a nested structure
                    messages = data.get('messages', data.get('data', []))
                    if not isinstance(messages, list):
                        logger.warning(f"Unexpected chat history structure: {list(data.keys())}")
                        messages = []
                else:
                    logger.warning(f"Unexpected chat history response type: {type(data)}")
                    messages = []
                
                # Log structure of first message for debugging
                if messages and len(messages) > 0:
                    logger.debug(f"First message keys: {list(messages[0].keys()) if isinstance(messages[0], dict) else 'not a dict'}")
                
                return messages

    async def get_last_incoming_messages(self) -> List[dict]:
        """
        Get recent incoming messages across all chats.
        Used for incremental updates.
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        url = self._get_url("lastIncomingMessages")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.warning(f"Green API Error getting last incoming messages: {response.status} - {error_text}")
                    return []
                
                data = await response.json()
                return data if isinstance(data, list) else []

    async def get_chats(self) -> List[dict]:
        """
        Get all chats including groups and personal chats.
        Returns list of chat objects with id, name, type, etc.
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        url = self._get_url("getChats")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Green API Error getting chats: {response.status} - {error_text}")
                    return []
                
                data = await response.json()
                return data if isinstance(data, list) else []

    async def get_contacts(self) -> List[dict]:
        """
        Get all contacts from the address book.
        Returns list of contact objects.
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        url = self._get_url("getContacts")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Green API Error getting contacts: {response.status} - {error_text}")
                    return []
                
                data = await response.json()
                return data if isinstance(data, list) else []

    async def get_group_data(self, group_id: str) -> dict:
        """
        Get group data including participants.
        Returns dict with group data or empty dict on error.
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        url = self._get_url("getGroupData")
        payload = {"groupId": group_id}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Green API Error getting group data: {response.status} - {error_text}")
                        return {}
                    
                    data = await response.json()
                    # Check if API returned an error message as string
                    if isinstance(data, str):
                        logger.error(f"Green API returned error string: {data}")
                        return {}
                    
                    # Log the structure for debugging
                    if isinstance(data, dict):
                        logger.debug(f"getGroupData response keys: {list(data.keys())}")
                        logger.debug(f"getGroupData response: {data}")
                        return data
                    else:
                        logger.warning(f"getGroupData returned non-dict: {type(data)}")
                        return {}
        except Exception as e:
            logger.error(f"Exception getting group data for {group_id}: {e}")
            return {}

    async def add_group_participant(self, group_id: str, participant_id: str) -> dict:
        """
        Add a participant to a WhatsApp group.
        
        Args:
            group_id: Group ID (e.g., "120363163252210518@g.us")
            participant_id: Participant ID (e.g., "79001234567@c.us")
            
        Returns:
            Response dict with success status
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        url = self._get_url("addGroupParticipant")
        payload = {
            "groupId": group_id,
            "participantChatId": participant_id
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Green API Error adding participant: {response.status} - {error_text}")
                    return {"success": False, "error": error_text}
                
                try:
                    data = await response.json()
                    return {"success": True, "data": data}
                except Exception as e:
                    # Some APIs return empty response on success
                    text = await response.text()
                    if not text or text.strip() == "":
                        return {"success": True, "data": {}}
                    logger.warning(f"Could not parse JSON response: {e}, text: {text}")
                    return {"success": True, "data": {"raw": text}}



    async def receive_notification(self) -> Optional[dict]:
        """
        Receive a notification from the queue (HTTP API method).
        Returns notification object or None if queue is empty.
        
        Notification format:
        {
            "receiptId": 1234,
            "body": {
                "typeWebhook": "incomingMessageReceived",
                "instanceData": {...},
                "timestamp": 1234567890,
                "idMessage": "...",
                "senderData": {...},
                "messageData": {...}
            }
        }
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        url = self._get_url("receiveNotification")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.debug(f"No notifications in queue: {response.status}")
                    return None
                
                data = await response.json()
                # If queue is empty, Green API returns null
                return data if data else None

    async def delete_notification(self, receipt_id: int) -> bool:
        """
        Delete a notification from the queue after processing.
        
        Args:
            receipt_id: Receipt ID from the notification
            
        Returns:
            True if deleted successfully, False otherwise
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        url = f"{self.base_url}/waInstance{self.instance_id}/deleteNotification/{self.api_token}/{receipt_id}"

        async with aiohttp.ClientSession() as session:
            async with session.delete(url) as response:
                if response.status != 200:
                    logger.warning(f"Failed to delete notification {receipt_id}: {response.status}")
                    return False
                return True

    async def download_file_by_id(self, chat_id: str, id_message: str) -> Optional[bytes]:
        """
        Download media file using chatId and idMessage.
        This is the correct method for downloading media from Green API.
        
        Args:
            chat_id: Chat ID (e.g., "79216507071@c.us")
            id_message: Message ID containing media
            
        Returns:
            File contents as bytes, or None if download failed
        """
        if not self.instance_id or not self.api_token:
            raise ValueError("Green API credentials not configured")

        url = self._get_url("downloadFile")
        payload = {
            "chatId": chat_id,
            "idMessage": id_message
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload,timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Failed to download file: {response.status} - {error_text}")
                        return None
                    
                    # Check content type
                    content_type = response.headers.get('Content-Type', '')
                    content_length = response.headers.get('Content-Length', 'unknown')
                    # Downloading file (removed verbose logging)
                    
                    # Return file contents as bytes
                    file_data = await response.read()
                    file_size = len(file_data)
                    # Downloaded file (removed verbose logging)
                    
                    # Check if response is JSON error instead of file
                    if file_size < 500:
                        try:
                            import json
                            error_data = json.loads(file_data.decode('utf-8'))
                            logger.error(f"❌ Green API returned JSON error instead of file: {error_data}")
                            return None
                        except:
                            # Not JSON, but very small - might be thumbnail or error
                            logger.warning(f"⚠️ Downloaded file is very small ({file_size} bytes) - might be thumbnail or error")
                    
                    return file_data
                    
        except Exception as e:
            logger.error(f"Error downloading file {id_message}: {e}")
            return None


    async def download_media_file(self, file_url: str, save_path: str, timeout: int = 30) -> bool:
        """
        Download a media file directly from downloadUrl (not via Green API endpoint).
        This method makes a direct HTTP GET request to the downloadUrl and saves the file.
        
        Args:
            file_url: Direct download URL (downloadUrl from Green API response)
            save_path: Absolute path where to save the file
            timeout: Download timeout in seconds
            
        Returns:
            True if download successful, False otherwise
        """
        import os
        import aiofiles
        import json
        
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Failed to download media from {file_url}: HTTP {response.status} - {error_text[:200]}")
                        return False
                    
                    # Check Content-Type to detect JSON responses
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'application/json' in content_type or 'text/json' in content_type:
                        # Got JSON instead of file - this shouldn't happen with direct downloadUrl
                        try:
                            json_data = await response.json()
                            logger.error(f"❌ Received JSON instead of file from {file_url}: {json_data}")
                            return False
                        except:
                            # Try to read as text
                            text_data = await response.text()
                            logger.error(f"❌ Received JSON/text instead of file from {file_url}: {text_data[:200]}")
                            return False
                    
                    # Read the file content
                    file_data = await response.read()
                    file_size = len(file_data)
                    
                    # Check if response is very small - might be JSON error
                    if file_size < 500:
                        try:
                            # Try to parse as JSON
                            json_data = json.loads(file_data.decode('utf-8', errors='ignore'))
                            logger.error(f"❌ Received JSON error instead of file (size: {file_size} bytes): {json_data}")
                            return False
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            # Not JSON, but very small - might be thumbnail or error
                            if file_size < 100:
                                logger.warning(f"⚠️ Downloaded file is very small ({file_size} bytes) - might be error or thumbnail")
                    
                    # Save file
                    async with aiofiles.open(save_path, 'wb') as f:
                        await f.write(file_data)
                    
                    logger.debug(f"✅ Downloaded media file from {file_url} to {save_path} ({file_size} bytes)")
                    return True
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error downloading media from {file_url}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error downloading media file from {file_url}: {e}", exc_info=True)
            return False

green_api_service = GreenApiService()

