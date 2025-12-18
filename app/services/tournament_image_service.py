"""
Сервис для обработки изображений турниров
"""
import os
import logging
import uuid
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image
from app.core.config import settings

logger = logging.getLogger(__name__)

class TournamentImageService:
    """Сервис для сохранения и обработки изображений турниров"""
    
    def __init__(self):
        self.tournaments_media_dir = os.path.join(settings.BASE_DIR, 'app', 'static', 'media', 'tournaments')
        self._ensure_directory_exists()
    
    def _ensure_directory_exists(self):
        """Создает директорию для хранения изображений турниров"""
        os.makedirs(self.tournaments_media_dir, exist_ok=True)
        logger.info(f"Tournament images directory: {self.tournaments_media_dir}")
    
    def _validate_image(self, file_content: bytes, filename: str) -> Tuple[bool, str]:
        """
        Валидация изображения
        
        Returns:
            (is_valid, error_message)
        """
        # Проверка расширения
        allowed_extensions = {'.jpg', '.jpeg', '.png'}
        file_ext = Path(filename).suffix.lower()
        if file_ext not in allowed_extensions:
            return False, f"Недопустимый формат файла. Разрешены: {', '.join(allowed_extensions)}"
        
        # Проверка размера (до 15 МБ)
        max_size = 15 * 1024 * 1024  # 15 МБ
        logger.info(f"🔍 File size check: {len(file_content)} bytes, max_size: {max_size} bytes")
        if len(file_content) > max_size:
            error_msg = f"Файл слишком большой. Максимальный размер: 15 МБ"
            logger.error(f"❌ File too large: {error_msg}")
            return False, error_msg
        
        # Проверка, что это действительно изображение
        try:
            from io import BytesIO
            img = Image.open(BytesIO(file_content))
            img.verify()  # Проверяем, что файл валидный
        except Exception as e:
            return False, f"Некорректный файл изображения: {str(e)}"
        
        return True, ""
    
    async def save_original(self, file_content: bytes, filename: str) -> str:
        """
        Сохраняет оригинальное изображение
        
        Args:
            file_content: Содержимое файла (bytes)
            filename: Имя исходного файла
            
        Returns:
            URL для доступа к файлу (например, /static/media/tournaments/xxx.jpg)
        """
        # Валидация
        is_valid, error_msg = self._validate_image(file_content, filename)
        if not is_valid:
            raise ValueError(error_msg)
        
        # Генерируем уникальное имя файла
        file_ext = Path(filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(self.tournaments_media_dir, unique_filename)
        
        # Сохраняем файл
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        logger.info(f"✅ Saved original image: {unique_filename}")
        
        # Возвращаем URL
        return f"/static/media/tournaments/{unique_filename}"
    
    def generate_cover_16x9(self, original_url: str) -> Optional[str]:
        """
        Генерирует обложку 16:9 из оригинального изображения
        
        Args:
            original_url: URL оригинального изображения (например, /static/media/tournaments/xxx.jpg)
            
        Returns:
            URL обложки 16:9 или None при ошибке
        """
        try:
            # Преобразуем URL в путь к файлу
            if original_url.startswith('/static/'):
                filename = os.path.basename(original_url)
                original_path = os.path.join(self.tournaments_media_dir, filename)
            else:
                original_path = original_url
            
            if not os.path.exists(original_path):
                logger.error(f"Original image not found: {original_path}")
                return None
            
            # Открываем изображение
            img = Image.open(original_path)
            
            # Целевой размер: 1600x900 (минимум 1200x675)
            target_width = 1600
            target_height = 900
            min_width = 1200
            min_height = 675
            
            # Вычисляем размеры для кропа 16:9
            img_width, img_height = img.size
            aspect_ratio = img_width / img_height
            target_aspect = 16 / 9
            
            if aspect_ratio > target_aspect:
                # Изображение шире - обрезаем по ширине
                new_width = int(img_height * target_aspect)
                left = (img_width - new_width) // 2
                cropped = img.crop((left, 0, left + new_width, img_height))
            else:
                # Изображение выше - обрезаем по высоте
                new_height = int(img_width / target_aspect)
                top = (img_height - new_height) // 2
                cropped = img.crop((0, top, img_width, top + new_height))
            
            # Ресайзим до целевого размера
            resized = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Сохраняем
            original_filename = Path(original_path).stem
            cover_filename = f"{original_filename}_16x9.jpg"
            cover_path = os.path.join(self.tournaments_media_dir, cover_filename)
            
            # Конвертируем в RGB если нужно (для JPEG)
            if resized.mode != 'RGB':
                resized = resized.convert('RGB')
            
            resized.save(cover_path, 'JPEG', quality=90)
            
            logger.info(f"✅ Generated 16:9 cover: {cover_filename}")
            
            return f"/static/media/tournaments/{cover_filename}"
            
        except Exception as e:
            logger.error(f"Error generating 16:9 cover: {e}", exc_info=True)
            return None
    
    def generate_cover_square(self, original_url: str) -> Optional[str]:
        """
        Генерирует квадратную обложку 1:1 из оригинального изображения
        
        Args:
            original_url: URL оригинального изображения
            
        Returns:
            URL квадратной обложки или None при ошибке
        """
        try:
            # Преобразуем URL в путь к файлу
            if original_url.startswith('/static/'):
                filename = os.path.basename(original_url)
                original_path = os.path.join(self.tournaments_media_dir, filename)
            else:
                original_path = original_url
            
            if not os.path.exists(original_path):
                logger.error(f"Original image not found: {original_path}")
                return None
            
            # Открываем изображение
            img = Image.open(original_path)
            
            # Целевой размер: 1080x1080
            target_size = 1080
            
            # Вычисляем размеры для квадратного кропа
            img_width, img_height = img.size
            size = min(img_width, img_height)
            
            # Центрируем кроп
            left = (img_width - size) // 2
            top = (img_height - size) // 2
            cropped = img.crop((left, top, left + size, top + size))
            
            # Ресайзим до целевого размера
            resized = cropped.resize((target_size, target_size), Image.Resampling.LANCZOS)
            
            # Сохраняем
            original_filename = Path(original_path).stem
            cover_filename = f"{original_filename}_square.jpg"
            cover_path = os.path.join(self.tournaments_media_dir, cover_filename)
            
            # Конвертируем в RGB если нужно (для JPEG)
            if resized.mode != 'RGB':
                resized = resized.convert('RGB')
            
            resized.save(cover_path, 'JPEG', quality=90)
            
            logger.info(f"✅ Generated square cover: {cover_filename}")
            
            return f"/static/media/tournaments/{cover_filename}"
            
        except Exception as e:
            logger.error(f"Error generating square cover: {e}", exc_info=True)
            return None

# Создаем глобальный экземпляр сервиса
tournament_image_service = TournamentImageService()


