import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: AsyncIOScheduler = None


async def sync_all_contacts_job():
    """Background job to sync messages for all contacts"""
    try:
        from app.services.message_sync_service import message_sync_service
        
        logger.info("Starting scheduled message sync for all contacts")
        result = await message_sync_service.sync_all_contacts()
        logger.info(f"Scheduled sync completed: {result}")
        
    except Exception as e:
        logger.error(f"Error in scheduled sync job: {e}")


async def expire_premium_subscriptions_job():
    """Background job to automatically disable expired premium subscriptions"""
    try:
        from app.services.premium_service import premium_service
        
        logger.info("🔝 Checking for expired premium subscriptions...")
        
        # Используем новый premium_service для проверки и отключения
        deactivated = await premium_service.check_and_deactivate_expired()
        
        if deactivated:
            logger.info(f"🔝 Expired {len(deactivated)} premium subscriptions: {deactivated}")
        else:
            logger.debug("🔝 No expired premium subscriptions found")
            
    except Exception as e:
        logger.error(f"Error in premium expiration job: {e}")


def setup_scheduler():
    """Setup and configure the scheduler"""
    global scheduler
    
    if scheduler is not None:
        return scheduler
    
    scheduler = AsyncIOScheduler()
    
    # DISABLED: Automatic sync temporarily disabled during setup
    # Add job: sync every 2 hours
    # scheduler.add_job(
    #     sync_all_contacts_job,
    #     trigger=IntervalTrigger(hours=2),
    #     id='sync_whatsapp_messages',
    #     name='Sync WhatsApp messages for all contacts',
    #     replace_existing=True,
    #     next_run_time=datetime.now()  # Run immediately on startup
    # )
    
    # Проверка истёкших премиум-подписок каждый час
    scheduler.add_job(
        expire_premium_subscriptions_job,
        trigger=IntervalTrigger(hours=1),
        id='expire_premium_subscriptions',
        name='Expire premium subscriptions',
        replace_existing=True,
        next_run_time=datetime.now()  # Запустить сразу при старте
    )
    
    logger.info("Scheduler configured (premium expiration enabled)")
    return scheduler


async def start_scheduler():
    """Start the scheduler"""
    global scheduler
    
    if scheduler is None:
        setup_scheduler()
    
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started successfully")
    else:
        logger.info("Scheduler is already running")


async def stop_scheduler():
    """Stop the scheduler"""
    global scheduler
    
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
