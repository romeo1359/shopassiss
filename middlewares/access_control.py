from aiogram import BaseMiddleware, types

from app import data_manager
from config import ADMIN_ID
from keyboards.reply import build_contact_share_keyboard
from states.user_states import UserStates
from utils.helpers import has_verified_phone, safe_callback_answer

class AccessControlMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        from_user = getattr(event, 'from_user', None)
        if not from_user:
            return await handler(event, data)

        if from_user.id == ADMIN_ID:
            return await handler(event, data)

        state = data.get('state')
        current_state = await state.get_state() if state else None
        allowed_states = {
            UserStates.registration_full_name.state,
            UserStates.registration_phone.state,
            UserStates.waiting_for_referral_code.state,
            UserStates.waiting_for_channel_join.state,
        }

        if isinstance(event, types.Message) and (event.text or '').startswith('/start'):
            return await handler(event, data)

        user_info = await data_manager.get_user(from_user.id)

        if user_info and user_info.get('banned'):
            if isinstance(event, types.CallbackQuery):
                await safe_callback_answer(event, "شما از استفاده از ربات محروم شده‌اید.", show_alert=True)
            else:
                await event.answer("شما از استفاده از ربات محروم شده‌اید. 🚫")
            return

        if current_state in allowed_states:
            return await handler(event, data)

        if not user_info:
            if isinstance(event, types.CallbackQuery):
                await safe_callback_answer(event, "ابتدا /start را بزنید و ثبت‌نام را کامل کنید.", show_alert=True)
            else:
                await event.answer("ابتدا /start را بزنید و ثبت‌نام را کامل کنید.")
            return

        if not has_verified_phone(user_info):
            if state:
                await state.update_data(full_name=user_info.get('full_name', 'ناشناس'))
                await state.set_state(UserStates.registration_phone)
            prompt = "برای استفاده از ربات باید شماره موبایل خودتان را با دکمه اشتراک ثبت کنید."
            if isinstance(event, types.CallbackQuery):
                await safe_callback_answer(event, prompt, show_alert=True)
                try:
                    await event.message.answer(prompt, reply_markup=build_contact_share_keyboard())
                except Exception:
                    pass
            else:
                await event.answer(prompt, reply_markup=build_contact_share_keyboard())
            return

        if not user_info.get('is_approved') and current_state not in allowed_states:
            prompt = "ثبت نام شما هنوز تایید نشده است. تا زمان تایید امکان استفاده از ربات را ندارید."
            if isinstance(event, types.CallbackQuery):
                await safe_callback_answer(event, prompt, show_alert=True)
            else:
                await event.answer(prompt)
            return

        return await handler(event, data)



def register_middlewares(dp):
    middleware = AccessControlMiddleware()
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
