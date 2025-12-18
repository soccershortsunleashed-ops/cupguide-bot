from fastapi import APIRouter, HTTPException, Body
from typing import List
from app.models.channel import Channel, ChannelType
from app.services.channel_service import channel_service
from pydantic import BaseModel

router = APIRouter()

class AddChannelRequest(BaseModel):
    identifier: str
    type: ChannelType

@router.get("/", response_model=List[Channel])
async def list_channels():
    return await channel_service.get_channels()

@router.post("/", response_model=Channel)
async def add_channel(request: AddChannelRequest):
    try:
        channel = await channel_service.add_channel(request.identifier, request.type)
        
        # Trigger monitoring update
        from app.services.monitoring_service import monitoring_service
        await monitoring_service.force_check()
        
        return channel
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{channel_id}")
async def delete_channel(channel_id: str):
    await channel_service.delete_channel(channel_id)
    return {"status": "deleted"}
