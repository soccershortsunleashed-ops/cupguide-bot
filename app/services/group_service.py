import json
import os
import aiofiles
from typing import List
from app.core.config import settings
from app.models.group import Group
from fastapi import HTTPException

class GroupService:
    def __init__(self):
        self.file_path = os.path.join(settings.DATA_DIR, "groups.json")
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            default_groups = [
                {"name": "Общая"},
                {"name": "Тренеры по футболу"},
                {"name": "Экипировка"}
            ]
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(default_groups, f, ensure_ascii=False, indent=2)

    async def get_groups(self) -> List[Group]:
        async with aiofiles.open(self.file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            if not content:
                return []
            try:
                data = json.loads(content)
                return [Group(**item) for item in data]
            except json.JSONDecodeError:
                return []

    async def add_group(self, group: Group):
        groups = await self.get_groups()
        if any(g.name == group.name for g in groups):
            raise HTTPException(status_code=400, detail="Group already exists")
        
        groups.append(group)
        await self._save_groups(groups)
        return group

    async def delete_group(self, name: str):
        groups = await self.get_groups()
        updated_groups = [g for g in groups if g.name != name]
        
        if len(updated_groups) == len(groups):
            raise HTTPException(status_code=404, detail="Group not found")
            
        await self._save_groups(updated_groups)

    async def _save_groups(self, groups: List[Group]):
        data = [g.model_dump() for g in groups]
        async with aiofiles.open(self.file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

group_service = GroupService()
