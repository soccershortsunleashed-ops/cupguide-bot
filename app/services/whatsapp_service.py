import logging
import os
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta
import base64
import time
from seleniumwire import webdriver  # Selenium-Wire instead of regular selenium
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from app.core.config import settings
from app.models.channel import Channel, ChannelType, Platform
import hashlib
import mimetypes
import uuid

logger = logging.getLogger(__name__)

class WhatsAppService:
    """
    WhatsApp service using raw Selenium (No third-party wrapper)
    """
    
    def __init__(self):
        self.driver = None
        self.authenticated = False
        self._qr_code = None
        self.monitored_chats_file = os.path.join(settings.DATA_DIR, "monitored_chats.json")
        self.monitored_chats = self._load_monitored_chats()
        # Lock to prevent concurrent access to Selenium WebDriver
        self._selenium_lock = asyncio.Lock()
        logger.info(f"WhatsApp service initialized. Loaded {len(self.monitored_chats)} monitored chats.")

    def _load_monitored_chats(self) -> List[str]:
        """Load monitored chats from JSON file"""
        try:
            if os.path.exists(self.monitored_chats_file):
                import json
                with open(self.monitored_chats_file, 'r', encoding='utf-8') as f:
                    chats = json.load(f)
                    logger.info(f"Loaded {len(chats)} monitored chats from {self.monitored_chats_file}: {chats}")
                    return chats
            else:
                logger.warning(f"Monitored chats file not found: {self.monitored_chats_file}")
        except Exception as e:
            logger.error(f"Error loading monitored chats from {self.monitored_chats_file}: {e}", exc_info=True)
        return []

    def _save_monitored_chats(self):
        """Save monitored chats to JSON file"""
        try:
            import json
            with open(self.monitored_chats_file, 'w', encoding='utf-8') as f:
                json.dump(self.monitored_chats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving monitored chats: {e}")
    
    async def connect(self):
        """Initialize WhatsApp Web connection"""
        try:
            # If driver exists, check if it's alive
            if self.driver:
                try:
                    self.driver.current_url
                    return True
                except:
                    logger.warning("Existing driver is dead, restarting...")
                    await self.disconnect()

            # Chrome options
            chrome_options = Options()
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--ignore-certificate-errors") # Fix for HTTPS issues
            chrome_options.add_argument("--allow-insecure-localhost")
            # chrome_options.add_argument("--headless=new") # Commented out for debugging visibility if needed
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # Persist session
            session_dir = os.path.join(settings.DATA_DIR, "whatsapp_session")
            chrome_options.add_argument(f"--user-data-dir={session_dir}")
            
            # Selenium-Wire options for network request interception
            seleniumwire_options = {
                'disable_encoding': True,  # Important to get actual content
                'verify_ssl': False,  #Don't verify SSL for easier debugging
                'ignore_http_methods': ['OPTIONS'],
                'connection_timeout': None,
            }
            
            # Create driver
            logger.info("Starting Chrome driver...")
            driver_path = ChromeDriverManager().install()
            # webdriver_manager may return a path to a helper file; ensure we point to the .exe
            if driver_path.lower().endswith('.chromedriver') or not driver_path.lower().endswith('.exe'):
                driver_dir = os.path.dirname(driver_path)
                possible_exe = os.path.join(driver_dir, "chromedriver.exe")
                if os.path.isfile(possible_exe):
                    driver_path = possible_exe
            service = Service(driver_path)
            self.driver = webdriver.Chrome(
                service=service,
                options=chrome_options,
                seleniumwire_options=seleniumwire_options  # Enable request interception
            )
            
            # Open WhatsApp Web
            logger.info("Opening WhatsApp Web...")
            self.driver.get("https://web.whatsapp.com")
            
            # Start background auth check
            asyncio.create_task(self._check_auth_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to WhatsApp: {e}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
            raise

    async def _check_connection(self) -> bool:
        """Check if driver is alive and reconnect if needed"""
        if not self.driver:
            logger.info("Driver not initialized, connecting...")
            try:
                await self.connect()
                return True
            except:
                return False

        try:
            # Simple check to see if driver is responsive
            self.driver.current_url
            return True
        except Exception as e:
            logger.warning(f"Driver connection lost ({e}), reconnecting...")
            try:
                await self.disconnect()
                await self.connect()
                return True
            except Exception as e2:
                logger.error(f"Reconnection failed: {e2}")
                return False

    async def _check_auth_loop(self):
        """Loop to check for QR code or successful login"""
        logger.info("Starting auth check loop...")
        max_attempts = 60 # 5 minutes
        attempts = 0
        
        while attempts < max_attempts and not self.authenticated:
            if not self.driver:
                break
                
            try:
                # Use WebDriverWait to properly wait for authenticated elements
                wait = WebDriverWait(self.driver, 10)  # 10 second timeout per attempt
                
                # Try multiple selectors in order of reliability
                selectors_to_try = [
                    (By.CSS_SELECTOR, "div[data-testid='chat-list']", "chat-list"),
                    (By.CSS_SELECTOR, "div[data-testid='conversation-panel-wrapper']", "conversation-panel"),
                    (By.XPATH, "//header[@data-testid='chatlist-header']", "chatlist-header"),
                    (By.XPATH, "//div[@id='pane-side']", "pane-side"),
                    (By.XPATH, "//span[@data-icon='search']", "search-icon"),
                    (By.CSS_SELECTOR, "div[data-testid='chat']", "chat-element"),
                ]
                
                authenticated_via = None
                for by, selector, name in selectors_to_try:
                    try:
                        element = wait.until(EC.presence_of_element_located((by, selector)))
                        if element:
                            authenticated_via = name
                            break
                    except TimeoutException:
                        continue
                    except Exception as e:
                        logger.debug(f"Selector {name} check failed: {e}")
                        continue
                
                if authenticated_via:
                    self.authenticated = True
                    self._qr_code = None
                    logger.info(f"✅ WhatsApp authenticated via {authenticated_via}!")
                    break
                
                # 2. If not logged in, try to get QR code
                if not self.authenticated:
                    try:
                        # Canvas element usually contains the QR code
                        canvas = self.driver.find_element(By.TAG_NAME, "canvas")
                        if canvas:
                            # Get base64 image from canvas
                            qr_b64 = self.driver.execute_script(
                                "return arguments[0].toDataURL('image/png').substring(22);", 
                                canvas
                            )
                            if qr_b64:
                                self._qr_code = qr_b64
                                logger.debug("QR code retrieved")
                    except Exception as e:
                        # QR might not be loaded yet
                        pass
            
            except Exception as e:
                logger.error(f"Error in auth loop: {e}")
            
            await asyncio.sleep(5)
            attempts += 1

    async def disconnect(self):
        """Disconnect from WhatsApp"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
                self.authenticated = False
                logger.info("WhatsApp disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
    
    async def get_qr_code(self) -> Optional[str]:
        """Get QR code as base64 string"""
        return self._qr_code
    
    async def get_all_chats(self) -> List[dict]:
        """Get all WhatsApp chats"""
        # Ensure connection is alive
        if not await self._check_connection():
            logger.error("Cannot get chats: Connection failed")
            return []
            
        if not self.authenticated:
            logger.warning("get_all_chats called but not authenticated")
            return []
        
        try:
            chats = []
            
            # Wait a bit for chats to load
            wait = WebDriverWait(self.driver, 5)
            
            # Log page source for debugging
            try:
                page_html = self.driver.page_source
                logger.debug(f"Page HTML length: {len(page_html)}")
                # Log snippet of HTML to see structure
                if len(page_html) > 1000:
                    logger.debug(f"HTML snippet: {page_html[500:1500]}")
            except Exception as e:
                logger.debug(f"Could not log page source: {e}")
            
            # Try multiple selectors for chat elements - updated for current WhatsApp Web
            chat_selectors = [
                "div[data-testid='conversation-panel-wrapper'] div[role='listitem']",  # Chats in side panel
                "div[role='listitem']",  # Generic list items
                "div[data-testid='cell-frame-container']",
                "span[data-testid='cell-frame-title']",  # Chat titles
                "#pane-side div[tabindex='-1']",  # Clickable chat divs
            ]
            
            chat_elements = []
            for selector in chat_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(f"Found {len(elements)} elements using selector: {selector}")
                        chat_elements = elements
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}") 
                    continue
            
            if not chat_elements:
                logger.warning("No chat elements found with any selector")
                # Try to get more info about page structure
                try:
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text[:500]
                    logger.debug(f"Body text sample: {body_text}")
                except:
                    pass
                return []
            
            # Extract chat names using multiple approaches
            for idx, elem in enumerate(chat_elements[:30]):  # Limit to 30 chats
                try:
                    chat_name = None
                    
                    # Try multiple methods to extract chat name
                    # Method 1: Look for title attribute
                    try:
                        title_elem = elem.find_element(By.XPATH, ".//span[@title]")
                        chat_name = title_elem.get_attribute("title")
                    except:
                        pass
                    
                    # Method 2: Look for specific data-testid
                    if not chat_name:
                        try:
                            title_elem = elem.find_element(By.CSS_SELECTOR, "span[data-testid='cell-frame-title']")
                            chat_name = title_elem.text
                        except:
                            pass
                    
                    # Method 3: Just get all text and take first line
                    if not chat_name:
                        try:
                            elem_text = elem.text
                            if elem_text:
                                lines = elem_text.split('\n')
                                chat_name = lines[0] if lines else None
                        except:
                            pass
                    
                    # Method 4: Look for any span with dir='auto'
                    if not chat_name:
                        try:
                            title_elem = elem.find_element(By.XPATH, ".//span[@dir='auto']")
                            chat_name = title_elem.text
                        except:
                            pass
                    
                    if chat_name and chat_name.strip() and len(chat_name) > 0:
                        # Filter out non-chat elements (e.g., timestamps, status messages)
                        if len(chat_name) < 100 and not chat_name.isdigit():
                            chats.append({
                                "id": chat_name,  # Using name as ID
                                "title": chat_name
                            })
                            logger.debug(f"Found chat: {chat_name}")
                except Exception as e:
                    logger.debug(f"Error extracting chat {idx}: {e}")
                    continue
            
            # Remove duplicates while preserving order
            seen = set()
            unique_chats = []
            for chat in chats:
                if chat['id'] not in seen:
                    seen.add(chat['id'])
                    unique_chats.append(chat)
            
            logger.info(f"Extracted {len(unique_chats)} unique chats total")
            return unique_chats
            
        except Exception as e:
            logger.error(f"Error getting chats: {e}")
            return []
    
    
    async def _download_media(self, url: str) -> Optional[str]:
        """Download media from blob URL and return base64 string"""
        try:
            script = """
                var uri = arguments[0];
                var callback = arguments[1];
                var xhr = new XMLHttpRequest();
                xhr.responseType = 'blob';
                xhr.onload = function() {
                    var reader = new FileReader();
                    reader.onloadend = function() {
                        callback(reader.result);
                    }
                    reader.readAsDataURL(xhr.response);
                };
                xhr.open('GET', uri);
                xhr.send();
            """
            # Selenium async script execution
            result = self.driver.execute_async_script(script, url)
            if result and result.startswith('data:'):
                return result # This is the base64 data URL
            return None
        except Exception as e:
            logger.error(f"Error downloading media {url}: {e}")
            return None

    async def _open_chat(self, chat_name: str) -> bool:
        """Open a specific chat by name, using search if necessary"""
        try:
            # 1. Check if already open
            try:
                header_title = self.driver.find_element(By.CSS_SELECTOR, "header span[dir='auto']").text
                if header_title == chat_name:
                    return True
            except:
                pass

            # 2. Try to find in visible list first
            try:
                chat_elem = self.driver.find_element(By.XPATH, f"//span[@title='{chat_name}']")
                chat_elem.click()
                await asyncio.sleep(1)
                return True
            except:
                pass
            
            # 3. Use Search
            try:
                # Click search button or find input
                search_box = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[contenteditable='true'][data-tab='3']"))
                )
                search_box.clear()
                search_box.send_keys(chat_name)
                await asyncio.sleep(1.5) # Wait for search results
                
                # Click the first result
                # We need to be careful to click the correct one if there are partial matches
                # But usually the best match is top.
                # Let's try to find exact match in results
                results = self.driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']")
                for res in results:
                    try:
                        title = res.find_element(By.CSS_SELECTOR, "span[title]").get_attribute("title")
                        if title == chat_name:
                            res.click()
                            
                            # Clear search
                            try:
                                cancel_btn = self.driver.find_element(By.CSS_SELECTOR, "span[data-icon='x-alt']")
                                cancel_btn.click()
                            except:
                                pass
                                
                            return True
                    except:
                        continue
                
                # If exact match not found in loop, try clicking the first result if it looks reasonable
                if results:
                    results[0].click()
                    # Clear search
                    try:
                        cancel_btn = self.driver.find_element(By.CSS_SELECTOR, "span[data-icon='x-alt']")
                        cancel_btn.click()
                    except:
                        pass
                    return True
                    
            except Exception as e:
                logger.debug(f"Search failed: {e}")
                
            return False
        except Exception as e:
            logger.error(f"Error opening chat {chat_name}: {e}")
            return False

    async def _capture_audio_from_requests(self, message_element, timeout=5.0) -> Optional[bytes]:
        """
        Capture audio blob from network requests after clicking play button.
        
        Args:
            message_element: The message element containing the voice message
            timeout: Maximum time to wait for audio request (seconds)
        
        Returns:
            bytes: Audio file content or None if not found
        """
        try:
            # Clear previous requests
            del self.driver.requests
            
            # Find and click play button
            play_button_selectors = [
                "span[data-testid='audio-play']",
                "span[data-icon='audio-play']",
                "button[aria-label*='воспроизв']",
                "button[aria-label*='Play']",
            ]
            
            play_button = None
            for selector in play_button_selectors:
                try:
                    play_button = message_element.find_element(By.CSS_SELECTOR, selector)
                    if play_button:
                        logger.info(f"Found play button with selector: {selector}")
                        break
                except:
                    continue
            
            if not play_button:
                logger.warning("No play button found for voice message")
                return None
            
            # Click play button
            play_button.click()
            logger.info("Clicked play button, monitoring network requests...")
            
            # Wait for audio request
            start_time = time.time()
            while time.time() - start_time < timeout:
                for request in self.driver.requests:
                    if request.response:
                        content_type = request.response.headers.get('Content-Type', '').lower()
                        
                        # Check for audio content by Content-Type
                        if 'audio' in content_type or 'ogg' in content_type or 'webm' in content_type or 'mpeg' in content_type:
                            logger.info(f"✅ Found audio by Content-Type: {request.url[:100]}... (Content-Type: {content_type})")
                            
                            audio_bytes = request.response.body
                            if audio_bytes and len(audio_bytes) > 100:
                                logger.info(f"Captured audio: {len(audio_bytes)} bytes")
                                return audio_bytes
                        
                        # ALSO check for audio by URL pattern
                        if any(pattern in request.url.lower() for pattern in ['ptt', 'audio', 'voice', '.ogg', '.opus', '.m4a', '.enc']):
                            if request.response.status_code == 200 and request.response.body:
                                body_size = len(request.response.body)
                                if body_size > 1024:  # At least 1KB
                                    logger.info(f"✅ Found potential audio by URL pattern: {request.url[:100]}... | Size: {body_size} bytes")
                                    return request.response.body
                
                await asyncio.sleep(0.1)
            
            logger.warning(f"No audio request found within {timeout} seconds via CDP. Trying fallback...")
            
            # FALLBACK: Check if <audio> tag appeared in DOM and try to download blob
            try:
                audio_element = message_element.find_element(By.TAG_NAME, "audio")
                if audio_element:
                    src = audio_element.get_attribute("src")
                    if src and src.startswith("blob:"):
                        logger.info(f"Fallback: Found audio blob URL: {src}")
                        # Use existing _download_media to get base64 data
                        b64_data = await self._download_media(src)
                        if b64_data:
                            # Convert data URL to bytes
                            header, encoded = b64_data.split(",", 1)
                            return base64.b64decode(encoded)
            except:
                pass
                
            return None
            
        except Exception as e:
            logger.error(f"Error capturing audio from requests: {e}")
            return None

    async def _check_connection(self):
        """Check if the driver is still responsive"""
        try:
            if not self.driver:
                return False
            # Simple check
            _ = self.driver.current_url
            return True
        except:
            return False

    async def get_messages_from_chat(self, chat_name: str, days: int = 30, min_date: Optional[datetime] = None) -> List[dict]:
        """
        Extract messages from a WhatsApp chat using Selenium.
        Returns list of message dictionaries.
        
        Args:
            chat_name: Name of the chat (as displayed in WhatsApp)
            days: Number of days of history to fetch (default 30)
            min_date: If provided, stop fetching when messages older than this are reached
        """
        # Acquire lock to prevent concurrent access to Selenium
        async with self._selenium_lock:
            return await self._get_messages_from_chat_impl(chat_name, days, min_date)
    
    async def _get_messages_from_chat_impl(self, chat_name: str, days: int = 30, min_date: Optional[datetime] = None) -> List[dict]:
        """Internal implementation of get_messages_from_chat (called with lock held)"""
        # Ensure connection is alive
        if not await self._check_connection():
            logger.error("Cannot get messages: Connection failed")
            return []
            
        if not self.authenticated:
            logger.error("Cannot get messages: WhatsApp not authenticated")
            return []
        
        try:
            logger.info(f"Starting message extraction from chat '{chat_name}'")
            
            # Step 1: Open the chat
            if not await self._open_chat(chat_name):
                logger.error(f"Failed to open chat '{chat_name}'")
                return []
            
            logger.info(f"Opened chat '{chat_name}'")
            await asyncio.sleep(2)  # Wait for chat to load

            # Step 2: Wait for messages container to load
            try:
                messages_container = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='conversation-panel-body']"))
                )
            except:
                # Fallback selector
                try:
                    messages_container = self.driver.find_element(By.CSS_SELECTOR, "div[class*='copyable-area']")
                except Exception as e:
                    logger.error(f"Could not find messages container: {e}")
                    return []
            
            # Step 3: Scroll up to load older messages
            logger.info("Scrolling to load message history...")
            cutoff_date = datetime.now().astimezone() - timedelta(days=days)
            if min_date:
                # Ensure min_date is timezone aware
                if min_date.tzinfo is None:
                    min_date = min_date.replace(tzinfo=datetime.now().astimezone().tzinfo)
                # Use the more recent of cutoff_date or min_date
                if min_date > cutoff_date:
                    cutoff_date = min_date
                    logger.info(f"Using incremental sync. Cutoff date set to last message date: {cutoff_date}")
            
            last_height = self.driver.execute_script("return arguments[0].scrollHeight", messages_container)
            no_change_count = 0  # Track consecutive attempts with no height change
            
            # Always scroll thoroughly for complete message history
            # Use a set to track unique message IDs or content to detect if we are really loading new messages
            previous_first_msg_content = ""
            
            for scroll_attempt in range(100):  # Increased to 100
                # Scroll to top
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollTo(0, 0);",
                        messages_container
                    )
                    await asyncio.sleep(1.5)  # Wait for load
                    
                    # Check if we have new content at the top
                    try:
                        # Get the first message element's text content as a signature
                        # We use a broad selector to catch any message row
                        # IMPORTANT: Scope to messages_container to avoid finding sidebar elements
                        first_msg = messages_container.find_element(By.CSS_SELECTOR, "div[role='row']")
                        current_first_msg_content = first_msg.text
                        
                        if current_first_msg_content == previous_first_msg_content:
                            no_change_count += 1
                            # Try a small scroll down and up to trigger lazy loading
                            self.driver.execute_script("arguments[0].scrollBy(0, 500)", messages_container)
                            await asyncio.sleep(0.5)
                            self.driver.execute_script("arguments[0].scrollTo(0, 0);", messages_container)
                            await asyncio.sleep(1.0)
                            
                            # Check again
                            first_msg = messages_container.find_element(By.CSS_SELECTOR, "div[role='row']")
                            if first_msg.text == previous_first_msg_content:
                                if no_change_count >= 10: # Increased tolerance
                                    logger.info(f"Reached top of chat after {scroll_attempt + 1} scroll attempts (content unchanged)")
                                    break
                            else:
                                no_change_count = 0
                                previous_first_msg_content = first_msg.text
                        else:
                            no_change_count = 0
                            previous_first_msg_content = current_first_msg_content
                            
                    except Exception as e:
                        # If we can't find any message, maybe it's empty or loading
                        pass
                    
                    # Also check scrollHeight as a secondary signal
                    new_height = self.driver.execute_script("return arguments[0].scrollHeight", messages_container)
                    last_height = new_height
                    
                except Exception as e:
                    logger.error(f"Error during scrolling: {e}")
                    break
            
            logger.info("Finished scrolling, now extracting messages...")
            
            # DEBUG: Log container HTML to understand structure
            try:
                container_html = messages_container.get_attribute('innerHTML')
                logger.info(f"Container HTML start: {container_html[:500]}...")
            except:
                pass

            # Step 4: Extract all message elements
            messages = []
            
            # Try multiple selectors for message bubbles
            message_selectors = [
                "div[data-testid='msg-container']",  # Primary WhatsApp selector
                "div[role='row']", # Generic row selector (often used in virtual lists)
                "div[class*='message-'][class*='focusable']",  # Message bubbles with focusable class
                "div.message-in, div.message-out",  # Incoming/outgoing messages  
                "div[data-testid='conversation-panel-messages'] div[data-testid='msg-container']",  # Scoped to conversation panel
            ]
            
            message_elements = []
            for selector in message_selectors:
                try:
                    # IMPORTANT: Scope to messages_container
                    elements = messages_container.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        # Filter valid elements
                        valid_elements = []
                        for elem in elements:
                            try:
                                parent_id = elem.find_element(By.XPATH, "./ancestor::div[@id][1]").get_attribute("id")
                                if "pane-side" not in parent_id:
                                    valid_elements.append(elem)
                            except:
                                valid_elements.append(elem)
                        
                        if valid_elements:
                            logger.info(f"Found {len(valid_elements)} message elements with selector: {selector}")
                            message_elements = valid_elements
                            break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not message_elements:
                logger.warning(f"No message elements found in chat '{chat_name}'")
                return []
            
            # Prepare media directory
            media_dir = os.path.join(settings.DATA_DIR, "media", "whatsapp", chat_name)
            os.makedirs(media_dir, exist_ok=True)

            # Step 5: Parse each message
            for idx, msg_elem in enumerate(message_elements):
                try:
                    message_data = {}
                    
                    # Handle "Read more" buttons
                    try:
                        read_more_btns = msg_elem.find_elements(By.CSS_SELECTOR, "span[role='button']")
                        for btn in read_more_btns:
                            if btn.text.lower() in ['read more', 'читать далее', 'еще', 'more']:
                                self.driver.execute_script("arguments[0].click();", btn)
                                await asyncio.sleep(0.1)
                    except:
                        pass

                    # Extract text content
                    try:
                        text_elem = msg_elem.find_element(By.CSS_SELECTOR, "span.selectable-text")
                        message_data['text'] = text_elem.text or ""
                        logger.info(f"Extracted text via span.selectable-text: {message_data['text'][:50]}...")
                    except:
                        try:
                            # Fallback: try to get all text from message container
                            # But exclude time and sender if possible
                            # This is a bit risky as it might include metadata
                            full_text = msg_elem.text
                            # Try to clean it up?
                            message_data['text'] = full_text or ""
                            logger.info(f"Extracted text via msg_elem.text fallback: {message_data['text'][:50]}...")
                        except:
                            message_data['text'] = ""
                            logger.warning(f"Failed to extract text for message {idx}")
                    
                    # Extract sender
                    try:
                        sender_elem = msg_elem.find_element(By.CSS_SELECTOR, "span[data-testid='sender-text']")
                        message_data['sender'] = sender_elem.text
                    except:
                        message_data['sender'] = None
                    
                    # Extract timestamp
                    try:
                        time_elem = msg_elem.find_element(By.CSS_SELECTOR, "span[data-testid='msg-time']")
                        time_text = time_elem.text
                        message_data['date'] = self._parse_whatsapp_time(time_text, msg_elem)
                    except:
                        message_data['date'] = self._parse_whatsapp_time("", msg_elem)
                        
                    logger.info(f"Msg {idx}: Date={message_data.get('date')}, TextLen={len(message_data.get('text', ''))}")
                    
                    # Check for media
                    media_files = []
                    
                    # 1. Images
                    try:
                        imgs = msg_elem.find_elements(By.CSS_SELECTOR, "img[src^='blob:']")
                        for img in imgs:
                            src = img.get_attribute('src')
                            if src:
                                b64_data = await self._download_media(src)
                                if b64_data:
                                    # Save to file
                                    ext = "png" # Default
                                    if "image/jpeg" in b64_data: ext = "jpg"
                                    elif "image/webp" in b64_data: ext = "webp"
                                    
                                    filename = f"{uuid.uuid4()}.{ext}"
                                    filepath = os.path.join(media_dir, filename)
                                    
                                    header, encoded = b64_data.split(",", 1)
                                    data = base64.b64decode(encoded)
                                    
                                    with open(filepath, "wb") as f:
                                        f.write(data)
                                    
                                    media_files.append({
                                        "type": "photo",
                                        "path": f"/media/whatsapp/{chat_name}/{filename}"
                                    })
                    except Exception as e:
                        logger.debug(f"Error extracting image: {e}")

                    # 2. Videos
                    try:
                        # Direct video tags
                        videos = msg_elem.find_elements(By.CSS_SELECTOR, "video")
                        for video in videos:
                            src = video.get_attribute('src')
                            if src and src.startswith('blob:'):
                                b64_data = await self._download_media(src)
                                if b64_data:
                                    filename = f"{uuid.uuid4()}.mp4"
                                    filepath = os.path.join(media_dir, filename)
                                    
                                    header, encoded = b64_data.split(",", 1)
                                    data = base64.b64decode(encoded)
                                    
                                    with open(filepath, "wb") as f:
                                        f.write(data)
                                        
                                    media_files.append({
                                        "type": "video",
                                        "path": f"/media/whatsapp/{chat_name}/{filename}"
                                    })
                        
                        # Click-to-play videos (often just an image with a play button initially)
                        if not videos:
                            try:
                                # Look for play button container
                                play_btns = msg_elem.find_elements(By.CSS_SELECTOR, "span[data-testid='audio-play'], span[data-testid='video-play']") 
                                # Note: audio-play is for voice notes, video-play might be different. 
                                # Let's try a more generic approach for video containers that aren't loaded
                                video_containers = msg_elem.find_elements(By.CSS_SELECTOR, "div[class*='video-thumb']")
                                pass
                            except:
                                pass
                    except Exception as e:
                        logger.debug(f"Error extracting video: {e}")

                    # 3. Audio (Voice messages)
                    try:
                        # First, try to detect voice message containers
                        voice_indicators = [
                            "div[data-testid='audio-msg-container']",
                            "div[data-testid='ptt-msg-container']",  # PTT = Push-to-talk (voice)
                            "div[class*='audio']",
                            "span[data-testid='audio-duration']",
                            "span[data-icon='audio-play']",
                            "span[data-icon='audio-pause']",
                        ]
                        
                        has_voice = False
                        for selector in voice_indicators:
                            try:
                                elem = msg_elem.find_elements(By.CSS_SELECTOR, selector)
                                if elem:
                                    logger.info(f"Found voice indicator in message {idx} with selector: {selector}")
                                    has_voice = True
                                    break
                            except:
                                pass
                        
                        # Try to find existing audio tags first
                        audios = msg_elem.find_elements(By.CSS_SELECTOR, "audio")
                        
                        # If no audio tag but we detected a voice message, use CDP to capture audio
                        if not audios and has_voice:
                            logger.info(f"Voice message detected in message {idx}, attempting to capture via network requests...")
                            
                            # Use new CDP-based method to capture audio
                            audio_bytes = await self._capture_audio_from_requests(msg_elem, timeout=5.0)
                            
                            if audio_bytes:
                                # Save audio to file
                                filename = f"{uuid.uuid4()}.ogg"  # WhatsApp usually uses ogg/opus
                                filepath = os.path.join(media_dir, filename)
                                
                                with open(filepath, "wb") as f:
                                    f.write(audio_bytes)
                                
                                logger.info(f"Successfully saved voice message via CDP: {filename} ({len(audio_bytes)} bytes)")
                                media_files.append({
                                    "type": "voice",
                                    "path": f"/media/whatsapp/{chat_name}/{filename}"
                                })
                            else:
                                logger.warning(f"Failed to capture voice message audio for message {idx}")
                    except Exception as e:
                        logger.info(f"Error extracting audio from message {idx}: {e}")

                    # 4. Polls
                    try:
                        poll_container = msg_elem.find_elements(By.CSS_SELECTOR, "div[data-testid='poll-bubble']")
                        if poll_container:
                            logger.info(f"Found poll container in message {idx}")
                            poll_data = {"type": "poll", "question": "", "options": []}
                            
                            # Get Question
                            try:
                                question_elem = poll_container[0].find_element(By.TAG_NAME, "strong")
                                poll_data["question"] = question_elem.text
                                logger.info(f"Poll question: {poll_data['question']}")
                            except Exception as e:
                                logger.info(f"Could not find poll question: {e}")
                                
                            # Get Options
                            try:
                                options = poll_container[0].find_elements(By.CSS_SELECTOR, "li")
                                logger.info(f"Found {len(options)} poll options")
                                for opt in options:
                                    poll_data["options"].append(opt.text)
                            except Exception as e:
                                logger.info(f"Could not find poll options: {e}")
                            
                            # Append to text or handle as specific type
                            if poll_data["question"]:
                                poll_text = f"\n📊 Опрос: {poll_data['question']}\n"
                                for i, opt in enumerate(poll_data["options"]):
                                    poll_text += f"{i+1}. {opt}\n"
                                message_data['text'] = (message_data.get('text', '') + poll_text).strip()
                                logger.info(f"Added poll to message text: {len(poll_data['options'])} options")
                    except Exception as e:
                        logger.info(f"Error extracting poll from message {idx}: {e}")

                    message_data['media_files'] = media_files
                    
                    # Skip if no text and no media
                    if not message_data['text'].strip() and not media_files:
                        logger.info(f"Skipping message {idx}: No text and no media found")
                        continue
                    
                    # Filter by date
                    if message_data['date'] < cutoff_date:
                        logger.info(f"Skipping message {idx}: Date {message_data['date']} is older than cutoff {cutoff_date}")
                        continue
                    
                    messages.append(message_data)
                    logger.info(f"Successfully extracted message {idx}: {message_data['date']} - {message_data['text'][:20]}...")
                    
                except Exception as e:
                    logger.error(f"Could not parse message {idx}: {e}")
                    continue
            
            logger.info(f"Extracted {len(messages)} messages from chat '{chat_name}'")
            return messages
            
        except Exception as e:
            logger.error(f"Error extracting messages from chat '{chat_name}': {e}")
            return []
    
    def _parse_whatsapp_time(self, time_text: str, msg_elem=None) -> datetime:
        """Parse WhatsApp time string to datetime"""
        # Use timezone-aware current time
        now = datetime.now().astimezone()
        
        try:
            # Try to get exact timestamp from data-pre-plain-text if available
            # Format usually: "[14:30, 24.11.2025] Sender: "
            if msg_elem:
                try:
                    pre_text = msg_elem.get_attribute("data-pre-plain-text")
                    if pre_text:
                        # Extract content between brackets
                        import re
                        match = re.search(r"\[(.*?)\],?", pre_text)
                        if match:
                            dt_str = match.group(1)
                            # Try common formats
                            formats = [
                                "%H:%M, %d.%m.%Y",
                                "%I:%M %p, %m/%d/%Y",
                                "%H:%M, %d/%m/%Y"
                            ]
                            for fmt in formats:
                                try:
                                    dt = datetime.strptime(dt_str, fmt)
                                    return dt.replace(tzinfo=now.tzinfo)
                                except:
                                    continue
                except:
                    pass

            # Fallback to text parsing
            if not time_text:
                return now

            time_text = time_text.strip().lower()
            
            # Handle "HH:MM" format (today)
            if ':' in time_text and len(time_text) <= 5:
                hour, minute = map(int, time_text.split(':'))
                return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Handle relative dates
            if 'вчера' in time_text or 'yesterday' in time_text:
                return now - timedelta(days=1)
            elif 'сегодня' in time_text or 'today' in time_text:
                return now
            
            # Handle full date "DD.MM.YYYY"
            import re
            date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", time_text)
            if date_match:
                day, month, year = map(int, date_match.groups())
                # Use replace and ensure timezone is preserved
                result = now.replace(year=year, month=month, day=day, hour=12, minute=0, second=0, microsecond=0)
                # Explicitly ensure timezone info is present
                if result.tzinfo is None:
                    result = result.replace(tzinfo=now.tzinfo)
                return result
                
            # Handle day of week (simple approximation to last occurrence)
            days_map = {
                'понедельник': 0, 'monday': 0,
                'вторник': 1, 'tuesday': 1,
                'среда': 2, 'wednesday': 2,
                'четверг': 3, 'thursday': 3,
                'пятница': 4, 'friday': 4,
                'суббота': 5, 'saturday': 5,
                'воскресенье': 6, 'sunday': 6
            }
            
            for day_name, day_num in days_map.items():
                if day_name in time_text:
                    current_day = now.weekday()
                    diff = current_day - day_num
                    if diff <= 0:
                        diff += 7
                    return now - timedelta(days=diff)

            return now
        except Exception as e:
            logger.debug(f"Date parsing failed for '{time_text}': {e}")
            return now
    
    async def send_message(self, chat_id: str, message: str) -> bool:
        """Send a text message to a specific chat.
        chat_id: the display name of the chat (as shown in the chat list).
        Returns True on success, False otherwise.
        """
        # Ensure connection is alive
        if not await self._check_connection():
            logger.error("Cannot send message: Connection failed")
            return False

        if not self.authenticated:
            logger.error("Cannot send message: WhatsApp not authenticated.")
            return False
        try:
            # Locate the chat by its title attribute (chat name) and click it
            chat_elem = self.driver.find_element(By.XPATH, f"//span[@title='{chat_id}']")
            chat_elem.click()
            # Wait for the message input box to be present
            input_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true'][@data-tab='10']"))
            )
            # Send the message and press Enter
            input_box.send_keys(message)
            input_box.send_keys(Keys.ENTER)
            logger.info(f"Message sent to chat '{chat_id}'.")
            return True
        except Exception as e:
            logger.error(f"Error sending message to chat '{chat_id}': {e}")
            return False
    
    async def add_monitored_chat(self, chat_id: str) -> bool:
        """Add a chat to the monitored chats list."""
        if chat_id not in self.monitored_chats:
            self.monitored_chats.append(chat_id)
            self._save_monitored_chats()
            logger.info(f"Added '{chat_id}' to monitored chats. Total: {len(self.monitored_chats)}")
            return True
        logger.warning(f"Chat '{chat_id}' is already being monitored")
        return False
    async def remove_monitored_chat(self, chat_id: str) -> bool:
        """Remove a chat from the monitored chats list."""
        if chat_id in self.monitored_chats:
            self.monitored_chats.remove(chat_id)
            self._save_monitored_chats()
            logger.info(f"Removed '{chat_id}' from monitored chats. Remaining: {len(self.monitored_chats)}")
            return True
        logger.warning(f"Chat '{chat_id}' was not in monitored chats")
        return False

    async def get_monitored_chats(self) -> List[str]:
        """Return the list of monitored chats."""
        return self.monitored_chats.copy()

    async def get_monitored_chats_as_channels(self) -> List[Channel]:
        """Return monitored chats as Channel objects."""
        from app.services.green_api_service import green_api_service
        
        channels = []
        for chat_name in self.monitored_chats:
            # If it's a group ID, try to get the group name from get_chats()
            title = chat_name
            if chat_name.endswith('@g.us'):
                try:
                    # Method 1: Try get_chats() - it returns all chats with names
                    chats = await green_api_service.get_chats()
                    for chat in chats:
                        if chat.get('id') == chat_name and chat.get('type') == 'group':
                            title = chat.get('name', chat_name)
                            logger.info(f"✅ Got group name '{title}' for ID {chat_name} from get_chats()")
                            break
                    
                    # Method 2: If not found in get_chats(), try get_group_data()
                    if title == chat_name:
                        logger.debug(f"Group not found in get_chats(), trying get_group_data()...")
                        group_data = await green_api_service.get_group_data(chat_name)
                        if group_data and isinstance(group_data, dict):
                            # Try different possible field names
                            title = (group_data.get('name') or 
                                    group_data.get('title') or
                                    group_data.get('subject') or
                                    group_data.get('groupName') or
                                    chat_name)
                            if title != chat_name:
                                logger.info(f"✅ Got group name '{title}' for ID {chat_name} from get_group_data()")
                            else:
                                logger.warning(f"Could not get group name for {chat_name}, using ID. Group data keys: {list(group_data.keys())}")
                        else:
                            logger.warning(f"get_group_data() returned empty or invalid data for {chat_name}")
                except Exception as e:
                    logger.error(f"Error getting group name for {chat_name}: {e}", exc_info=True)
                    # Use ID as fallback
                    title = chat_name
            
            channels.append(Channel(
                id=chat_name,
                title=title,  # Use group name if available, otherwise ID
                username=None,
                type=ChannelType.SOURCE,
                platform=Platform.WHATSAPP
            ))
        return channels

# Global instance
whatsapp_service = WhatsAppService()


