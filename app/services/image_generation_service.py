"""
Сервис для генерации изображений через DALL-E
"""
import logging
import os
import aiohttp
import aiofiles
from typing import List, Optional, Dict
from app.core.config import settings
from datetime import datetime

logger = logging.getLogger(__name__)

class ImageGenerationService:
    """Сервис для генерации изображений через OpenAI DALL-E"""
    
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.configured = bool(self.api_key)
    
    async def generate_tournament_poster(
        self,
        tournament_title: str,
        city: str = "Сочи",
        birth_years: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        custom_prompt: Optional[str] = None
    ) -> Dict:
        """
        Генерирует постер для турнира через DALL-E
        
        Returns:
            Словарь с 'image_url' и 'image_path' (если изображение сохранено локально)
        """
        if not self.configured:
            logger.warning("OpenAI API key not configured, cannot generate image")
            return {"error": "OpenAI API key not configured"}
        
        try:
            # Используем кастомный промпт, если предоставлен, иначе создаем стандартный
            if custom_prompt:
                prompt = custom_prompt
            else:
                # Подготавливаем переменные для промпта
                sport_type = "football"  # По умолчанию футбол, можно расширить
                if tournament_title and any(word in tournament_title.lower() for word in ['футбол', 'football']):
                    sport_type = "football"
                elif tournament_title and any(word in tournament_title.lower() for word in ['баскетбол', 'basketball']):
                    sport_type = "basketball"
                elif tournament_title and any(word in tournament_title.lower() for word in ['хоккей', 'hockey']):
                    sport_type = "hockey"
                
                tournament_name = tournament_title or "Tournament"
                city_name = city or "City"
                
                # Форматируем годы рождения
                if birth_years and len(birth_years) > 0:
                    if len(birth_years) == 1:
                        birth_year_group = birth_years[0]
                    elif len(birth_years) == 2:
                        birth_year_group = f"{birth_years[0]}–{birth_years[1]}"
                    else:
                        # Если много годов, показываем диапазон
                        sorted_years = sorted([int(y) for y in birth_years if y.isdigit()])
                        if sorted_years:
                            birth_year_group = f"{sorted_years[0]}–{sorted_years[-1]}"
                        else:
                            birth_year_group = ", ".join(birth_years[:3])
                else:
                    birth_year_group = "2015–2018"
                
                # Форматируем даты
                if start_date and end_date:
                    dates_text = f"{start_date} – {end_date}"
                elif start_date:
                    dates_text = start_date
                elif end_date:
                    dates_text = end_date
                else:
                    dates_text = "TBA"
                
                # Создаем промпт с переменными
                # ВАЖНО: Промпт на английском для DALL-E, но текст на постере должен быть на русском языке
                prompt = f"""Create a realistic, cinematic movie-poster-style illustration for a youth {sport_type} tournament.

Atmosphere similar to modern sports drama films: dramatic lighting, dynamic composition, deep shadows, highly detailed young athletes and emotional expressions.

Include visual references to (IMPORTANT: All text on the poster must be in Russian language):

• Tournament name: {tournament_name} (display in Russian)

• City: {city_name} (display in Russian, format as "г. {city_name}" if city name is in Cyrillic)

• Birth year group: {birth_year_group} (display in Russian format, e.g., "Год рождения: {birth_year_group}")

• Tournament dates: {dates_text} (display in Russian format, e.g., "Даты проведения: {dates_text}")

Show young players in action (passing, shooting, competing), realistic textures of uniforms, wet grass, and stadium lights.

Add volumetric lighting, rim light, and a sense of scale and anticipation.

Style: cinematic realism, inspired by high-end sports movie posters; rich dramatic colors; film-like depth of field.

Format: vertical high-resolution poster 4:5 or 3:4 ratio.

CRITICAL: All text elements on the poster (tournament name, city, dates, birth years) must be written in Russian language using Cyrillic script. The poster design should be atmospheric and minimal, but any text that appears must be in Russian."""
            
            logger.info(f"Generating tournament poster with DALL-E...")
            logger.debug(f"Prompt: {prompt[:200]}...")
            
            # Вызываем DALL-E API
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "size": "1024x1344",  # Вертикальный формат 3:4 (1024x1344) или можно использовать 1024x1280 для 4:5
                    "quality": "hd",
                    "n": 1
                }
                
                async with session.post(
                    "https://api.openai.com/v1/images/generations",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"DALL-E API error: {response.status} - {error_text}")
                        return {"error": f"DALL-E API error: {error_text}"}
                    
                    result = await response.json()
                    
                    if 'data' in result and len(result['data']) > 0:
                        image_url = result['data'][0].get('url')
                        revised_prompt = result['data'][0].get('revised_prompt')
                        
                        if revised_prompt:
                            logger.info(f"Revised prompt: {revised_prompt[:200]}...")
                        
                        # Сохраняем изображение локально
                        image_path = await self._download_and_save_image(image_url, tournament_title)
                        
                        logger.info(f"✅ Poster generated successfully: {image_url}")
                        
                        return {
                            "image_url": image_url,
                            "image_path": image_path,
                            "revised_prompt": revised_prompt
                        }
                    else:
                        logger.error(f"No image data in DALL-E response: {result}")
                        return {"error": "No image data in response"}
                        
        except Exception as e:
            logger.error(f"Error generating tournament poster: {e}", exc_info=True)
            return {"error": str(e)}
    
    async def _download_and_save_image(self, image_url: str, tournament_title: str) -> Optional[str]:
        """Скачивает изображение и сохраняет его локально"""
        try:
            # Создаем директорию для постеров
            posters_dir = os.path.join(settings.BASE_DIR, 'app', 'static', 'posters')
            os.makedirs(posters_dir, exist_ok=True)
            
            # Генерируем имя файла
            safe_title = "".join(c for c in tournament_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_title = safe_title.replace(' ', '_')[:50]  # Ограничиваем длину
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{safe_title}_{timestamp}.png"
            file_path = os.path.join(posters_dir, filename)
            
            # Скачиваем изображение
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        
                        # Сохраняем файл
                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(image_data)
                        
                        # Возвращаем относительный путь для веб-доступа
                        relative_path = f"/static/posters/{filename}"
                        logger.info(f"✅ Image saved to: {relative_path}")
                        return relative_path
                    else:
                        logger.error(f"Failed to download image: HTTP {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error downloading and saving image: {e}", exc_info=True)
            return None

image_generation_service = ImageGenerationService()

