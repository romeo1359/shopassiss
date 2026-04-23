import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import bot, data_manager, dp
from config import logger
from handlers.admin import (
    cleanup_files_job,
    nightly_admin_update,
    router as admin_router,
    send_pending_payments_alert,
    send_weekly_debt_report,
)
from handlers.user import router as user_router
from middlewares.access_control import register_middlewares

async def main() -> None:
    logger.info("ربات در حال اجراست...")
    await data_manager.init_db()

    register_middlewares(dp)
    dp.include_router(user_router)
    dp.include_router(admin_router)

    scheduler = AsyncIOScheduler(timezone='Asia/Dubai')
    scheduler.add_job(send_weekly_debt_report, 'cron', day_of_week='sat', hour=12)
    pending_alert_minutes = int(await data_manager.get_setting('pending_payment_alert_minutes') or '15')
    scheduler.add_job(send_pending_payments_alert, 'interval', minutes=max(1, pending_alert_minutes))
    scheduler.add_job(nightly_admin_update, 'cron', hour=23, minute=0)
    scheduler.add_job(cleanup_files_job, 'cron', hour=2, minute=30)
    scheduler.start()

    try:
        while True:
            try:
                await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
            except Exception as e:
                logger.error(f"خطا در polling: {e}")
                logger.info("تلاش مجدد در 10 ثانیه...")
                await asyncio.sleep(10)
    finally:
        scheduler.shutdown(wait=False)
        await data_manager.close()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("ربات با موفقیت متوقف شد.")
    except Exception as e:
        logger.critical(f"خطای غیرمنتظره: {e}", exc_info=True)
