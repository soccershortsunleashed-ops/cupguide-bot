"""
Сервис для управления конфигурацией LLM (провайдер, ключи, модели)
"""
import json
import os
import logging
from typing import Optional, Dict, Any
from pydantic import BaseModel
from app.core.config import settings

logger = logging.getLogger(__name__)


class ProviderConfig(BaseModel):
    """Конфигурация для одного провайдера"""
    api_key: Optional[str] = None
    text_model: Optional[str] = None
    vision_model: Optional[str] = None


class LLMConfig(BaseModel):
    """Полная конфигурация LLM"""
    provider: str = "openai"  # "openai", "gemini", "groq" или "megallm"
    openai: ProviderConfig = ProviderConfig()
    gemini: ProviderConfig = ProviderConfig()
    groq: ProviderConfig = ProviderConfig()
    megallm: ProviderConfig = ProviderConfig()


class LLMConfigService:
    """Сервис для управления конфигурацией LLM"""
    
    def __init__(self):
        self.config_file = os.path.join(settings.DATA_DIR, "llm_config.json")
        self._ensure_config_file()
    
    def _ensure_config_file(self):
        """Создает файл конфигурации, если его нет"""
        if not os.path.exists(self.config_file):
            logger.info(f"Creating LLM config file: {self.config_file}")
            # Инициализируем с дефолтными значениями
            default_config = LLMConfig(
                provider="openai",
                openai=ProviderConfig(
                    text_model="gpt-4o",
                    vision_model="gpt-4o"
                ),
                gemini=ProviderConfig(
                    text_model=None,  # Будет выбрана пользователем из списка доступных
                    vision_model=None  # Будет выбрана пользователем из списка доступных
                ),
                groq=ProviderConfig(
                    text_model="llama-3.3-70b-versatile",
                    vision_model=None  # Groq пока без vision в проекте
                ),
                megallm=ProviderConfig(
                    text_model="gpt-5",
                    vision_model=None
                )
            )
            self._save_config(default_config)
    
    def _load_config(self) -> LLMConfig:
        """Загружает конфигурацию из файла"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return LLMConfig(**data)
            return LLMConfig()
        except Exception as e:
            logger.error(f"Error loading LLM config: {e}", exc_info=True)
            return LLMConfig()
    
    def _save_config(self, config: LLMConfig):
        """Сохраняет конфигурацию в файл"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config.dict(), f, ensure_ascii=False, indent=2)
            logger.info(f"Saved LLM config to {self.config_file}")
        except Exception as e:
            logger.error(f"Error saving LLM config: {e}", exc_info=True)
            raise
    
    def get_config(self) -> LLMConfig:
        """Возвращает текущую конфигурацию"""
        return self._load_config()
    
    def set_provider(self, provider: str):
        """Устанавливает активного провайдера"""
        if provider not in ["openai", "gemini", "groq", "megallm"]:
            raise ValueError(f"Unknown provider: {provider}")
        
        config = self._load_config()
        config.provider = provider
        self._save_config(config)
        logger.info(f"Set LLM provider to: {provider}")
    
    def set_provider_key(self, provider: str, api_key: str):
        """Устанавливает API ключ для провайдера. Обнуляет модели при смене ключа."""
        if provider not in ["openai", "gemini", "groq", "megallm"]:
            raise ValueError(f"Unknown provider: {provider}")
        
        config = self._load_config()
        
        # Проверяем, изменился ли ключ
        old_key = None
        if provider == "openai":
            old_key = config.openai.api_key
        elif provider == "gemini":
            old_key = config.gemini.api_key
        elif provider == "groq":
            old_key = config.groq.api_key
        else:
            old_key = config.megallm.api_key
        
        # Устанавливаем новый ключ
        if provider == "openai":
            config.openai.api_key = api_key
            # Если ключ изменился, обнуляем модели (как указано в задаче)
            if old_key != api_key:
                config.openai.text_model = None
                config.openai.vision_model = None
                logger.info(f"API key changed for {provider}, resetting models")
        elif provider == "gemini":
            config.gemini.api_key = api_key
            if old_key != api_key:
                config.gemini.text_model = None
                config.gemini.vision_model = None
                logger.info(f"API key changed for {provider}, resetting models")
        elif provider == "groq":
            config.groq.api_key = api_key
            if old_key != api_key:
                config.groq.text_model = None
                config.groq.vision_model = None
                logger.info(f"API key changed for {provider}, resetting models")
        else:
            config.megallm.api_key = api_key
            if old_key != api_key:
                config.megallm.text_model = None
                config.megallm.vision_model = None
                logger.info(f"API key changed for {provider}, resetting models")
        
        self._save_config(config)
        logger.info(f"Set API key for provider: {provider}")
    
    def set_models(self, provider: str, text_model: Optional[str] = None, vision_model: Optional[str] = None):
        """Устанавливает модели для провайдера"""
        if provider not in ["openai", "gemini", "groq", "megallm"]:
            raise ValueError(f"Unknown provider: {provider}")
        
        config = self._load_config()
        if provider == "openai":
            if text_model:
                config.openai.text_model = text_model
            if vision_model:
                config.openai.vision_model = vision_model
        elif provider == "gemini":
            if text_model:
                config.gemini.text_model = text_model
            if vision_model:
                config.gemini.vision_model = vision_model
        elif provider == "groq":
            if text_model:
                config.groq.text_model = text_model
            if vision_model:
                config.groq.vision_model = vision_model
        else:
            if text_model:
                config.megallm.text_model = text_model
            if vision_model:
                config.megallm.vision_model = vision_model
        
        self._save_config(config)
        logger.info(f"Set models for provider {provider}: text={text_model}, vision={vision_model}")
    
    def get_provider_config(self, provider: Optional[str] = None) -> ProviderConfig:
        """Возвращает конфигурацию для указанного провайдера или активного"""
        config = self._load_config()
        target_provider = provider or config.provider
        
        if target_provider == "openai":
            return config.openai
        elif target_provider == "gemini":
            return config.gemini
        elif target_provider == "groq":
            return config.groq
        else:
            return config.megallm
    
    def get_active_api_key(self) -> Optional[str]:
        """Возвращает API ключ активного провайдера"""
        config = self._load_config()
        provider_config = self.get_provider_config()
        return provider_config.api_key


# Создаем глобальный экземпляр сервиса
llm_config_service = LLMConfigService()

