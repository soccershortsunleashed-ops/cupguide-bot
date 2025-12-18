from fastapi import APIRouter
from typing import Dict, List
from datetime import datetime, timedelta
from app.services.contact_service import contact_service
from app.services.channel_service import channel_service
# Temporarily disabled due to dependency issues
# from app.services.whatsapp_service import whatsapp_service

router = APIRouter()


@router.get("/stats")
async def get_dashboard_stats():
    """Get dashboard statistics"""
    try:
        # Get total contacts count
        contacts = await contact_service.get_contacts()
        total_contacts = len(contacts)
        
        # Get messages count for today
        today = datetime.now().date()
        from app.services.message_service import message_service
        all_messages = await message_service.get_messages()
        messages_today = sum(1 for msg in all_messages if msg.date.date() == today)
        
        # Get channels count
        channels = await channel_service.get_channels()
        active_channels = len(channels)
        
        # Get WhatsApp groups count (temporarily disabled)
        # monitored_chats = whatsapp_service.get_monitored_chats()
        # whatsapp_groups = len([chat for chat in monitored_chats if '@g.us' in chat])
        whatsapp_groups = 0  # Temporary placeholder
        
        return {
            "total_contacts": total_contacts,
            "messages_today": messages_today,
            "active_channels": active_channels,
            "whatsapp_groups": whatsapp_groups,
            "contacts_change": "+0%",  # TODO: Calculate from previous period
            "messages_change": "+0%",  # TODO: Calculate from previous period
            "channels_change": "+0",   # TODO: Calculate from previous period
            "groups_change": "+0"      # TODO: Calculate from previous period
        }
    except Exception as e:
        return {
            "total_contacts": 0,
            "messages_today": 0,
            "active_channels": 0,
            "whatsapp_groups": 0,
            "contacts_change": "+0%",
            "messages_change": "+0%",
            "channels_change": "+0",
            "groups_change": "+0"
        }


@router.get("/engagement")
async def get_engagement_metrics(days: int = 30):
    """Get engagement metrics for the last N days"""
    try:
        from app.services.message_service import message_service
        all_messages = await message_service.get_messages()
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Filter messages by date
        filtered_messages = [msg for msg in all_messages if msg.date >= cutoff_date]
        
        # Group by date
        daily_counts = {}
        for msg in filtered_messages:
            date_key = msg.date.date().isoformat()
            daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
        
        # Create data points for chart
        dates = sorted(daily_counts.keys())
        values = [daily_counts[date] for date in dates]
        
        return {
            "labels": dates,
            "values": values
        }
    except Exception as e:
        return {
            "labels": [],
            "values": []
        }


@router.get("/alerts")
async def get_dashboard_alerts():
    """Get real-time alerts for dashboard"""
    alerts = []
    
    # Check for recent errors or issues
    # TODO: Implement actual alert logic based on system status
    
    return alerts

