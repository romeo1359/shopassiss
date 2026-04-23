from aiogram import Router

from .users import router as users_router
from .products import router as products_router
from .settings import router as settings_router
from .support import router as support_router
from .education import router as education_router
from .misc import router as misc_router
from .misc import cleanup_files_job, nightly_admin_update, send_pending_payments_alert, send_weekly_debt_report

router = Router()
router.include_router(users_router)
router.include_router(products_router)
router.include_router(settings_router)
router.include_router(support_router)
router.include_router(education_router)
router.include_router(misc_router)
