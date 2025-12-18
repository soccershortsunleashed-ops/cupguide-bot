"""
Сервис для работы с Teletype API
"""
import aiohttp
import json
import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class TeletypeService:
    """Сервис для публикации турниров в Teletype"""
    
    def __init__(self):
        self.base_url = "https://teletype.in/api"
        self.access_token = os.getenv("TELETYPE_ACCESS_TOKEN")
        self.account_name = os.getenv("TELETYPE_ACCOUNT_NAME", "cupguide")
        
    async def publish_tournament(self, tournament: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Публикует турнир в Teletype"""
        if not self.access_token:
            logger.warning("Teletype access token не настроен")
            return None
            
        try:
            # Подготавливаем контент для Teletype
            content = self._prepare_tournament_content(tournament)
            
            # Создаем пост в Teletype
            post_data = {
                "title": tournament["title"],
                "content": content,
                "author_url": f"https://teletype.in/@{self.account_name}",
                "return_content": False
            }
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/posts",
                    headers=headers,
                    json=post_data
                ) as response:
                    
                    if response.status == 201:
                        result = await response.json()
                        logger.info(f"✅ Турнир '{tournament['title']}' опубликован в Teletype")
                        
                        return {
                            "url": result.get("url"),
                            "post_id": result.get("id"),
                            "published_at": datetime.now().isoformat()
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Ошибка публикации в Teletype: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Ошибка при публикации турнира в Teletype: {e}")
            return None
    
    def _prepare_tournament_content(self, tournament: Dict[str, Any]) -> str:
        """Подготавливает контент турнира для Teletype"""
        
        # Базовая информация
        content_parts = []
        
        # Добавляем изображение если есть
        if tournament.get("image_cover_square_url"):
            image_url = f"http://127.0.0.1:8000{tournament['image_cover_square_url']}"
            content_parts.append(f'<img src="{image_url}" alt="{tournament["title"]}">')
        
        # Краткое описание
        if tournament.get("short_description"):
            content_parts.append(f"<p>{tournament['short_description']}</p>")
        
        # Основная информация
        content_parts.append("<h3>📋 Основная информация</h3>")
        content_parts.append(f"<p><strong>📍 Место:</strong> {tournament['city']}, {tournament.get('region', '')}</p>")
        content_parts.append(f"<p><strong>📅 Даты:</strong> {tournament['start_date']} - {tournament['end_date']}</p>")
        
        if tournament.get("birth_years"):
            years = ", ".join(str(year).strip("[]'\"") for year in tournament["birth_years"])
            content_parts.append(f"<p><strong>⚽ Возраста:</strong> {years} г.р.</p>")
        
        if tournament.get("entry_fee"):
            content_parts.append(f"<p><strong>💰 Взнос:</strong> {tournament['entry_fee']}</p>")
        
        # Контакты
        content_parts.append("<h3>📞 Контакты</h3>")
        if tournament.get("organizer_name"):
            content_parts.append(f"<p><strong>Организатор:</strong> {tournament['organizer_name']}</p>")
        if tournament.get("contact"):
            content_parts.append(f"<p><strong>Телефон:</strong> {tournament['contact']}</p>")
        
        # Ссылка на полную карточку с UTM-метками для отслеживания
        tournament_url = f"http://127.0.0.1:8000/tournaments/{tournament['id']}?utm_source=telegraph&utm_medium=article&utm_campaign=tournament_{tournament['id']}"
        content_parts.append(f'<p><a href="{tournament_url}">🔗 Подробная информация о турнире</a></p>')
        
        # Полное описание если есть
        if tournament.get("body"):
            content_parts.append("<h3>📝 Подробное описание</h3>")
            # Конвертируем markdown в HTML (упрощенно)
            body_html = tournament["body"].replace("\n## ", "\n<h3>").replace("## ", "<h3>")
            body_html = body_html.replace("\n### ", "\n<h4>").replace("### ", "<h4>")
            body_html = body_html.replace("</h3>", "</h3>").replace("</h4>", "</h4>")
            body_html = body_html.replace("\n\n", "</p><p>").replace("\n", "<br>")
            body_html = f"<p>{body_html}</p>"
            content_parts.append(body_html)
        
        return "\n".join(content_parts)
    
    async def update_tournament_teletype_info(self, tournament_id: int, teletype_data: Dict[str, Any]):
        """Обновляет информацию о публикации в Teletype в базе данных"""
        try:
            # Здесь должно быть обновление в базе данных
            # Пока обновим JSON файл
            import json
            
            with open('data/tournaments.json', 'r', encoding='utf-8') as f:
                tournaments = json.load(f)
            
            for tournament in tournaments:
                if tournament['id'] == tournament_id:
                    tournament['publish_to_teletype'] = True
                    tournament['teletype_url'] = teletype_data.get('url')
                    tournament['teletype_post_id'] = teletype_data.get('post_id')
                    tournament['published_at'] = teletype_data.get('published_at')
                    break
            
            with open('data/tournaments.json', 'w', encoding='utf-8') as f:
                json.dump(tournaments, f, ensure_ascii=False, indent=2)
                
            logger.info(f"✅ Обновлена информация о Teletype для турнира {tournament_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления информации о Teletype: {e}")

# Создаем экземпляр сервиса
teletype_service = TeletypeService()