from aiogram import Router

from .registration import router as registration_router
from .profile import router as profile_router
from .representative import router as representative_router
from .shop import router as shop_router
from .wallet import router as wallet_router
from .support import router as support_router

router = Router()
router.include_router(registration_router)
router.include_router(profile_router)
router.include_router(representative_router)
router.include_router(shop_router)
router.include_router(wallet_router)
router.include_router(support_router)
