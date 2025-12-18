from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.green_api_service import green_api_service

router = APIRouter()

class SendMessageRequest(BaseModel):
    chat_id: str
    message: str

class SendGroupMessageRequest(BaseModel):
    group_name: str
    message: str

@router.post("/send/contact")
async def send_message_to_contact(request: SendMessageRequest):
    try:
        result = await green_api_service.send_message(request.chat_id, request.message)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send/group")
async def send_message_to_group(request: SendGroupMessageRequest):
    try:
        result = await green_api_service.send_to_group(request.group_name, request.message)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/my-groups")
async def get_my_groups():
    """Получить список всех доступных групп WhatsApp с их ID"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Получаем все чаты
        chats = await green_api_service.get_chats()
        logger.info(f"Получено чатов из get_chats(): {len(chats)}")
        
        if not chats:
            logger.warning("get_chats() вернул пустой список")
            # Попробуем альтернативный способ - через getContacts
            try:
                contacts = await green_api_service.get_contacts()
                logger.info(f"Получено контактов из get_contacts(): {len(contacts)}")
                # Фильтруем группы из контактов
                groups_from_contacts = [c for c in contacts if isinstance(c, dict) and c.get("id", "").endswith("@g.us")]
                if groups_from_contacts:
                    logger.info(f"Найдено групп в контактах: {len(groups_from_contacts)}")
                    chats = groups_from_contacts
            except Exception as e:
                logger.error(f"Ошибка при получении контактов: {e}")
        
        # Логируем структуру всех чатов для отладки
        if chats and len(chats) > 0:
            logger.info(f"Всего получено чатов: {len(chats)}")
            for idx, chat in enumerate(chats[:5]):  # Логируем первые 5
                logger.info(f"Чат #{idx + 1}: {chat}")
                if isinstance(chat, dict):
                    logger.info(f"  Ключи: {list(chat.keys())}")
                    logger.info(f"  id: {chat.get('id')}")
                    logger.info(f"  chatId: {chat.get('chatId')}")
                    logger.info(f"  type: {chat.get('type')}")
                    logger.info(f"  name: {chat.get('name')}")
        
        # Фильтруем только группы (заканчиваются на @g.us)
        groups = []
        for chat in chats:
            if not isinstance(chat, dict):
                logger.debug(f"Пропущен чат (не dict): {type(chat)}")
                continue
            
            # Пробуем разные варианты получения ID
            chat_id = (chat.get("id") or 
                      chat.get("chatId") or 
                      chat.get("chat_id") or 
                      "")
            
            logger.debug(f"Проверка чата: id={chat_id}, type={chat.get('type')}, keys={list(chat.keys())}")
            
            # Проверяем по ID
            if isinstance(chat_id, str) and chat_id.endswith("@g.us"):
                logger.info(f"Найдена группа по ID: {chat_id}")
                groups.append(chat)
            # Также проверяем по типу, если ID не содержит @g.us
            elif chat.get("type") == "group":
                # Если тип group, но ID не заканчивается на @g.us, попробуем получить ID из других полей
                logger.warning(f"Чат с type='group', но ID не заканчивается на @g.us: {chat_id}")
                # Все равно добавляем, если есть хоть какой-то ID
                if chat_id:
                    groups.append(chat)
        
        logger.info(f"Отфильтровано групп: {len(groups)}")
        
        # Для каждой группы получаем дополнительную информацию
        groups_info = []
        for group in groups:
            group_id = group.get("id") or group.get("chatId") or ""
            group_name = (group.get("name") or 
                         group.get("contactName") or 
                         group.get("title") or 
                         group.get("subject") or 
                         "Без названия")
            group_type = group.get("type", "group")
            
            # Получаем количество участников
            participants_count = 0
            try:
                group_data = await green_api_service.get_group_data(group_id)
                if group_data and isinstance(group_data, dict):
                    participants = group_data.get("participants", [])
                    participants_count = len(participants) if participants else 0
            except Exception as e:
                logger.debug(f"Не удалось получить данные группы {group_id}: {e}")
            
            groups_info.append({
                "id": group_id,
                "name": group_name,
                "type": group_type,
                "participants_count": participants_count
            })
        
        logger.info(f"Итого групп для возврата: {len(groups_info)}")
        
        # Если групп не найдено через get_chats, попробуем через getContacts
        if len(groups_info) == 0:
            logger.info("Группы не найдены через get_chats(), пробуем getContacts()...")
            try:
                contacts = await green_api_service.get_contacts()
                logger.info(f"Получено контактов: {len(contacts)}")
                
                # Ищем группы в контактах
                for contact in contacts:
                    if not isinstance(contact, dict):
                        continue
                    
                    contact_id = (contact.get("id") or 
                                contact.get("chatId") or 
                                contact.get("chat_id") or 
                                "")
                    
                    # Проверяем, является ли это группой
                    if isinstance(contact_id, str) and contact_id.endswith("@g.us"):
                        contact_name = (contact.get("name") or 
                                       contact.get("contactName") or 
                                       contact.get("title") or 
                                       "Без названия")
                        contact_type = contact.get("type", "group")
                        
                        # Получаем количество участников
                        participants_count = 0
                        try:
                            group_data = await green_api_service.get_group_data(contact_id)
                            if group_data and isinstance(group_data, dict):
                                participants = group_data.get("participants", [])
                                participants_count = len(participants) if participants else 0
                        except Exception as e:
                            logger.debug(f"Не удалось получить данные группы {contact_id}: {e}")
                        
                        groups_info.append({
                            "id": contact_id,
                            "name": contact_name,
                            "type": contact_type,
                            "participants_count": participants_count
                        })
                        logger.info(f"Найдена группа в контактах: {contact_name} ({contact_id})")
            except Exception as e:
                logger.error(f"Ошибка при получении групп через getContacts: {e}")
        
        # Подготавливаем debug информацию с примерами чатов
        debug_info = {
            "chats_received": len(chats),
            "groups_filtered": len(groups),
            "contacts_checked": len(contacts) if 'contacts' in locals() else 0,
            "sample_chats": []
        }
        
        # Добавляем примеры первых чатов для отладки (без чувствительных данных)
        for chat in chats[:3]:
            if isinstance(chat, dict):
                sample = {
                    "keys": list(chat.keys()),
                    "id": str(chat.get("id", ""))[:50],  # Ограничиваем длину
                    "chatId": str(chat.get("chatId", ""))[:50],
                    "type": str(chat.get("type", "")),
                    "name": str(chat.get("name", ""))[:50]
                }
                debug_info["sample_chats"].append(sample)
        
        return {
            "status": "success",
            "total": len(groups_info),
            "groups": groups_info,
            "debug": debug_info
        }
    except Exception as e:
        logger.error(f"Ошибка при получении групп: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))