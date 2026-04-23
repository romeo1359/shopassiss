from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup

from app import bot, data_manager
from config import ADMIN_ID
from states.user_states import UserStates
from keyboards.inline import build_support_category_markup, build_support_priority_markup, cancel_only_button, ikb_btn
from keyboards.reply import user_main_menu
from utils.formatters import escape_markdown
from utils.settings_helpers import get_support_category_label, get_support_priority_label
from utils.telegram_utils import rate_limit, safe_callback_answer
router = Router()

# 15. هندلرهای پشتیبانی
# =================================================================
@router.message(F.text.in_(["📞 پشتیبانی", "🛟 پشتیبانی"]))
async def start_support_for_user(message: types.Message, state: FSMContext, **kwargs):
    await message.answer("ابتدا دسته‌بندی تیکت را انتخاب کنید:", reply_markup=build_support_category_markup())
    await state.set_state(UserStates.waiting_for_support_category)

@router.callback_query(F.data.startswith("support_category_"))
async def support_category_selected(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    category = (callback.data or '').split('support_category_', 1)[1].lower()
    if category not in SUPPORT_CATEGORY_LABELS:
        await callback.answer('دسته‌بندی نامعتبر است.', show_alert=True)
        return
    await state.update_data(support_category=category)
    await callback.message.edit_text(f"دسته‌بندی انتخاب شد: {SUPPORT_CATEGORY_LABELS[category]}\nحالا اولویت تیکت را انتخاب کنید:", reply_markup=build_support_priority_markup())
    await state.set_state(UserStates.waiting_for_support_priority)

@router.callback_query(F.data.startswith("support_priority_"))
async def support_priority_selected(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    priority = (callback.data or '').split('support_priority_', 1)[1].lower()
    if priority not in SUPPORT_PRIORITY_LABELS:
        await callback.answer('اولویت نامعتبر است.', show_alert=True)
        return
    await state.update_data(support_priority=priority)
    await callback.message.edit_text("لطفا سوال یا مشکل خود را به طور کامل ارسال کنید. ✍️", reply_markup=cancel_only_button)
    await state.set_state(UserStates.waiting_for_support_message)

@router.message(UserStates.waiting_for_support_message)
@rate_limit(20)
async def handle_support_message(message: types.Message, state: FSMContext, **kwargs):
    user_id = message.from_user.id
    user_info = await data_manager.get_user(user_id)
    full_name = user_info.get('full_name', 'ناشناس')
    state_data = await state.get_data()
    tracking_code = state_data.get('support_tracking_code')
    payment_id = state_data.get('support_payment_id')
    category = state_data.get('support_category', 'general')
    priority = state_data.get('support_priority', 'normal')
    ticket_id = await data_manager.add_support_ticket(user_id, full_name, message.text, tracking_code, category=category, priority=priority, related_payment_id=payment_id or '')
    admin_message_text = (
        f"**تیکت پشتیبانی جدید:** 🎫\n"
        f"**نام:** {escape_markdown(full_name)}\n"
        f"**شناسه (ID):** `{user_id}`\n"
    )
    admin_message_text += f"**دسته‌بندی:** {get_support_category_label(category)}\n**اولویت:** {get_support_priority_label(priority)}\n"
    if tracking_code:
        admin_message_text += f"**مرتبط با کد رهگیری:** `{tracking_code}`\n"
    if payment_id:
        admin_message_text += f"**مرتبط با شناسه پرداخت:** `{payment_id}`\n"
    admin_message_text += f"**متن پیام:**\n`{escape_markdown(message.text)}`"
    reply_button = InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="➡️ پاسخ به کاربر", callback_data=f"reply_to_user_{user_id}_{ticket_id}")]
        ]
    )
    await bot.send_message(ADMIN_ID, admin_message_text, reply_markup=reply_button, parse_mode="Markdown")
    await message.answer("پیام شما به پشتیبانی ارسال شد. منتظر پاسخ مدیر باشید. ✅")
    await state.clear()
    await bot.send_message(user_id, "به منوی اصلی بازگشتید.", reply_markup=user_main_menu)

@router.message(UserStates.waiting_for_support_with_tracking)
@rate_limit(20)
async def handle_support_with_tracking(message: types.Message, state: FSMContext, **kwargs):
    user_id = message.from_user.id
    user_info = await data_manager.get_user(user_id)
    full_name = user_info.get('full_name', 'ناشناس')
    state_data = await state.get_data()
    tracking_code = state_data.get('support_tracking_code')
    payment_id = state_data.get('support_payment_id')
    category = state_data.get('support_category', 'general')
    priority = state_data.get('support_priority', 'normal')
    ticket_id = await data_manager.add_support_ticket(user_id, full_name, message.text, tracking_code, category=category, priority=priority, related_payment_id=payment_id or '')
    admin_message_text = (
        f"**تیکت پشتیبانی جدید:** 🎫\n"
        f"**نام:** {escape_markdown(full_name)}\n"
        f"**شناسه (ID):** `{user_id}`\n"
    )
    admin_message_text += f"**دسته‌بندی:** {get_support_category_label(category)}\n**اولویت:** {get_support_priority_label(priority)}\n"
    if tracking_code:
        admin_message_text += f"**مرتبط با کد رهگیری:** `{tracking_code}`\n"
    if payment_id:
        admin_message_text += f"**مرتبط با شناسه پرداخت:** `{payment_id}`\n"
    admin_message_text += f"**متن پیام:**\n`{escape_markdown(message.text)}`"
    reply_button = InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="➡️ پاسخ به کاربر", callback_data=f"reply_to_user_{user_id}_{ticket_id}")]
        ]
    )
    await bot.send_message(ADMIN_ID, admin_message_text, reply_markup=reply_button, parse_mode="Markdown")
    await message.answer("پیام شما به پشتیبانی ارسال شد. منتظر پاسخ مدیر باشید. ✅")
    await state.clear()
    await bot.send_message(user_id, "به منوی اصلی بازگشتید.", reply_markup=user_main_menu)

# =================================================================
# 16. هندلرهای مدیریت کاربران (ادمین) با بررسی دسترسی
# =================================================================
