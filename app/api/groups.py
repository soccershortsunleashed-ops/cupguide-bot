from fastapi import APIRouter, HTTPException
from typing import List
from app.models.group import Group
from app.services.group_service import group_service

router = APIRouter()

@router.get("/", response_model=List[Group])
async def get_groups():
    return await group_service.get_groups()

@router.post("/", response_model=Group)
async def create_group(group: Group):
    return await group_service.add_group(group)

@router.delete("/{name}")
async def delete_group(name: str):
    await group_service.delete_group(name)
    return {"status": "success"}
