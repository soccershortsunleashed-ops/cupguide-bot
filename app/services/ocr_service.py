"""Сервис для распознавания текста с изображений (OCR)"""
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import easyocr, but don't fail if not installed
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    easyocr = None
    EASYOCR_AVAILABLE = False
    logger.warning("EasyOCR not installed. Install with: pip install easyocr")

# Try OpenAI Vision API as alternative
try:
    from openai import AsyncOpenAI
    from app.core.config import settings
    OPENAI_VISION_AVAILABLE = True
except Exception:
    OPENAI_VISION_AVAILABLE = False

# Try Gemini API
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    genai = None
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not available. Gemini Vision support will be disabled.")

# Импорт менеджера квот Gemini
try:
    from google.api_core.exceptions import ResourceExhausted
    from app.services.gemini_quota_service import gemini_quota_state
    RESOURCE_EXHAUSTED_AVAILABLE = True
except ImportError:
    ResourceExhausted = Exception
    gemini_quota_state = None
    RESOURCE_EXHAUSTED_AVAILABLE = False
    logger.warning("google.api_core.exceptions not available. Gemini quota management will be limited.")


class OCRService:
    """Сервис для распознавания текста с изображений"""
    
    def __init__(self):
        self._current_api_key = None
        self._current_provider = None
        self.easyocr_reader = None
        self.openai_client = None
        self.gemini_model = None
        # Кэшируем распознанный текст по абсолютному пути к файлу, чтобы переиспользовать результат
        self._ocr_cache = {}
        
        if EASYOCR_AVAILABLE:
            logger.info("EasyOCR available for OCR")
        elif OPENAI_VISION_AVAILABLE:
            logger.info("OpenAI Vision API available for OCR")
        else:
            logger.warning("No OCR service available. Install EasyOCR or configure OpenAI API key.")
    
    def _get_easyocr_reader(self):
        """Ленивая инициализация EasyOCR reader"""
        if not EASYOCR_AVAILABLE:
            return None
        
        if self.easyocr_reader is None:
            try:
                logger.info("Initializing EasyOCR reader (this may take a minute on first run)...")
                self.easyocr_reader = easyocr.Reader(['ru', 'en'], gpu=False)
                logger.info("EasyOCR reader initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize EasyOCR: {e}")
                return None
        
        return self.easyocr_reader
    
    async def _get_vision_client(self):
        """Получить клиент для Vision API (OpenAI или Gemini) из конфига"""
        try:
            # Получаем конфигурацию
            from app.services.llm_config_service import llm_config_service
            config = llm_config_service.get_config()
            
            # Ищем провайдера с поддержкой Vision API (не обязательно активного)
            vision_providers = []
            
            # Проверяем Groq Vision (приоритет - быстрый и надежный)
            if config.groq.api_key and config.groq.vision_model:
                vision_providers.append(("groq", config.groq))
            
            # Проверяем Gemini (бесплатный, но с квотами)
            if config.gemini.api_key and config.gemini.vision_model:
                vision_providers.append(("gemini", config.gemini))
            
            # Проверяем OpenAI
            if config.openai.api_key and config.openai.api_key.startswith("sk-"):
                vision_providers.append(("openai", config.openai))
            
            # Если нет подходящих провайдеров, используем активного (fallback)
            if not vision_providers:
                provider = config.provider
                provider_config = llm_config_service.get_provider_config(provider)
                api_key = provider_config.api_key
            else:
                # Используем первого доступного провайдера с Vision
                provider, provider_config = vision_providers[0]
                api_key = provider_config.api_key
            
            # Fallback на старый способ, если в конфиге нет ключа
            if not api_key:
                from app.services.llm_key_service import llm_key_service
                api_key = await llm_key_service.get_active_key()
                if not api_key:
                    api_key = settings.OPENAI_API_KEY
                    if api_key and api_key.startswith("AIza"):
                        provider = "gemini"
                    else:
                        provider = "openai"
            
            if not api_key:
                return None, None
            
            # Получаем vision модель из конфига
            if provider == "gemini":
                # Для Gemini используем vision модель или text модель, но только если они настроены
                if provider_config.vision_model:
                    vision_model_id = provider_config.vision_model
                elif provider_config.text_model:
                    vision_model_id = provider_config.text_model
                else:
                    logger.error("❌ Vision model not configured for Gemini. Please select a model in admin panel.")
                    return None, None
            elif provider == "groq":
                # Для Groq используем специальную Vision модель
                vision_model_id = provider_config.vision_model or "meta-llama/llama-4-scout-17b-16e-instruct"
            else:
                vision_model_id = provider_config.vision_model or provider_config.text_model or "gpt-4o"
            
            # Пересоздаем клиент если ключ, провайдер или модель изменились
            if (api_key != self._current_api_key or 
                provider != self._current_provider or
                vision_model_id != getattr(self, '_current_vision_model', None)):
                
                self._current_api_key = api_key
                self._current_provider = provider
                self._current_vision_model = vision_model_id
                
                if provider == "gemini":
                    if not GEMINI_AVAILABLE:
                        logger.error("❌ OCR Service: Gemini API not available. Install google-generativeai package.")
                        return None, None
                    try:
                        genai.configure(api_key=api_key)
                        self.gemini_model = genai.GenerativeModel(vision_model_id)
                        masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
                        logger.debug(f"OCR Service: Gemini client initialized (key: {masked_key}, model: {vision_model_id})")
                        return self.gemini_model, "gemini"
                    except Exception as e:
                        error_msg = str(e)
                        if "404" in error_msg and "not found" in error_msg.lower():
                            logger.error(f"❌ Vision model '{vision_model_id}' not found. Resetting model in config.")
                            # Обнуляем несуществующую модель
                            from app.services.llm_config_service import llm_config_service
                            llm_config_service.set_models("gemini", vision_model=None)
                            return None, None
                        else:
                            raise
                
                elif provider == "groq":
                    if not OPENAI_VISION_AVAILABLE:
                        return None, None
                    # Groq использует OpenAI-совместимый API
                    self.groq_client = AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
                    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
                    logger.debug(f"OCR Service: Groq client initialized (key: {masked_key}, model: {vision_model_id})")
                    return self.groq_client, "groq"
                
                elif provider in ["openai", "other", None]:
                    if not OPENAI_VISION_AVAILABLE:
                        return None, None
                    self.openai_client = AsyncOpenAI(api_key=api_key)
                    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
                    logger.debug(f"OCR Service: OpenAI client initialized (key: {masked_key}, model: {vision_model_id})")
                    return self.openai_client, "openai"
            
            # Возвращаем существующий клиент
            if hasattr(self, 'gemini_model') and self._current_provider == "gemini":
                return self.gemini_model, "gemini"
            elif hasattr(self, 'groq_client') and self._current_provider == "groq":
                return self.groq_client, "groq"
            elif self.openai_client and self._current_provider in ["openai", "other", None]:
                return self.openai_client, "openai"
            
            return None, None
        except Exception as e:
            logger.error(f"Failed to initialize vision client: {e}")
            return None, None
    
    async def extract_text_from_image(self, image_path: str) -> Optional[str]:
        """
        Извлекает текст с изображения используя доступный OCR сервис
        Кэширует результаты, чтобы не обрабатывать одно и то же изображение повторно
        
        Args:
            image_path: Путь к файлу изображения
            
        Returns:
            Распознанный текст или None при ошибке
        """
        if not os.path.exists(image_path):
            logger.warning(f"Image file not found: {image_path}")
            return None
        
        # Нормализуем путь для проверки кэша и статуса
        normalized_path = os.path.abspath(image_path)
        
        # Проверяем, не обрабатывали ли мы это изображение уже (кэш)
        if normalized_path in self._ocr_cache:
            logger.debug(f"⏭️ Returning cached OCR result for: {image_path}")
            return self._ocr_cache[normalized_path]
        
        # Проверяем статус OCR через QuotaManager
        from app.services.quota_manager import quota_manager
        
        # Проверяем лимит на количество вызовов OCR
        if not quota_manager.can_make_ocr_call():
            logger.warning(f"⚠️ OCR call limit reached. Skipping OCR for {image_path}")
            return None
        
        # Проверяем статус OCR для этого сообщения
        ocr_status = quota_manager.get_ocr_status(normalized_path)
        if ocr_status and ocr_status.status == "success":
            # Если OCR был успешным, но кэш пуст (например, после перезапуска), 
            # пропускаем проверку квот и пытаемся извлечь текст снова
            logger.debug(f"🔄 OCR was successful before but cache is empty, re-extracting: {image_path}")
        elif quota_manager.should_skip_ocr(normalized_path):
            logger.debug(f"⏭️ Skipping OCR for {image_path} (previous error, attempts exhausted)")
            return None
        
        # Пробуем Vision API (OpenAI или Gemini) сначала (быстрее и точнее)
        client, provider = await self._get_vision_client()
        
        # Проверяем доступность провайдера
        if provider and not quota_manager.is_provider_available(provider):
            logger.warning(f"⚠️ {provider.upper()} is temporarily unavailable (quota exceeded). Skipping OCR.")
            # Помечаем как ошибку, но не permanent_error (может восстановиться)
            quota_manager.set_ocr_status(normalized_path, "error", 
                                        error=f"{provider.upper()} quota exceeded", 
                                        error_type="429")
            return None
        
        if client:
            quota_manager.increment_ocr_call_count()
            try:
                if provider == "gemini":
                    text = await self._extract_with_gemini_vision(image_path, client, normalized_path)
                elif provider == "groq":
                    text = await self._extract_with_groq_vision(image_path, client, normalized_path)
                else:
                    text = await self._extract_with_openai_vision(image_path, client, normalized_path)
                if text:
                    # Успешно обработано
                    quota_manager.set_ocr_status(normalized_path, "success")
                    return text
            except Exception as e:
                # Ошибка будет обработана в методах _extract_with_*
                pass
        
        # Fallback на EasyOCR (не использует квоты)
        if EASYOCR_AVAILABLE:
            quota_manager.increment_ocr_call_count()
            text = await self._extract_with_easyocr(image_path)
            if text:
                quota_manager.set_ocr_status(normalized_path, "success")
                return text
        
        logger.warning(f"No OCR service available to extract text from {image_path}")
        return None
    
    async def _extract_with_openai_vision(self, image_path: str, client, message_key: str) -> Optional[str]:
        """Извлекает текст используя OpenAI Vision API"""
        try:
            if not client:
                return None
            
            import base64
            
            # Читаем изображение и кодируем в base64
            with open(image_path, 'rb') as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Определяем MIME тип
            ext = Path(image_path).suffix.lower()
            mime_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }.get(ext, 'image/jpeg')
            
            # Получаем модель из конфига (для OpenAI)
            from app.services.llm_config_service import llm_config_service
            config = llm_config_service.get_config()
            if config.provider == "openai":
                provider_config = llm_config_service.get_provider_config("openai")
                vision_model = provider_config.vision_model or provider_config.text_model or "gpt-4o"
            else:
                vision_model = "gpt-4o"  # Fallback
            
            # Запрос к OpenAI Vision API
            response = await client.chat.completions.create(
                model=vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Распознай весь текст на этом изображении. Верни только текст, без дополнительных комментариев. Если текст на русском языке, сохрани его на русском. Если есть контактная информация, даты, названия турниров или событий - обязательно включи их."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000
            )
            
            text = response.choices[0].message.content.strip()
            if text:
                # Сохраняем в кэш обработанных изображений (нормализованный путь)
                normalized_path = os.path.abspath(image_path)
                self._ocr_cache[normalized_path] = text
                logger.info(f"✅ Extracted {len(text)} chars from image using OpenAI Vision")
                return text
            
            return None
            
        except Exception as e:
            from app.services.quota_manager import quota_manager
            error_msg = str(e)
            error_type = None
            
            # Определяем тип ошибки
            if "429" in error_msg or "rate_limit" in error_msg.lower() or "quota" in error_msg.lower():
                error_type = "429"
                # Помечаем OpenAI как недоступный на 60 секунд
                quota_manager.mark_provider_unavailable("openai", retry_delay=60.0)
                logger.warning("⚠️ OpenAI quota exceeded. Marking as unavailable for 60 seconds.")
            
            # Обновляем статус OCR
            quota_manager.set_ocr_status(message_key, "error", error=error_msg, error_type=error_type)
            logger.error(f"Error extracting text with OpenAI Vision: {e}", exc_info=True)
            return None
    
    async def _extract_with_gemini_vision(self, image_path: str, model, message_key: str) -> Optional[str]:
        """Извлекает текст используя Gemini Vision API"""
        if not model:
            return None
        
        # Проверяем дневную квоту Gemini перед вызовом
        if gemini_quota_state and not gemini_quota_state.is_available():
            logger.warning(
                "Gemini daily quota exhausted (OCR). Skipping vision OCR for this image."
            )
            return None
        
        import asyncio
        from PIL import Image
        
        # Читаем изображение
        try:
            image = Image.open(image_path)
        except Exception as e:
            logger.error(f"Error opening image {image_path}: {e}", exc_info=True)
            return None
        
        prompt = "Распознай весь текст на этом изображении. Верни только текст, без дополнительных комментариев. Если текст на русском языке, сохрани его на русском. Если есть контактная информация, даты, названия турниров или событий - обязательно включи их."
        
        # Gemini API синхронный, оборачиваем в thread pool
        def generate_sync():
            try:
                response = model.generate_content([prompt, image])
                return response.text
            except Exception as e:
                error_msg = str(e)
                if "404" in error_msg and "not found" in error_msg.lower():
                    # Модель не найдена - обнуляем её в конфиге
                    logger.error(f"❌ Vision model not found during OCR. Resetting model in config.")
                    from app.services.llm_config_service import llm_config_service
                    llm_config_service.set_models("gemini", vision_model=None)
                raise
        
        try:
            text = await asyncio.to_thread(generate_sync)
        except ResourceExhausted as e:
            msg = str(e)
            logger.error("Error extracting text with Gemini Vision (quota): %s", msg)

            if gemini_quota_state and "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in msg:
                gemini_quota_state.mark_daily_exhausted()

            # Возвращаем None, чтобы message_analysis просто пропустил OCR
            return None
        except Exception as e:
            error_msg = str(e)
            # Проверяем, не является ли это ResourceExhausted (на случай, если импорт не сработал)
            if "ResourceExhausted" in str(type(e).__name__) or "429" in error_msg:
                if gemini_quota_state and "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in error_msg:
                    gemini_quota_state.mark_daily_exhausted()
                return None
            
            # Другие ошибки обрабатываем через quota_manager
            from app.services.quota_manager import quota_manager
            error_type = None
            retry_delay = 60.0
            
            if "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                error_type = "429"
                try:
                    import re
                    retry_match = re.search(r'retry.*?(\d+)', error_msg, re.IGNORECASE)
                    if retry_match:
                        retry_delay = float(retry_match.group(1))
                except:
                    pass
                
                quota_manager.mark_provider_unavailable("gemini", retry_delay=retry_delay)
                logger.warning(f"⚠️ Gemini quota exceeded. Marking as unavailable for {retry_delay} seconds.")
            
            quota_manager.set_ocr_status(message_key, "error", error=error_msg, error_type=error_type)
            logger.error(f"Error extracting text with Gemini Vision: {e}", exc_info=True)
            return None
        
        if text and text.strip():
            # Сохраняем в кэш обработанных изображений
            normalized_path = os.path.abspath(image_path)
            self._ocr_cache[normalized_path] = text.strip()
            logger.info(f"✅ Extracted text with Gemini Vision from {image_path} ({len(text)} chars)")
            return text.strip()
        
        return None
    
    async def _extract_with_groq_vision(self, image_path: str, client, message_key: str) -> Optional[str]:
        """Извлекает текст используя Groq Vision API"""
        try:
            if not client:
                return None
            
            import base64
            
            # Читаем изображение и кодируем в base64
            with open(image_path, 'rb') as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Определяем MIME тип
            ext = Path(image_path).suffix.lower()
            mime_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }.get(ext, 'image/jpeg')
            
            # Получаем модель из конфига (для Groq)
            from app.services.llm_config_service import llm_config_service
            config = llm_config_service.get_config()
            vision_model = config.groq.vision_model or "meta-llama/llama-4-scout-17b-16e-instruct"
            
            # Запрос к Groq Vision API
            response = await client.chat.completions.create(
                model=vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Распознай весь текст на этом изображении. Верни только текст, без дополнительных комментариев. Если текст на русском языке, сохрани его на русском. Если есть контактная информация, даты, названия турниров или событий - обязательно включи их."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000
            )
            
            text = response.choices[0].message.content.strip()
            if text:
                # Сохраняем в кэш обработанных изображений (нормализованный путь)
                normalized_path = os.path.abspath(image_path)
                self._ocr_cache[normalized_path] = text
                logger.info(f"✅ Extracted {len(text)} chars from image using Groq Vision")
                return text
            
            return None
            
        except Exception as e:
            from app.services.quota_manager import quota_manager
            error_msg = str(e)
            error_type = None
            
            # Определяем тип ошибки
            if "429" in error_msg or "rate_limit" in error_msg.lower() or "quota" in error_msg.lower():
                error_type = "429"
                # Помечаем Groq как недоступный на 60 секунд
                quota_manager.mark_provider_unavailable("groq", retry_delay=60.0)
                logger.warning("⚠️ Groq quota exceeded. Marking as unavailable for 60 seconds.")
            
            # Обновляем статус OCR
            quota_manager.set_ocr_status(message_key, "error", error=error_msg, error_type=error_type)
            logger.error(f"Error extracting text with Groq Vision: {e}", exc_info=True)
            return None
    
    async def _extract_with_easyocr(self, image_path: str) -> Optional[str]:
        """Извлекает текст используя EasyOCR"""
        if not EASYOCR_AVAILABLE:
            return None
        
        try:
            reader = self._get_easyocr_reader()
            if not reader:
                return None
            
            # Запускаем OCR в отдельном потоке, чтобы не блокировать async loop
            import asyncio
            loop = asyncio.get_event_loop()
            
            def run_ocr():
                try:
                    result = reader.readtext(image_path, detail=0)
                    return " ".join(result)
                except Exception as e:
                    logger.error(f"EasyOCR error: {e}")
                    return ""
            
            text = await loop.run_in_executor(None, run_ocr)
            
            if text and text.strip():
                # Сохраняем в кэш обработанных изображений (нормализованный путь)
                normalized_path = os.path.abspath(image_path)
                self._ocr_cache[normalized_path] = text.strip()
                logger.info(f"✅ Extracted {len(text)} chars from image using EasyOCR")
                return text.strip()
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting text with EasyOCR: {e}", exc_info=True)
            return None


# Создаем глобальный экземпляр сервиса
ocr_service = OCRService()

