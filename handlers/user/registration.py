import datetime
import re

from aiogram import F, Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup

from app import data_manager
from config import ADMIN_ID, BUTTON_STYLE_DANGER, BUTTON_STYLE_SUCCESS
from states.admin_states import AdminStates
from states.user_states import UserStates
from keyboards.inline import cancel_only_button, ikb_btn, start_button
from keyboards.reply import admin_main_menu, build_contact_share_keyboard, rep_menu, user_main_menu
from utils.formatters import escape_markdown, format_persian_date, normalize_phone
from utils.telegram_utils import admin_only, ask_for_referral_or_admin_approval, build_force_join_markup, is_user_member_of_force_channel, safe_callback_answer, safe_send_message
router = Router()


@router.callback_query(F.data == "cancel")
async def cancel_process(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    await state.clear()
    user_id = callback.from_user.id
    user_info = await data_manager.get_user(user_id)

    if await data_manager.is_admin(user_id):
        await safe_send_message(callback.message.chat.id, "به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)
    elif user_info and user_info.get('is_rep'):
        await safe_send_message(callback.message.chat.id, "به منوی نماینده بازگشتید.", reply_markup=rep_menu)
    elif user_info and user_info.get('full_name') != "ناشناس":
        await safe_send_message(callback.message.chat.id, "به منوی اصلی بازگشتید.", reply_markup=user_main_menu)
    else:
        await safe_send_message(callback.message.chat.id, "برای شروع مجدد، روی دکمه زیر کلیک کنید.", reply_markup=start_button)

@router.callback_query(F.data == "start_bot")
async def start_bot_callback(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    await command_start_handler(callback.message, state)


@router.message(F.text == "🚀 شروع ربات")
async def start_bot_text_handler(message: types.Message, state: FSMContext, **kwargs):
    await command_start_handler(message, state)

# 10. هندلرهای کاربر — ثبت‌نام
# =================================================================
@router.message(CommandStart())
async def command_start_handler(message: types.Message, state: FSMContext, **kwargs):
    user_id = message.from_user.id
    user_info = await data_manager.get_user(user_id)

    if user_info and user_info.get('banned', False):
        await message.answer("شما از استفاده از این ربات محروم شده‌اید. 🚫")
        return

    if await data_manager.is_admin(user_id):
        await message.answer("سلام ادمین عزیز! به پنل مدیریت خوش آمدید. 👋", reply_markup=admin_main_menu)
        return

    bot_status = await data_manager.get_setting('bot_status')
    if bot_status == "off":
        await message.answer("جهت بروزرسانی، ربات در حال حاضر غیرفعال است. 🛠️", reply_markup=start_button)
        return

    if not user_info:
        await data_manager.create_user(user_id, "ناشناس", "ثبت نشده")
        user_info = await data_manager.get_user(user_id)

    if user_info.get('is_approved'):
        welcome_message = (await data_manager.get_setting('welcome_message') or '').strip()
        if welcome_message:
            await message.answer(welcome_message)
        if user_info.get('is_rep'):
            await message.answer(f"سلام {message.from_user.full_name}! به پنل نماینده خوش آمدید. 👋", reply_markup=rep_menu)
        else:
            await message.answer(f"سلام {message.from_user.full_name}! به ربات فروش سونی تل خوش آمدید. 👋\n\nبرای استفاده از ربات از منوی زیر استفاده کنید.", reply_markup=user_main_menu)
        return

    status = user_info.get('registration_status', 'new')
    if status == 'pending_admin':
        await message.answer("⏳ درخواست ثبت‌نام شما در انتظار تأیید ادمین است.")
        return
    if status == 'awaiting_referral':
        if not await is_user_member_of_force_channel(user_id):
            markup = await build_force_join_markup()
            await message.answer("📢 برای ادامه ثبت‌نام ابتدا در کانال اجباری عضو شوید و سپس «بررسی عضویت» را بزنید.", reply_markup=markup)
            await state.set_state(UserStates.waiting_for_channel_join)
            return
        await ask_for_referral_or_admin_approval(message)
        await state.set_state(UserStates.waiting_for_referral_code)
        return
    if status == 'rejected':
        reason = (user_info.get('rejection_reason') or '').strip()
        reason_text = f"\nدلیل رد: {reason}" if reason else ""
        await message.answer(f"❌ درخواست ثبت‌نام شما رد شده است.{reason_text}\nبرای بررسی مجدد با پشتیبانی تماس بگیرید.")
        return

    await message.answer("👋 سلام! برای استفاده از ربات، لطفاً ثبت‌نام کنید.\nنام و نام خانوادگی خود را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(UserStates.registration_full_name)

@router.message(UserStates.registration_full_name)
async def reg_get_full_name(message: types.Message, state: FSMContext, **kwargs):
    if not message.text or len(message.text.strip()) < 3:
        await message.answer("لطفاً یک نام معتبر (حداقل ۳ کاراکتر) وارد کنید.")
        return
    await state.update_data(full_name=message.text.strip())
    await message.answer("لطفاً شماره موبایل خود را فقط با استفاده از دکمه زیر به اشتراک بگذارید:", reply_markup=build_contact_share_keyboard())
    await state.set_state(UserStates.registration_phone)

@router.message(UserStates.registration_phone)
async def reg_get_phone(message: types.Message, state: FSMContext, **kwargs):
    if not message.contact:
        await message.answer("لطفاً فقط از دکمه «اشتراک شماره موبایل 📞» استفاده کنید.", reply_markup=build_contact_share_keyboard())
        return
    if getattr(message.contact, 'user_id', None) != message.from_user.id:
        await message.answer("⛔ فقط باید شماره موبایل متعلق به حساب خودتان را با دکمه اشتراک ارسال کنید.", reply_markup=build_contact_share_keyboard())
        return
    phone = normalize_phone(message.contact.phone_number) or message.contact.phone_number
    if not re.fullmatch(r'09\d{9}', phone):
        await message.answer("شماره موبایل ارسال‌شده معتبر نیست. لطفاً دوباره از دکمه اشتراک استفاده کنید.", reply_markup=build_contact_share_keyboard())
        return
    state_data = await state.get_data()
    user_id = message.from_user.id
    await data_manager.update_user(
        user_id,
        full_name=state_data['full_name'],
        phone_number=phone,
        phone_verified=1,
        registration_status='awaiting_referral',
        is_approved=0
    )
    full_name = state_data.get("full_name", "-")
    await safe_send_message(ADMIN_ID, f"🆕 کاربر جدید ثبت‌نام را آغاز کرد.\nنام: {escape_markdown(full_name)}\nشناسه: `{user_id}`\nشماره: `{escape_markdown(phone)}`", parse_mode='Markdown')

    if not await is_user_member_of_force_channel(user_id):
        markup = await build_force_join_markup()
        await message.answer("📢 برای تکمیل ثبت‌نام، ابتدا باید در کانال اجباری عضو شوید و سپس روی «بررسی عضویت» بزنید.", reply_markup=markup)
        await state.set_state(UserStates.waiting_for_channel_join)
        return

    await ask_for_referral_or_admin_approval(message)
    await state.set_state(UserStates.waiting_for_referral_code)

@router.callback_query(F.data == "verify_force_join")
async def verify_force_join(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    if not await is_user_member_of_force_channel(callback.from_user.id):
        await callback.message.answer("❌ هنوز عضویت شما در کانال تأیید نشد. لطفاً ابتدا عضو شوید و دوباره تلاش کنید.")
        return
    await ask_for_referral_or_admin_approval(callback.message)
    await state.set_state(UserStates.waiting_for_referral_code)

@router.callback_query(F.data == "register_without_referral")
async def register_without_referral(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    user_id = callback.from_user.id
    user_info = await data_manager.get_user(user_id)
    if not user_info:
        await callback.message.answer("ابتدا /start را بزنید.")
        return
    await data_manager.update_user(user_id, registration_status='pending_admin', is_approved=0)
    text = (
        f"🆕 **درخواست ثبت‌نام جدید**\n"
        f"**نام:** {escape_markdown(user_info.get('full_name', 'ناشناس'))}\n"
        f"**شناسه:** `{user_id}`\n"
        f"**شماره موبایل:** `{escape_markdown(user_info.get('phone_number', 'ثبت نشده'))}`\n"        f"**تاریخ:** {escape_markdown(format_persian_date(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))}"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        ikb_btn(text="✅ تأیید ثبت‌نام", style=BUTTON_STYLE_SUCCESS, callback_data=f"approve_registration_{user_id}"),
        ikb_btn(text="❌ رد", style=BUTTON_STYLE_DANGER, callback_data=f"reject_registration_{user_id}")
    ]])
    await safe_send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=markup)
    await callback.message.answer("⏳ درخواست ثبت‌نام شما برای ادمین ارسال شد. پس از تأیید، امکان استفاده از ربات فعال می‌شود.")
    await state.clear()

@router.message(UserStates.waiting_for_referral_code)
async def process_referral_code(message: types.Message, state: FSMContext, **kwargs):
    code = (message.text or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{5,16}', code):
        await message.answer("فرمت کد معرف معتبر نیست. دوباره وارد کنید یا روی «بدون کد معرف» بزنید.")
        return
    ref_user = await data_manager.get_user_by_referral_code(code)
    if not ref_user or not ref_user.get('is_approved'):
        await message.answer("❌ کد معرف معتبر نیست.")
        return
    new_code = await data_manager.approve_user_registration(
        message.from_user.id,
        approved_by=ref_user['user_id'],
        referrer_user_id=ref_user['user_id']
    )
    await safe_send_message(
        ADMIN_ID,
        f"✅ کاربر جدید با کد معرف ثبت شد.\nکاربر: `{message.from_user.id}`\nمعرف: `{ref_user['user_id']}`\nکد معرفی کاربر جدید: `{new_code}`",
        parse_mode="Markdown"
    )
    await message.answer(f"✅ ثبت‌نام شما با موفقیت تأیید شد.\nکد معرف شما: `{new_code}`", parse_mode="Markdown", reply_markup=user_main_menu)
    await state.clear()

@router.callback_query(F.data.startswith("approve_registration_"))
@admin_only
async def approve_registration(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    target_user_id = int(callback.data.rsplit("_", 1)[-1])
    user_info = await data_manager.get_user(target_user_id)
    if not user_info:
        await callback.message.edit_text("کاربر یافت نشد.")
        return
    code = await data_manager.approve_user_registration(target_user_id, approved_by=callback.from_user.id)
    await callback.message.edit_text(f"✅ ثبت‌نام کاربر `{target_user_id}` تأیید شد.\nکد معرف: `{code}`", parse_mode="Markdown")
    await safe_send_message(target_user_id, f"✅ ثبت‌نام شما تأیید شد.\nکد معرف شما: `{code}`", parse_mode="Markdown", reply_markup=user_main_menu)

@router.callback_query(F.data.startswith("reject_registration_"))
@admin_only
async def reject_registration(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    target_user_id = int(callback.data.rsplit("_", 1)[-1])
    await state.update_data(reject_registration_user_id=target_user_id)
    await callback.message.edit_text("لطفاً دلیل رد ثبت‌نام را ارسال کنید.\nبرای رد بدون توضیح، فقط `-` را بفرستید.", parse_mode="Markdown", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_registration_rejection_reason)


@router.message(AdminStates.waiting_for_registration_rejection_reason)
async def reject_registration_reason(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    state_data = await state.get_data()
    target_user_id = int(state_data.get('reject_registration_user_id') or 0)
    if not target_user_id:
        await message.answer("درخواست نامعتبر است. دوباره تلاش کنید.")
        await state.clear()
        return
    raw_reason = (message.text or '').strip()
    reason = '' if raw_reason == '-' else raw_reason
    await data_manager.reject_user_registration(target_user_id, approved_by=message.from_user.id, reason=reason)
    reason_line = f"\nدلیل رد: {reason}" if reason else ''
    await message.answer(f"❌ ثبت‌نام کاربر `{target_user_id}` رد شد.{reason_line}", parse_mode="Markdown")
    await safe_send_message(target_user_id, f"❌ درخواست ثبت‌نام شما رد شد.{reason_line}", reply_markup=start_button)
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

# =================================================================
