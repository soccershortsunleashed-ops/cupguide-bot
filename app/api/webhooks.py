from fastapi import APIRouter, Request, HTTPException
from app.services.tournament_service import tournament_service
import logging

router = APIRouter(tags=["webhooks"])
logger = logging.getLogger(__name__)

@router.post("/webhooks/green-api")
async def receive_green_api_webhook(request: Request):
    """
    Endpoint to receive webhooks from Green API.
    """
    try:
        event = await request.json()
        
        # Process asynchronously to avoid blocking the webhook response
        # In a production env, this should go to a queue (Celery/Redis)
        # For now, we await it but ensure it handles errors gracefully
        await tournament_service.process_webhook_event(event)
        
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        # Always return 200 to Green API to prevent retries of bad payloads
        return {"status": "error", "detail": str(e)}
