from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup

from app import bot, data_manager
from config import ADMIN_ID, logger
from states.admin_states import AdminStates
from keyboards.inline import ikb_btn
from utils.formatters import escape_markdown
router = Router()

# 12. هندلر درخواست نمایندگی
# =================================================================
@router.callback_query(F.data == "request_representative")
async def request_representative(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    user_id = callback.from_user.id
    user_info = await data_manager.get_user(user_id)
    required_amount = int(await data_manager.get_setting('representative_required_balance') or '0')
    if required_amount == 0:
        await callback.message.edit_text(
            "⚠️ امکان ثبت درخواست نمایندگی در حال حاضر وجود ندارد. لطفاً با پشتیبانی تماس بگیرید."
        )
        return
    if user_info.get('balance', 0) < required_amount:
        shortage = int(required_amount) - int(user_info.get('balance', 0) or 0)
        await callback.message.edit_text(
            f"❌ برای درخواست نمایندگی، باید حداقل {required_amount:,} تومان در کیف پول خود داشته باشید.\n"
            f"موجودی فعلی شما: {int(user_info.get('balance', 0) or 0):,} تومان\n"
            f"میزان کسری: {shortage:,} تومان\n"
            f"لطفاً ابتدا کیف پول خود را شارژ کنید و سپس مجدداً اقدام نمایید."
        )
        return
    full_name = user_info.get('full_name', 'ناشناس')
    admin_msg = (
        f"🧑‍💻 **درخواست نمایندگی جدید**\n"
        f"**کاربر:** {escape_markdown(full_name)} (ID: `{user_id}`)\n"
        f"**شماره تماس:** `{escape_markdown(user_info.get('phone_number', 'ثبت نشده'))}`"
    )
    approve_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                ikb_btn(text="✅ تأیید", callback_data=f"approve_rep_{user_id}"),
                ikb_btn(text="❌ رد", callback_data=f"reject_rep_{user_id}")
            ]
        ]
    )
    try:
        await bot.send_message(ADMIN_ID, admin_msg, reply_markup=approve_buttons, parse_mode="Markdown")
        await callback.message.edit_text("✅ درخواست نمایندگی شما برای بررسی به ادمین ارسال شد.")
    except Exception as e:
        logger.error(f"Failed to send representative request to admin: {e}")
        await callback.message.edit_text("❌ خطایی در ارسال درخواست به ادمین رخ داد. لطفاً با پشتیبانی تماس بگیرید.")
    await callback.answer()

@router.callback_query(F.data.startswith("approve_rep_"))
async def approve_rep_request(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(callback.from_user.id):
        await callback.answer("⛔ دسترسی غیرمجاز.", show_alert=True)
        return
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text("لطفاً درصد تخفیف را وارد کنید:")
    await state.set_state(AdminStates.waiting_for_rep_discount)
    await callback.answer()

@router.callback_query(F.data.startswith("reject_rep_"))
async def reject_rep_request(callback: types.CallbackQuery, **kwargs):
    if not await data_manager.is_admin(callback.from_user.id):
        await callback.answer("⛔ دسترسی غیرمجاز.", show_alert=True)
        return
    user_id = int(callback.data.split('_')[-1])
    await bot.send_message(user_id, "❌ درخواست نمایندگی شما رد شد.")
    await callback.message.edit_text("درخواست رد شد.")
    await callback.answer()

# =================================================================
