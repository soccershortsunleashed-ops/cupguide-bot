from openai import AsyncOpenAI, RateLimitError
from app.core.config import settings
from app.services.llm_key_service import llm_key_service
from app.services.llm_config_service import llm_config_service
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

# Попытка импортировать Gemini
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not available. Gemini support will be disabled.")

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

class LLMService:
    def __init__(self):
        self.client = None  # OpenAI клиент или Gemini модель
        self.provider = None  # "openai" или "gemini"
        self.model = None  # Модель OpenAI (из конфига)
        self.gemini_model = None  # Модель Gemini (из конфига)
        self.configured = False
        self._current_api_key = None
        # Инициализация будет выполнена асинхронно
    
    async def _ensure_client(self):
        """Обеспечивает наличие настроенного клиента с актуальным ключом из конфига"""
        try:
            # Получаем конфигурацию
            config = llm_config_service.get_config()
            provider = config.provider
            provider_config = llm_config_service.get_provider_config(provider)
            
            api_key = provider_config.api_key
            
            # Fallback на старый способ, если в конфиге нет ключа
            if not api_key:
                api_key = await llm_key_service.get_active_key()
                if not api_key and settings.OPENAI_API_KEY:
                    api_key = settings.OPENAI_API_KEY
                    if api_key.startswith("AIza"):
                        provider = "gemini"
                    else:
                        provider = "openai"
            
            if not api_key:
                self.client = None
                self.configured = False
                self.provider = None
                logger.warning("⚠️ No active LLM key found. LLM features will not work.")
                return
            
            # Получаем модели из конфига
            if provider == "gemini":
                if not provider_config.text_model:
                    logger.error("❌ Text model not configured for Gemini. Please select a model in admin panel.")
                    self.client = None
                    self.configured = False
                    return
                text_model = provider_config.text_model
            elif provider == "groq":
                text_model = provider_config.text_model or "llama-3.3-70b-versatile"
            elif provider == "megallm":
                text_model = provider_config.text_model or "gpt-5"
            else:
                text_model = provider_config.text_model or "gpt-4o"
            
            # Если ключ, провайдер или модель изменились, пересоздаем клиент
            if (api_key != self._current_api_key or 
                provider != self.provider or 
                text_model != (self.gemini_model if provider == "gemini" else self.model) or
                self.client is None):
                
                self._current_api_key = api_key
                self.provider = provider
                
                if provider == "gemini":
                    if not GEMINI_AVAILABLE:
                        logger.error("❌ Gemini API not available. Install google-generativeai package.")
                        self.client = None
                        self.configured = False
                        return
                    
                    # Настраиваем Gemini с моделью из конфига
                    try:
                        genai.configure(api_key=api_key)
                        self.gemini_model = text_model
                        self.client = genai.GenerativeModel(text_model)
                        self.configured = True
                        masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
                        logger.info(f"✅ LLM service configured with Gemini API (key: {masked_key}, model: {text_model})")
                    except Exception as e:
                        error_msg = str(e)
                        if "404" in error_msg and "not found" in error_msg.lower():
                            logger.error(f"❌ Model '{text_model}' not found. Resetting model in config.")
                            # Обнуляем несуществующую модель
                            llm_config_service.set_models("gemini", text_model=None, vision_model=None)
                            self.client = None
                            self.configured = False
                            logger.warning("⚠️ Please select a valid model in admin panel.")
                        else:
                            raise
                
                elif provider in ["openai", "other", None]:
                    # Создаем клиент OpenAI с моделью из конфига
                    self.model = text_model
                    self.client = AsyncOpenAI(api_key=api_key)
                    self.configured = True
                    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
                    logger.info(f"✅ LLM service configured with OpenAI API (key: {masked_key}, model: {text_model})")
                elif provider == "megallm":
                    # MegaLLM OpenAI-совместимый API
                    self.model = text_model
                    self.client = AsyncOpenAI(api_key=api_key, base_url="https://ai.megallm.io/v1")
                    self.configured = True
                    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
                    logger.info(f"✅ LLM service configured with MegaLLM API (key: {masked_key}, model: {text_model})")
                elif provider == "groq":
                    # Groq использует OpenAI-совместимый API
                    self.model = text_model
                    self.client = AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
                    self.configured = True
                    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
                    logger.info(f"✅ LLM service configured with Groq API (key: {masked_key}, model: {text_model})")
                else:
                    logger.error(f"❌ Unknown provider: {provider}")
                    self.client = None
                    self.configured = False
                    
        except Exception as e:
            logger.error(f"Failed to configure LLM API: {e}", exc_info=True)
            self.client = None
            self.configured = False
    
    async def refresh_client(self):
        """Принудительно обновляет клиент (используется при смене ключа)"""
        self._current_api_key = None
        await self._ensure_client()

    async def generate_content_async(self, prompt: str, system_prompt: str = None) -> str:
        """
        Универсальный метод для генерации контента через OpenAI или Gemini API.
        При ошибке 429 от Gemini пытается использовать OpenAI как fallback.
        """
        from app.services.quota_manager import quota_manager
        
        await self._ensure_client()
        if not self.configured:
            raise ValueError("LLM is not configured")
        
        # Проверяем доступность провайдера
        if not quota_manager.is_provider_available(self.provider):
            logger.warning(f"⚠️ {self.provider.upper()} is temporarily unavailable (quota exceeded). Skipping LLM call.")
            raise ValueError(f"{self.provider.upper()} quota exceeded. Skipping analysis.")
        
        try:
            if self.provider == "gemini":
                # Проверяем дневную квоту Gemini перед вызовом
                if gemini_quota_state and not gemini_quota_state.is_available():
                    logger.warning(
                        "Gemini daily quota exhausted according to local state. "
                        "Skipping LLM call and returning None."
                    )
                    return None
                
                # Формируем полный промпт с system prompt
                full_prompt = prompt
                if system_prompt:
                    full_prompt = f"{system_prompt}\n\n{prompt}"
                
                # Gemini API синхронный, оборачиваем в thread pool
                def generate_sync():
                    try:
                        response = self.client.generate_content(
                            full_prompt,
                            generation_config=genai.types.GenerationConfig(
                                temperature=0.7
                            )
                        )
                        return response.text
                    except Exception as e:
                        error_msg = str(e)
                        if "404" in error_msg and "not found" in error_msg.lower():
                            # Модель не найдена - обнуляем её в конфиге
                            logger.error(f"❌ Model '{self.gemini_model}' not found during generation. Resetting model in config.")
                            llm_config_service.set_models("gemini", text_model=None, vision_model=None)
                            self.configured = False
                            self.client = None
                        raise
                
                try:
                    result = await asyncio.to_thread(generate_sync)
                    return result
                except ResourceExhausted as e:
                    msg = str(e)
                    logger.error("Gemini ResourceExhausted: %s", msg)

                    # Если видим, что это именно дневной лимит — блокируем до конца суток
                    if gemini_quota_state and "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in msg:
                        gemini_quota_state.mark_daily_exhausted()

                    # Тут специально НЕ ретраем и НЕ пробрасываем исключение,
                    # а возвращаем None, чтобы верхний уровень просто пропустил анализ.
                    return None
            
            else:
                # OpenAI API
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7
                )
                return response.choices[0].message.content
        except RateLimitError as e:
            # Обработка ошибок OpenAI
            if self.provider != "gemini":
                error_code = getattr(e, 'code', None)
                error_type = None
                if hasattr(e, 'response') and e.response:
                    try:
                        error_data = e.response.json()
                        if 'error' in error_data:
                            error_type = error_data['error'].get('type')
                            error_code = error_data['error'].get('code')
                    except:
                        pass
                
                if error_type == 'insufficient_quota' or error_code == 'insufficient_quota':
                    logger.error(
                        "❌ OpenAI API: Превышена квота (insufficient_quota). "
                        "Проверьте баланс и план подписки на https://platform.openai.com/account/billing. "
                        "Анализ сообщений временно отключен."
                    )
                    raise ValueError(
                        "Превышена квота OpenAI API. Проверьте баланс и план подписки. "
                        "Анализ сообщений временно недоступен."
                    )
                else:
                    logger.warning(f"⚠️ OpenAI API rate limit: {e}. Повторная попытка может помочь.")
                    raise ValueError(f"Rate limit exceeded: {str(e)}")
            else:
                raise ValueError(f"Rate limit exceeded: {str(e)}")
        except Exception as e:
            from app.services.quota_manager import quota_manager
            from app.services.llm_config_service import llm_config_service
            error_str = str(e)
            provider_name = "Gemini" if self.provider == "gemini" else "Groq" if self.provider == "groq" else "MegaLLM" if self.provider == "megallm" else "OpenAI"
            
            # Проверяем текст ошибки на наличие insufficient_quota или 429
            is_quota_error = ('insufficient_quota' in error_str.lower() or 
                            'exceeded your current quota' in error_str.lower() or 
                            'quota' in error_str.lower() or
                            '429' in error_str or
                            'rate limit' in error_str.lower())
            
            if is_quota_error:
                retry_delay = 60.0
                # Пытаемся извлечь retry_delay из ошибки
                try:
                    import re
                    retry_match = re.search(r'retry.*?(\d+)', error_str, re.IGNORECASE)
                    if retry_match:
                        retry_delay = float(retry_match.group(1))
                except:
                    pass
                
                # Помечаем провайдера как недоступный
                quota_manager.mark_provider_unavailable(self.provider, retry_delay=retry_delay)
                
                # Если ошибка от Gemini, пытаемся использовать OpenAI как fallback
                if self.provider == "gemini":
                    logger.warning(f"⚠️ Gemini quota exceeded. Trying OpenAI fallback...")
                    try:
                        # Проверяем, есть ли OpenAI ключ
                        config = llm_config_service.get_config()
                        openai_config = llm_config_service.get_provider_config("openai")
                        if openai_config.api_key and quota_manager.is_provider_available("openai"):
                            logger.info("🔄 Falling back to OpenAI for text analysis")
                            # Временно переключаемся на OpenAI
                            old_provider = self.provider
                            old_client = self.client
                            old_model = self.model
                            
                            # Создаем OpenAI клиент
                            from openai import AsyncOpenAI
                            self.provider = "openai"
                            self.client = AsyncOpenAI(api_key=openai_config.api_key)
                            self.model = openai_config.text_model or "gpt-4o"
                            
                            try:
                                # Пробуем выполнить запрос через OpenAI
                                messages = []
                                if system_prompt:
                                    messages.append({"role": "system", "content": system_prompt})
                                messages.append({"role": "user", "content": prompt})
                                
                                response = await self.client.chat.completions.create(
                                    model=self.model,
                                    messages=messages,
                                    temperature=0.7
                                )
                                result = response.choices[0].message.content
                                logger.info("✅ Successfully used OpenAI fallback for text analysis")
                                return result
                            finally:
                                # Восстанавливаем Gemini клиент
                                self.provider = old_provider
                                self.client = old_client
                                self.model = old_model
                    except Exception as fallback_error:
                        logger.error(f"❌ OpenAI fallback also failed: {fallback_error}")
                
                logger.error(
                    f"❌ {provider_name} API: Превышена квота. "
                    "Проверьте баланс и план подписки."
                )
                raise ValueError(
                    f"Превышена квота {provider_name} API. Проверьте баланс и план подписки. "
                    "Анализ сообщений временно недоступен."
                )
            logger.error(f"Error generating content with {provider_name}: {e}")
            raise ValueError(f"Failed to generate content: {str(e)}")

    async def make_summary(self, text: str) -> str:
        await self._ensure_client()
        if not self.configured:
            raise ValueError("LLM is not configured")
        
        system_prompt = "You are a helpful news assistant."
        prompt = (
            "Сделай краткое новостное саммари (1-3 предложения) следующего текста. "
            "Стиль: новостной агрегатор. Пиши по-русски. "
            f"Текст:\n{text}"
        )
        
        try:
            return await self.generate_content_async(prompt, system_prompt)
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            raise ValueError(f"Failed to generate summary: {str(e)}")

    async def make_rewrite(self, text: str) -> str:
        await self._ensure_client()
        if not self.configured:
            raise ValueError("LLM is not configured")
            
        system_prompt = "You are a professional news editor."
        prompt = (
            "Перепиши новость в плавном журнальном стиле. "
            "Не выдумывай новые факты, сохраняй смысл. Пиши по-русски. "
            f"Текст:\n{text}"
        )
        
        try:
            return await self.generate_content_async(prompt, system_prompt)
        except Exception as e:
            logger.error(f"Error generating rewrite: {e}")
            raise
    
    async def process_text_with_prompt(self, text: str, user_prompt: str) -> str:
        """
        Обработать текст с помощью пользовательского промпта.
        Используется для переработки информации о контакте.
        """
        await self._ensure_client()
        if not self.configured:
            raise ValueError("LLM is not configured")
        
        if not user_prompt or not user_prompt.strip():
            raise ValueError("Промпт не может быть пустым")
        
        prompt = (
            f"{user_prompt}\n\n"
            f"Исходный текст:\n{text}\n\n"
            "Обработай текст согласно инструкции выше. Сохраняй важные факты и контакты. Пиши по-русски."
        )
        
        try:
            system_prompt = "You are a helpful assistant that processes and structures information."
            return await self.generate_content_async(prompt, system_prompt)
        except Exception as e:
            logger.error(f"Error processing text with prompt: {e}")
            raise

llm_service = LLMService()
