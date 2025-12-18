"""
Сервис для управления LLM ключами различных провайдеров (OpenAI, Gemini, и т.д.)
Хранит ключи в JSON файле и позволяет динамически переключать активный ключ
Поддерживает ключи любых форматов, не только OpenAI
"""
import json
import os
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
from app.core.config import settings
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class LLMKeyService:
    def __init__(self):
        self.keys_file = os.path.join(settings.DATA_DIR, "llm_keys.json")
        self._ensure_keys_file_exists()
    
    def _detect_provider(self, key: str, explicit_provider: Optional[str] = None) -> str:
        """Определяет провайдера по ключу или возвращает переданный явно."""
        if explicit_provider:
            return explicit_provider
        
        if not key:
            return "openai"
        
        if key.startswith("AIza"):
            return "gemini"
        if key.startswith("gsk_"):
            return "groq"
        if key.startswith("sk-mega"):
            return "megallm"
        if key.startswith("sk-"):
            return "openai"
        return "openai"
    
    def _ensure_keys_file_exists(self):
        """Создает файл с ключами, если его нет, и инициализирует из .env если есть"""
        if not os.path.exists(self.keys_file):
            logger.info(f"Creating LLM keys file: {self.keys_file}")
            keys: List[Dict] = []
            env_candidates = []
            
            if settings.OPENAI_API_KEY:
                env_candidates.append((settings.OPENAI_API_KEY, None))
            if getattr(settings, "GEMINI_API_KEY", None):
                env_candidates.append((settings.GEMINI_API_KEY, "gemini"))
            if getattr(settings, "GROQ_API_KEY", None):
                env_candidates.append((settings.GROQ_API_KEY, "groq"))
            
            has_active = False
            for raw_key, explicit_provider in env_candidates:
                provider = self._detect_provider(raw_key, explicit_provider)
                keys.append({
                    "key": raw_key,
                    "provider": provider,
                    "is_active": not has_active,  # первый добавленный ключ станет активным
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
                has_active = True
                logger.info(f"Initialized LLM keys file with key from .env (provider: {provider})")
            
            self._save_keys(keys)
        else:
            # Проверяем, есть ли активный ключ
            keys = self._load_keys()
            active_keys = [k for k in keys if k.get("is_active", False)]
            if not active_keys:
                env_candidates = []
                if settings.OPENAI_API_KEY:
                    env_candidates.append((settings.OPENAI_API_KEY, None))
                if getattr(settings, "GEMINI_API_KEY", None):
                    env_candidates.append((settings.GEMINI_API_KEY, "gemini"))
                if getattr(settings, "GROQ_API_KEY", None):
                    env_candidates.append((settings.GROQ_API_KEY, "groq"))
                
                if env_candidates:
                    raw_key, explicit_provider = env_candidates[0]
                    provider = self._detect_provider(raw_key, explicit_provider)
                    keys.append({
                        "key": raw_key,
                        "provider": provider,
                        "is_active": True,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    })
                    self._save_keys(keys)
                    logger.info(f"Added key from .env as active key (provider: {provider})")
    
    def _load_keys(self) -> List[Dict]:
        """Загружает ключи из JSON файла"""
        try:
            if os.path.exists(self.keys_file):
                with open(self.keys_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    return []
            return []
        except Exception as e:
            logger.error(f"Error loading LLM keys: {e}", exc_info=True)
            return []
    
    def _save_keys(self, keys: List[Dict]):
        """Сохраняет ключи в JSON файл"""
        try:
            os.makedirs(os.path.dirname(self.keys_file), exist_ok=True)
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump(keys, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(keys)} LLM keys to {self.keys_file}")
        except Exception as e:
            logger.error(f"Error saving LLM keys: {e}", exc_info=True)
            raise
    
    async def get_active_key(self) -> Optional[str]:
        """Возвращает текущий активный ключ"""
        keys = self._load_keys()
        for key_data in keys:
            if key_data.get("is_active", False):
                return key_data.get("key")
        return None
    
    async def get_all_keys(self) -> List[Dict]:
        """Возвращает список всех ключей (с маскировкой)"""
        keys = self._load_keys()
        result = []
        for key_data in keys:
            key = key_data.get("key", "")
            masked_key = self._mask_key(key)
            result.append({
                "key": masked_key,
                "provider": key_data.get("provider", "openai"),
                "is_active": key_data.get("is_active", False),
                "is_working": key_data.get("is_working"),
                "last_checked": key_data.get("last_checked"),
                "check_error": key_data.get("check_error"),
                "created_at": key_data.get("created_at", ""),
                "full_key": key  # Для внутреннего использования
            })
        return result
    
    def _mask_key(self, key: str) -> str:
        """Маскирует ключ для отображения"""
        if not key or len(key) < 10:
            return "***"
        
        # OpenAI ключи обычно начинаются с sk-
        if key.startswith("sk-"):
            parts = key.split("-")
            if len(parts) >= 2:
                prefix = "-".join(parts[:2])  # sk-proj или sk-xxx
                if len(key) > 20:
                    # Показываем первые 7 символов после префикса и последние 5
                    prefix_len = len(prefix) + 1
                    visible_start = key[prefix_len:prefix_len+7]
                    visible_end = key[-5:]
                    return f"{prefix}-{visible_start}...{visible_end}"
                else:
                    return f"{prefix}-***"
            return "sk-***"
        elif key.startswith("AIza"):  # Google API ключи
            if len(key) > 20:
                return f"AIza...{key[-5:]}"
            return "AIza***"
        elif key.startswith("gsk_"):  # Groq API ключи
            if len(key) > 20:
                return f"gsk_...{key[-5:]}"
            return "gsk_***"
        elif key.startswith("sk-mega"):  # MegaLLM API ключи
            if len(key) > 20:
                return f"sk-mega...{key[-5:]}"
            return "sk-mega***"
        else:
            # Для других форматов ключей (универсальная маскировка)
            if len(key) > 15:
                return f"{key[:7]}...{key[-5:]}"
            return "***"
    
    async def add_new_key(self, key: str, provider: str = "openai") -> bool:
        """
        Добавляет новый ключ и делает его активным.
        Все остальные ключи становятся неактивными.
        
        Args:
            key: API ключ (любого формата)
            provider: Тип провайдера (openai, gemini, и т.д.). По умолчанию "openai"
        """
        if not key or not key.strip():
            raise ValueError("Ключ не может быть пустым")
        
        key = key.strip()
        
        # Определяем провайдера автоматически по формату ключа, если не указан явно
        if provider == "openai" and not key.startswith("sk-"):
            # Если указан openai, но ключ не начинается с sk-, пытаемся определить автоматически
            if key.startswith("AIza"):
                provider = "gemini"
            elif key.startswith("gsk_"):
                provider = "groq"
            elif key.startswith("sk-mega"):
                provider = "megallm"
            # Для других форматов оставляем openai по умолчанию
        elif provider == "other":
            # Пытаемся определить провайдера автоматически для unknown
            if key.startswith("AIza"):
                provider = "gemini"
            elif key.startswith("gsk_"):
                provider = "groq"
            elif key.startswith("sk-"):
                provider = "openai"
            elif key.startswith("sk-mega"):
                provider = "megallm"
        
        keys = self._load_keys()
        
        # Проверяем, не является ли это дубликатом
        for existing_key in keys:
            if existing_key.get("key") == key:
                # Если ключ уже существует, просто делаем его активным
                logger.info("Key already exists, activating it")
                for k in keys:
                    k["is_active"] = (k.get("key") == key)
                self._save_keys(keys)
                return True
        
        # Делаем все существующие ключи неактивными
        for k in keys:
            k["is_active"] = False
        
        # Добавляем новый ключ как активный
        new_key_data = {
            "key": key,
            "provider": provider,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_working": None,  # Будет проверено при добавлении
            "last_checked": None
        }
        keys.append(new_key_data)
        
        self._save_keys(keys)
        logger.info(f"New LLM key added and activated (provider: {provider})")
        
        # Проверяем работоспособность нового ключа
        try:
            is_working, error_msg = await self.check_and_update_key_status(key, provider)
            if is_working:
                logger.info(f"✅ New key is working")
            else:
                logger.warning(f"⚠️ New key test failed: {error_msg}")
        except Exception as e:
            logger.error(f"Error testing new key: {e}", exc_info=True)
        
        return True
    
    async def get_active_provider(self) -> Optional[str]:
        """Возвращает тип провайдера активного ключа"""
        keys = self._load_keys()
        for key_data in keys:
            if key_data.get("is_active", False):
                return key_data.get("provider", "openai")
        return None
    
    async def get_active_key_masked(self) -> Optional[str]:
        """Возвращает маскированный активный ключ для отображения"""
        active_key = await self.get_active_key()
        if active_key:
            return self._mask_key(active_key)
        return None
    
    async def delete_key_by_index(self, index: int) -> bool:
        """
        Удаляет ключ по индексу из истории.
        Нельзя удалить активный ключ.
        
        Args:
            index: Индекс ключа в списке (0-based)
        
        Returns:
            bool: True если ключ удален, False если не удалось (например, ключ активен)
        
        Raises:
            ValueError: Если индекс невалиден или ключ активен
        """
        keys = self._load_keys()
        
        if index < 0 or index >= len(keys):
            raise ValueError(f"Неверный индекс ключа: {index}. Всего ключей: {len(keys)}")
        
        key_to_delete = keys[index]
        
        # Проверяем, не является ли ключ активным
        if key_to_delete.get("is_active", False):
            raise ValueError("Нельзя удалить активный ключ. Сначала активируйте другой ключ.")
        
        # Удаляем ключ
        keys.pop(index)
        self._save_keys(keys)
        
        logger.info(f"✅ Deleted key at index {index} (provider: {key_to_delete.get('provider', 'unknown')})")
        return True
    
    async def test_key(self, key: str, provider: str = "openai") -> Tuple[bool, Optional[str]]:
        """
        Проверяет работоспособность ключа через реальный запрос к API.
        
        Args:
            key: API ключ для проверки
            provider: Тип провайдера (openai, gemini, и т.д.)
        
        Returns:
            Tuple[bool, Optional[str]]: (работает ли ключ, сообщение об ошибке если не работает)
        """
        if not key or not key.strip():
            return False, "Ключ пустой"
        
        try:
            if provider == "openai" or provider == "other":
                # Дополнительная проверка формата ключа
                if key.startswith("AIza"):
                    return False, "Ключ имеет формат Gemini (AIza...), но указан провайдер OpenAI. Используйте ключ формата sk-... для OpenAI."
                
                # Проверяем через OpenAI API
                client = AsyncOpenAI(api_key=key)
                
                # Делаем минимальный тестовый запрос
                response = await client.chat.completions.create(
                    model="gpt-3.5-turbo",  # Используем более дешевую модель для теста
                    messages=[
                        {"role": "user", "content": "test"}
                    ],
                    max_tokens=5,
                    temperature=0
                )
                
                # Если получили ответ, ключ работает
                if response and response.choices:
                    logger.info(f"✅ Key test successful for provider: {provider}")
                    return True, None
                else:
                    return False, "Получен пустой ответ от API"
            
            elif provider == "groq":
                # Проверяем через Groq (OpenAI-совместимый API)
                try:
                    client = AsyncOpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
                    response = await client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": "test"}],
                        max_tokens=5,
                        temperature=0
                    )
                    if response and response.choices:
                        logger.info("✅ Key test successful for provider: groq")
                        return True, None
                    return False, "Получен пустой ответ от API"
                except Exception as e:
                    error_msg = str(e)
                    if "401" in error_msg or "unauthorized" in error_msg.lower():
                        return False, "Неверный API ключ Groq"
                    elif "quota" in error_msg.lower():
                        return False, "Превышена квота Groq API"
                    return False, f"Ошибка проверки: {error_msg[:100]}"
            
            elif provider == "megallm":
                # OpenAI-совместимый API MegaLLM
                try:
                    # Получаем модель из конфигурации или используем базовую
                    from app.services.llm_config_service import llm_config_service
                    config = llm_config_service.get_config()
                    test_model = config.megallm.text_model or "llama3-8b-instruct"
                    
                    client = AsyncOpenAI(api_key=key, base_url="https://ai.megallm.io/v1")
                    response = await client.chat.completions.create(
                        model=test_model,
                        messages=[{"role": "user", "content": "test"}],
                        max_tokens=5,
                        temperature=0
                    )
                    if response and response.choices:
                        logger.info(f"✅ Key test successful for provider: megallm (model: {test_model})")
                        return True, None
                    return False, "Получен пустой ответ от API"
                except Exception as e:
                    error_msg = str(e)
                    if "401" in error_msg or "unauthorized" in error_msg.lower():
                        return False, "Неверный API ключ MegaLLM"
                    elif "quota" in error_msg.lower():
                        return False, "Превышена квота MegaLLM API"
                    return False, f"Ошибка проверки: {error_msg[:100]}"
            
            elif provider == "gemini":
                # Проверяем через Gemini API
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=key)
                    
                    # Получаем список доступных моделей и используем первую доступную
                    models = genai.list_models()
                    available_model = None
                    for model in models:
                        methods = getattr(model, "supported_generation_methods", [])
                        if "generateContent" in methods:
                            available_model = model.name
                            break
                    
                    if not available_model:
                        return False, "Не найдено доступных моделей с generateContent"
                    
                    # Используем найденную модель для теста
                    model = genai.GenerativeModel(available_model)
                    
                    # Делаем минимальный тестовый запрос
                    response = model.generate_content("test")
                    
                    if response and response.text:
                        logger.info(f"✅ Key test successful for provider: {provider} (model: {available_model})")
                        return True, None
                    else:
                        return False, "Получен пустой ответ от API"
                except ImportError:
                    return False, "Google Generative AI библиотека не установлена. Установите: pip install google-generativeai"
                except Exception as e:
                    error_msg = str(e)
                    if "404" in error_msg and "not found" in error_msg.lower():
                        return False, f"Модель не найдена: {error_msg[:150]}. Пожалуйста, обновите конфигурацию и выберите модель из списка доступных."
                    elif "API_KEY_INVALID" in error_msg or "invalid" in error_msg.lower():
                        return False, "Неверный API ключ Gemini"
                    elif "quota" in error_msg.lower() or "QUOTA" in error_msg:
                        return False, "Превышена квота API. Проверьте баланс."
                    else:
                        return False, f"Ошибка проверки: {error_msg[:100]}"
            
            elif provider == "anthropic":
                # TODO: Добавить проверку для Anthropic API
                logger.warning("Anthropic key test not implemented yet")
                return True, None
            
            else:
                # Для неизвестных провайдеров пробуем OpenAI формат
                try:
                    client = AsyncOpenAI(api_key=key)
                    response = await client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": "test"}],
                        max_tokens=5,
                        temperature=0
                    )
                    if response and response.choices:
                        return True, None
                    return False, "Получен пустой ответ от API"
                except:
                    return False, "Не удалось проверить ключ для данного провайдера"
        
        except Exception as e:
            error_msg = str(e)
            
            # Определяем тип ошибки
            if "insufficient_quota" in error_msg.lower() or "exceeded your current quota" in error_msg.lower():
                return False, "Превышена квота API. Проверьте баланс."
            elif "invalid_api_key" in error_msg.lower() or "incorrect api key" in error_msg.lower():
                return False, "Неверный API ключ"
            elif "rate_limit" in error_msg.lower():
                return False, "Превышен лимит запросов. Попробуйте позже."
            elif "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
                return False, "Ошибка аутентификации. Проверьте ключ."
            else:
                return False, f"Ошибка проверки: {error_msg[:100]}"
    
    async def check_and_update_key_status(self, key: str, provider: str = "openai") -> Tuple[bool, Optional[str]]:
        """
        Проверяет ключ и обновляет его статус в файле.
        Если ошибка связана с несуществующей моделью, обнуляет модель в конфиге.
        
        Args:
            key: API ключ для проверки
            provider: Тип провайдера
        
        Returns:
            Tuple[bool, Optional[str]]: (работает ли ключ, сообщение об ошибке)
        """
        is_working, error_msg = await self.test_key(key, provider)
        
        # Если ошибка связана с несуществующей моделью, обнуляем модель в конфиге
        if not is_working and error_msg and ("404" in error_msg or "not found" in error_msg.lower()):
            if provider == "gemini":
                try:
                    from app.services.llm_config_service import llm_config_service
                    config = llm_config_service.get_config()
                    if config.provider == "gemini" and config.gemini.api_key == key:
                        logger.warning("Model not found error detected, resetting models in config")
                        llm_config_service.set_models("gemini", text_model=None, vision_model=None)
                except Exception as e:
                    logger.error(f"Error resetting models: {e}", exc_info=True)
        
        # Обновляем статус в файле
        keys = self._load_keys()
        for key_data in keys:
            if key_data.get("key") == key:
                key_data["is_working"] = is_working
                key_data["last_checked"] = datetime.now(timezone.utc).isoformat()
                if error_msg:
                    key_data["check_error"] = error_msg
                else:
                    key_data.pop("check_error", None)
                self._save_keys(keys)
                logger.info(f"Updated key status: is_working={is_working}, error={error_msg}")
                break
        
        return is_working, error_msg
    
    async def check_active_key(self) -> Tuple[bool, Optional[str]]:
        """
        Проверяет активный ключ и обновляет его статус.
        
        Returns:
            Tuple[bool, Optional[str]]: (работает ли ключ, сообщение об ошибке)
        """
        active_key = await self.get_active_key()
        if not active_key:
            return False, "Активный ключ не установлен"
        
        keys = self._load_keys()
        provider = "openai"
        for key_data in keys:
            if key_data.get("key") == active_key:
                provider = key_data.get("provider", "openai")
                break
        
        return await self.check_and_update_key_status(active_key, provider)
    
    async def get_key_status(self, key: str) -> Dict:
        """
        Возвращает статус ключа (работает ли, когда проверялся, ошибка если есть).
        
        Args:
            key: API ключ
        
        Returns:
            Dict с полями: is_working, last_checked, check_error
        """
        keys = self._load_keys()
        for key_data in keys:
            if key_data.get("key") == key:
                return {
                    "is_working": key_data.get("is_working", None),
                    "last_checked": key_data.get("last_checked"),
                    "check_error": key_data.get("check_error")
                }
        return {"is_working": None, "last_checked": None, "check_error": None}
    
    async def activate_key(self, key: str) -> bool:
        """
        Активирует существующий ключ из истории.
        Все остальные ключи становятся неактивными.
        
        Args:
            key: API ключ для активации
        
        Returns:
            bool: True если ключ найден и активирован, False если ключ не найден
        """
        if not key or not key.strip():
            raise ValueError("Ключ не может быть пустым")
        
        key = key.strip()
        keys = self._load_keys()
        
        # Ищем ключ в списке
        key_found = False
        for key_data in keys:
            if key_data.get("key") == key:
                key_found = True
                break
        
        if not key_found:
            logger.warning(f"Key not found in history: {self._mask_key(key)}")
            return False
        
        # Делаем все ключи неактивными
        for k in keys:
            k["is_active"] = (k.get("key") == key)
        
        self._save_keys(keys)
        logger.info(f"Key activated: {self._mask_key(key)}")
        return True
    
    async def activate_key_by_index(self, index: int) -> bool:
        """
        Активирует ключ по его индексу в списке.
        
        Args:
            index: Индекс ключа в списке (0-based)
        
        Returns:
            bool: True если ключ найден и активирован, False если индекс неверный
        """
        keys = self._load_keys()
        
        if index < 0 or index >= len(keys):
            logger.warning(f"Invalid key index: {index}")
            return False
        
        key_data = keys[index]
        key = key_data.get("key")
        
        if not key:
            logger.warning(f"Key at index {index} has no key value")
            return False
        
        return await self.activate_key(key)

# Создаем глобальный экземпляр сервиса
llm_key_service = LLMKeyService()

