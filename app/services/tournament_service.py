"""
Сервис для работы с турнирами
"""
import json
import os
import aiofiles
import logging
from typing import List, Optional
from datetime import datetime
from app.core.config import settings
from app.models.tournament import Tournament
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class TournamentService:
    def __init__(self):
        self.file_path = os.path.join(settings.DATA_DIR, "tournaments.json")
        self.contacts_file_path = os.path.join(settings.DATA_DIR, "contacts.json")
        self._ensure_file_exists()
    
    async def match_organizer_phone_to_contact(self, organizer_phone: str) -> Optional[int]:
        """
        Находит contact_id по телефону организатора.
        
        Args:
            organizer_phone: Телефон организатора
        
        Returns:
            contact_id или None если не найден
        """
        if not organizer_phone:
            return None
        
        # Нормализуем телефон (убираем всё кроме цифр)
        normalized_phone = ''.join(c for c in organizer_phone if c.isdigit())
        if normalized_phone.startswith('8') and len(normalized_phone) == 11:
            normalized_phone = '7' + normalized_phone[1:]
        
        try:
            import aiofiles
            async with aiofiles.open(self.contacts_file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                contacts = json.loads(content) if content else []
                
                for contact in contacts:
                    contact_phone = contact.get('phone', '')
                    # Нормализуем телефон контакта
                    normalized_contact_phone = ''.join(c for c in contact_phone if c.isdigit())
                    if normalized_contact_phone.startswith('8') and len(normalized_contact_phone) == 11:
                        normalized_contact_phone = '7' + normalized_contact_phone[1:]
                    
                    if normalized_phone == normalized_contact_phone:
                        return contact.get('id')
                
        except Exception as e:
            logger.warning(f"Error matching organizer phone: {e}")
        
        return None

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump([], f)

    async def get_tournaments(self) -> List[Tournament]:
        """Получить все турниры"""
        try:
            async with aiofiles.open(self.file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                if not content or not content.strip():
                    logger.info(f"No tournaments found in {self.file_path}, returning empty list")
                    return []
                try:
                    data = json.loads(content)
                    if not isinstance(data, list):
                        logger.error(f"Tournaments file does not contain a list, got {type(data)}")
                        return []
                    
                    tournaments = []
                    for idx, item in enumerate(data):
                        try:
                            # Преобразуем строки дат в datetime объекты, если нужно
                            if 'created_at' in item and isinstance(item['created_at'], str):
                                try:
                                    item['created_at'] = datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
                                except:
                                    item['created_at'] = datetime.utcnow()
                            elif 'created_at' not in item:
                                item['created_at'] = datetime.utcnow()
                            
                            if 'updated_at' in item and isinstance(item['updated_at'], str):
                                try:
                                    item['updated_at'] = datetime.fromisoformat(item['updated_at'].replace('Z', '+00:00'))
                                except:
                                    item['updated_at'] = None
                            
                            # Убеждаемся, что title есть (обязательное поле)
                            if 'title' not in item or not item['title']:
                                item['title'] = 'Турнир без названия'
                            
                            tournaments.append(Tournament(**item))
                        except Exception as e:
                            logger.error(f"Error parsing tournament item at index {idx}: {e}, item: {item}", exc_info=True)
                            continue
                    
                    logger.info(f"Successfully loaded {len(tournaments)} tournaments from {self.file_path}")
                    return tournaments
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error in tournaments file: {e}, file: {self.file_path}")
                    return []
        except FileNotFoundError:
            logger.warning(f"Tournaments file not found: {self.file_path}, returning empty list")
            return []
        except Exception as e:
            logger.error(f"Error loading tournaments from {self.file_path}: {e}", exc_info=True)
            return []

    async def get_tournament_by_id(self, tournament_id: int) -> Optional[Tournament]:
        """Получить турнир по ID"""
        tournaments = await self.get_tournaments()
        for tournament in tournaments:
            if tournament.id == tournament_id:
                return tournament
        return None

    async def save_tournament(self, tournament: Tournament) -> Tournament:
        """Сохранить турнир"""
        from app.utils.tournament_name_generator import generate_alternative_names
        
        tournaments = await self.get_tournaments()
        
        # Определяем следующий ID
        if tournament.id is None:
            next_id = max([t.id for t in tournaments if t.id is not None], default=0) + 1
            tournament.id = next_id
        
        # Автоматически генерируем альтернативные названия
        if tournament.title:
            tournament.alternative_names = generate_alternative_names(tournament.title)
            logger.info(f"🏷️ Generated {len(tournament.alternative_names)} alternative names for tournament '{tournament.title}'")
        
        # Обновляем дату обновления
        tournament.updated_at = datetime.utcnow()
        
        # Проверяем, существует ли уже турнир с таким ID
        existing_index = None
        for i, t in enumerate(tournaments):
            if t.id == tournament.id:
                existing_index = i
                break
        
        if existing_index is not None:
            tournaments[existing_index] = tournament
        else:
            tournaments.append(tournament)
        
        await self._save_data(tournaments)
        return tournament

    async def save_tournament_with_extracted_data(self, tournament: Tournament, extracted_data: dict = None) -> Tournament:
        """Сохранить турнир с извлеченными данными"""
        # Сохраняем турнир
        saved_tournament = await self.save_tournament(tournament)
        
        # Сохраняем извлеченные данные отдельно, если они есть
        if extracted_data:
            await self._save_extracted_data(saved_tournament.id, extracted_data)
        
        return saved_tournament

    async def get_extracted_data(self, tournament_id: int) -> Optional[dict]:
        """Получить извлеченные данные для турнира"""
        try:
            extracted_file_path = os.path.join(settings.DATA_DIR, f"tournament_{tournament_id}_extracted.json")
            if os.path.exists(extracted_file_path):
                async with aiofiles.open(extracted_file_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
        except Exception as e:
            logger.error(f"Error loading extracted data for tournament {tournament_id}: {e}")
        return None

    async def _save_extracted_data(self, tournament_id: int, extracted_data: dict):
        """Сохранить извлеченные данные для турнира"""
        try:
            extracted_file_path = os.path.join(settings.DATA_DIR, f"tournament_{tournament_id}_extracted.json")
            async with aiofiles.open(extracted_file_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(extracted_data, ensure_ascii=False, indent=2, default=str))
            logger.info(f"✅ Successfully saved extracted data for tournament {tournament_id}")
        except Exception as e:
            logger.error(f"❌ Error saving extracted data for tournament {tournament_id}: {e}", exc_info=True)
            raise e

    async def delete_tournament(self, tournament_id: int):
        """Удалить турнир"""
        tournaments = await self.get_tournaments()
        updated_tournaments = [t for t in tournaments if t.id != tournament_id]
        
        if len(updated_tournaments) == len(tournaments):
            raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")
        
        await self._save_data(updated_tournaments)

    async def update_tournament(self, tournament_id: int, updates: dict) -> Tournament:
        from app.utils.tournament_name_generator import generate_alternative_names
        
        tournaments = await self.get_tournaments()
        for idx, tournament in enumerate(tournaments):
            if tournament.id == tournament_id:
                data = tournament.model_dump()
                for key, value in updates.items():
                    data[key] = value
                data["updated_at"] = datetime.utcnow()
                
                # Если обновляется название - перегенерируем альтернативные названия
                if "title" in updates and updates["title"]:
                    data["alternative_names"] = generate_alternative_names(updates["title"])
                    logger.info(f"🏷️ Regenerated {len(data['alternative_names'])} alternative names for tournament '{updates['title']}'")
                
                updated_tournament = Tournament(**data)
                tournaments[idx] = updated_tournament
                await self._save_data(tournaments)
                return updated_tournament
        raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")

    async def _save_data(self, tournaments: List[Tournament]):
        """Сохранить турниры в JSON файл"""
        data = [t.model_dump() for t in tournaments]
        try:
            async with aiofiles.open(self.file_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))
            logger.info(f"✅ Successfully saved {len(tournaments)} tournaments to {self.file_path}")
        except Exception as e:
            logger.error(f"❌ Error saving tournaments: {e}", exc_info=True)
            raise e

tournament_service = TournamentService()
