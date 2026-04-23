import asyncio
import hashlib
import os
import smtplib
from email.mime.text import MIMEText

from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from app import bot, data_manager, dp
from config import ADMIN_ID, BACKUP_DIR, BUTTON_STYLE_DANGER, BUTTON_STYLE_PRIMARY, BUTTON_STYLE_SUCCESS, EMAIL_PASS, EMAIL_USER, UPLOADS_DIR, logger
from keyboards.inline import ikb_btn
from keyboards.reply import admin_main_menu, rep_menu, user_main_menu
from .formatters import escape_markdown_code, normalize_server_address
from .parsers import normalize_channel_ref, parse_channel_value, parse_config_file_marker

copy_temp_storage = {}


def has_verified_phone(user_info: dict) -> bool:
    if not user_info:
        return False
    phone = (user_info.get('phone_number') or '').strip()
    return bool(phone) and phone != 'ثبت نشده' and bool(user_info.get('phone_verified'))


def is_safe_managed_file(path_value: str) -> bool:
    try:
        real_path = os.path.realpath(path_value or '')
        if not real_path or not os.path.isfile(real_path):
            return False
        allowed_dirs = [os.path.realpath(UPLOADS_DIR), os.path.realpath(BACKUP_DIR)]
        return any(real_path.startswith(base + os.sep) or real_path == base for base in allowed_dirs)
    except Exception:
        return False


def send_email(to_email, subject, body):
    if not EMAIL_USER or not EMAIL_PASS:
        logger.warning('اطلاعات ایمیل تنظیم نشده است.')
        return False
    msg = MIMEText(body, 'html', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = EMAIL_USER
    msg['To'] = to_email
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logger.error(f'Failed to send email to {to_email}: {e}')
        return False


async def schedule_photo_deletion(file_name: str, days: int, user_id: int, purpose: str):
    await data_manager.add_file_cleanup(file_name, days, user_id, purpose)


async def ask_for_referral_or_admin_approval(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text='⏭ بدون کد معرف', style=BUTTON_STYLE_PRIMARY, callback_data='register_without_referral')]])
    await message.answer('اگر کد معرف دارید وارد کنید تا ثبت‌نام شما خودکار تأیید شود.\nدر غیر این صورت روی «بدون کد معرف» بزنید تا درخواست شما برای ادمین ارسال شود.', reply_markup=keyboard)


async def safe_callback_answer(callback: types.CallbackQuery, text: str = None, show_alert: bool = False):
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except Exception:
        pass


async def safe_send_message(chat_id, text: str, **kwargs):
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except TelegramBadRequest:
        kwargs.pop('parse_mode', None)
        kwargs.pop('reply_markup', None)
        return await bot.send_message(chat_id, text)
    except Exception as e:
        logger.warning(f'Failed to send message to {chat_id}: {e}')
        return None


async def safe_send_document(chat_id, document, **kwargs):
    try:
        return await bot.send_document(chat_id, document, **kwargs)
    except TelegramBadRequest:
        kwargs.pop('caption', None)
        return await bot.send_document(chat_id, document)
    except Exception as e:
        logger.warning(f'Failed to send document to {chat_id}: {e}')
        return None


async def safe_edit_callback_message(callback: types.CallbackQuery, text: str, **kwargs):
    try:
        if getattr(callback.message, 'caption', None):
            return await callback.message.edit_caption(text, **kwargs)
        return await callback.message.edit_text(text, **kwargs)
    except TelegramBadRequest:
        return await callback.message.answer(text, **kwargs)
    except Exception as e:
        logger.warning(f'Failed to edit callback message: {e}')
        try:
            return await callback.message.answer(text, **kwargs)
        except Exception:
            return None


async def is_user_member_of_force_channel(user_id: int) -> bool:
    channel_value = normalize_channel_ref(await data_manager.get_setting('mandatory_join_channel'))
    if not channel_value:
        return True
    parsed = parse_channel_value(channel_value, require_username=True)
    target_chat = parsed.get('chat_id') or parsed.get('username')
    try:
        member = await bot.get_chat_member(target_chat, user_id)
        return member.status in ('member', 'administrator', 'creator', 'restricted')
    except Exception as e:
        logger.warning(f'Failed to check mandatory channel membership: {e}')
        return False


async def build_force_join_markup() -> InlineKeyboardMarkup:
    channel_value = normalize_channel_ref(await data_manager.get_setting('mandatory_join_channel'))
    parsed = parse_channel_value(channel_value, require_username=True)
    join_url = f"https://t.me/{parsed['username'][1:]}"
    return InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text='📢 عضویت در کانال اجباری', style=BUTTON_STYLE_PRIMARY, url=join_url)], [ikb_btn(text='✅ بررسی عضویت', style=BUTTON_STYLE_SUCCESS, callback_data='verify_force_join')], [ikb_btn(text='❌ لغو', style=BUTTON_STYLE_DANGER, callback_data='cancel')]])


