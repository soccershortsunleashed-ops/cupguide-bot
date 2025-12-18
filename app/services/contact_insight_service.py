import json
import os
from typing import List, Optional
from app.models.contact_insight import ContactInsight
from datetime import datetime


class ContactInsightService:
    """Service for managing contact insights"""
    
    def __init__(self, data_file: str = "app/data/contact_insights.json"):
        self.data_file = data_file
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Create data file if it doesn't exist"""
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        if not os.path.exists(self.data_file):
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
    
    async def get_all_insights(self) -> List[ContactInsight]:
        """Get all contact insights"""
        with open(self.data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [ContactInsight(**item) for item in data]
    
    async def get_insights(self, contact_id: int) -> Optional[ContactInsight]:
        """Get insights for a specific contact"""
        insights = await self.get_all_insights()
        for insight in insights:
            if insight.contact_id == contact_id:
                return insight
        return None
    
    async def create_or_update_insights(self, insight: ContactInsight) -> ContactInsight:
        """Create or update contact insights"""
        insights = await self.get_all_insights()
        
        # Update timestamp
        insight.updated_at = datetime.now()
        
        # Find and update existing, or append new
        updated = False
        for i, existing in enumerate(insights):
            if existing.contact_id == insight.contact_id:
                insights[i] = insight
                updated = True
                break
        
        if not updated:
            insights.append(insight)
        
        # Save to file
        await self._save_insights(insights)
        return insight
    
    async def update_insights_field(self, contact_id: int, **fields) -> Optional[ContactInsight]:
        """Update specific fields of contact insights"""
        insight = await self.get_insights(contact_id)
        if not insight:
            return None
        
        # Update fields
        for key, value in fields.items():
            if hasattr(insight, key):
                setattr(insight, key, value)
        
        # Mark as manually edited if summary is changed
        if 'summary' in fields or 'tags' in fields or 'from_dialogs' in fields:
            insight.manually_edited = True
        
        return await self.create_or_update_insights(insight)
    
    async def delete_insights(self, contact_id: int) -> bool:
        """Delete insights for a contact"""
        insights = await self.get_all_insights()
        original_count = len(insights)
        insights = [i for i in insights if i.contact_id != contact_id]
        
        if len(insights) < original_count:
            await self._save_insights(insights)
            return True
        return False
    
    async def _save_insights(self, insights: List[ContactInsight]):
        """Save insights to file"""
        data = [insight.model_dump() for insight in insights]
        
        # Convert datetime to ISO string
        for item in data:
            if isinstance(item['updated_at'], datetime):
                item['updated_at'] = item['updated_at'].isoformat()
        
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# Singleton instance
contact_insight_service = ContactInsightService()