async def check_rate_limit(user_id: int) -> bool:
    if not await data_manager.can_make_request(user_id, cooldown_seconds=10):
        return False
    await data_manager.update_last_request_time(user_id)
    return True


async def cleanup_temp_storage(keys, delay):
    await asyncio.sleep(delay)
    for k in keys:
        copy_temp_storage.pop(k, None)


async def state_safe_clear_for_admin(message: types.Message):
    try:
        state = dp.fsm.get_context(bot=bot, chat_id=message.chat.id, user_id=message.from_user.id)
        await state.clear()
    except Exception:
        pass


async def get_main_menu_for_user(user_id: int):
    user_info = await data_manager.get_user(user_id)
    if await data_manager.is_admin(user_id):
        return admin_main_menu
    if user_info and user_info.get('is_rep'):
        return rep_menu
    return user_main_menu


async def refresh_user_role_menu(user_id: int, notice: str = None):
    reply_markup = await get_main_menu_for_user(user_id)
    try:
        await bot.send_message(user_id, notice or '✅ نقش و دسترسی شما به‌روزرسانی شد.', reply_markup=reply_markup)
    except Exception:
        pass


async def send_account_with_copy_buttons(chat_id: int, account: dict, extra_buttons: list = None):
    text = '📝 **اطلاعات اکانت:**\n'
    buttons = []
    temp_store = {}
    account_type = (account.get('account_type') or 'other').lower()

    def add_copy_field(label: str, value: str):
        nonlocal text, buttons, temp_store
        if not value:
            return
        text += f"**{label}:** `{escape_markdown_code(value)}`\n"
        value_id = f"copy_{hashlib.md5(value.encode()).hexdigest()[:8]}"
        temp_store[value_id] = value
        buttons.append([InlineKeyboardButton(text=f'📋 کپی {label}', callback_data=value_id)])

    if account_type in ('openvpn', 'l2tp', 'anyconnect'):
        add_copy_field('نام کاربری', account.get('username', ''))
        add_copy_field('رمز عبور', account.get('password', ''))
        add_copy_field('کلید (Secret)', account.get('secret', ''))
        if account.get('server'):
            add_copy_field('آدرس سرور', normalize_server_address(account.get('server', '')))
        if account_type == 'openvpn' and account.get('config'):
            cfg_path, cfg_caption = parse_config_file_marker(account['config'])
            if cfg_path:
                if is_safe_managed_file(cfg_path):
                    await safe_send_document(chat_id, FSInputFile(cfg_path), caption=(cfg_caption or 'فایل کانفیگ OpenVPN'))
                add_copy_field('نام فایل کانفیگ', os.path.basename(cfg_path))
            else:
                add_copy_field('فایل کانفیگ', account['config'])
        if account.get('extra_note'):
            label = 'لینک دانلود' if account_type == 'openvpn' else 'توضیحات'
            add_copy_field(label, account.get('extra_note', ''))
    elif account_type == 'v2ray':
        if account.get('config'):
            add_copy_field('لینک', account['config'])
    elif account_type == 'wireguard':
        if account.get('config'):
            add_copy_field('کانفیگ WireGuard', account['config'])
    else:
        if account.get('config'):
            add_copy_field('اطلاعات', account['config'])
        add_copy_field('نام کاربری', account.get('username', ''))
        add_copy_field('رمز عبور', account.get('password', ''))
        if account.get('server'):
            add_copy_field('سرور', account.get('server', ''))

    copy_temp_storage.update(temp_store)
    asyncio.create_task(cleanup_temp_storage(list(temp_store.keys()), 60))
    if extra_buttons:
        buttons.extend(extra_buttons)
    buttons.append([ikb_btn(text='🔙 بازگشت', callback_data='back_to_purchase')])
    await safe_send_message(chat_id, text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


async def notify_financial_admins_and_admin(message_text: str, photo_id: str = None, reply_markup: InlineKeyboardMarkup = None):
    if photo_id:
        await bot.send_photo(ADMIN_ID, photo=photo_id, caption=message_text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await bot.send_message(ADMIN_ID, message_text, parse_mode='Markdown', reply_markup=reply_markup)


def admin_only(handler):
    async def wrapper(callback, *args, **kwargs):
        kwargs.pop('dispatcher', None)
        if not await data_manager.is_admin(callback.from_user.id):
            await callback.answer('⛔ شما دسترسی ادمین ندارید.', show_alert=True)
            return
        return await handler(callback, *args, **kwargs)
    return wrapper


def rate_limit(seconds=10):
    def decorator(handler):
        async def wrapper(message: types.Message, *args, **kwargs):
            kwargs.pop('dispatcher', None)
            if not await check_rate_limit(message.from_user.id):
                await message.answer('⏳ لطفاً کمی صبر کنید و سپس دوباره تلاش کنید.')
                return
            return await handler(message, *args, **kwargs)
        return wrapper
    return decorator
