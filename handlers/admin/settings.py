import datetime
import os
import re
import shutil

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from app import bot, data_manager
from config import ADMIN_ID, BACKUP_DIR, BUTTON_STYLE_DANGER, BUTTON_STYLE_PRIMARY, BUTTON_STYLE_SUCCESS, logger
from states.admin_states import AdminStates
from keyboards.inline import back_to_admin_inline, cancel_only_button, ikb_btn
from keyboards.reply import admin_main_menu
from utils.formatters import escape_markdown
from utils.parsers import parse_channel_value
from utils.settings_helpers import get_primary_usdt_network, get_usdt_setting_key
from utils.telegram_utils import admin_only, safe_callback_answer, safe_edit_callback_message
router = Router()

# 18. سایر هندلرهای ادمین (تنظیمات ربات، مدیریت ادمین‌ها، حساب‌های بانکی)
# =================================================================
def build_admin_settings_menu(section: str = "main") -> InlineKeyboardMarkup:
    if section == "main":
        return InlineKeyboardMarkup(inline_keyboard=[
            [ikb_btn(text="🟢 وضعیت و عملکرد", style=BUTTON_STYLE_SUCCESS, callback_data="settings_section_status")],
            [ikb_btn(text="💳 پرداخت و کیف پول", style=BUTTON_STYLE_PRIMARY, callback_data="settings_section_payment")],
            [ikb_btn(text="📝 محتوا و آموزش", style=BUTTON_STYLE_PRIMARY, callback_data="settings_section_content")],
            [ikb_btn(text="📡 کانال و فایل سرور", style=BUTTON_STYLE_PRIMARY, callback_data="settings_section_channel")],
            [ikb_btn(text="🎯 معرفی و پورسانت", style=BUTTON_STYLE_PRIMARY, callback_data="settings_section_referral")],
            [ikb_btn(text="📊 گزارش و نگهداری", style=BUTTON_STYLE_PRIMARY, callback_data="settings_section_reports")],
            [ikb_btn(text="🔙 بازگشت به منوی ادمین", style=BUTTON_STYLE_DANGER, callback_data="back_to_main")],
        ])
    if section == "status":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"وضعیت کلی ربات: {'روشن 🟢' if (CURRENT_BOT_STATUS := globals().get('_current_bot_status','on'))=='on' else 'خاموش 🔴'}", callback_data="toggle_bot_status")],
            [InlineKeyboardButton(text=f"وضعیت فروشگاه: {'روشن 🟢' if (CURRENT_SHOP_STATUS := globals().get('_current_shop_status','on'))=='on' else 'خاموش 🔴'}", callback_data="toggle_shop_status")],
            [InlineKeyboardButton(text=f"حالت انتخاب حساب بانکی: {globals().get('_current_bank_mode_text','ثابت (پیش‌فرض) 📌')}", callback_data="toggle_bank_mode")],
            [InlineKeyboardButton(text=f"💰 مبلغ مورد نیاز برای نمایندگی: {int(globals().get('_current_rep_required','0')):,} تومان", callback_data="set_rep_required_amount")],
            [ikb_btn(text="🔙 بازگشت به تنظیمات", style=BUTTON_STYLE_DANGER, callback_data="back_to_settings")],
        ])
    if section == "payment":
        return InlineKeyboardMarkup(inline_keyboard=[
            [ikb_btn(text="💳 حداقل مبلغ شارژ کیف پول", callback_data="set_min_wallet_topup")],
            [ikb_btn(text="⏰ یادآور پرداخت‌های معلق", callback_data="set_pending_payment_alert_minutes")],
            [ikb_btn(text="👤 روش‌های پرداخت کاربران عادی", callback_data="pm_role_user")],
            [ikb_btn(text="🧑‍💻 روش‌های پرداخت نمایندگان", callback_data="pm_role_rep")],
            [ikb_btn(text="₮ مدیریت کیف پول‌های تتر", style=BUTTON_STYLE_PRIMARY, callback_data="set_usdt_wallet")],
            [ikb_btn(text="🌐 تنظیم شبکه اصلی تتر", style=BUTTON_STYLE_PRIMARY, callback_data="toggle_usdt_network")],
            [ikb_btn(text="🔙 بازگشت به تنظیمات", style=BUTTON_STYLE_DANGER, callback_data="back_to_settings")],
        ])
    if section == "content":
        return InlineKeyboardMarkup(inline_keyboard=[
            [ikb_btn(text="📝 پیام خوش‌آمد", callback_data="set_welcome_message")],
            [ikb_btn(text="📜 قوانین/توضیحات قبل از خرید", callback_data="set_buy_terms")],
            [ikb_btn(text="🎓 آموزش خرید با تتر", callback_data="set_usdt_tutorial")],
            [ikb_btn(text="🔙 بازگشت به تنظیمات", style=BUTTON_STYLE_DANGER, callback_data="back_to_settings")],
        ])
    if section == "referral":
        enabled = globals().get('_current_referral_enabled', 'on')
        mode = globals().get('_current_referral_mode', 'first_purchase')
        mode_label = 'فقط خرید اول' if mode == 'first_purchase' else 'همه خریدهای موفق'
        percent = globals().get('_current_referral_percent', '1')
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"سیستم معرفی: {'فعال 🟢' if enabled == 'on' else 'غیرفعال 🔴'}", callback_data="toggle_referral_system")],
            [InlineKeyboardButton(text=f"درصد پاداش: {percent}%", callback_data="set_referral_reward_percent")],
            [InlineKeyboardButton(text=f"حالت پاداش: {mode_label}", callback_data="toggle_referral_reward_mode")],
            [ikb_btn(text="📊 داشبورد معرفی", callback_data="show_referral_dashboard")],
            [ikb_btn(text="🔙 بازگشت به تنظیمات", style=BUTTON_STYLE_DANGER, callback_data="back_to_settings")],
        ])
    if section == "channel":
        return InlineKeyboardMarkup(inline_keyboard=[
            [ikb_btn(text="📢 تنظیم کانال عضویت اجباری", callback_data="set_mandatory_join_channel")],
            [ikb_btn(text="📁 ثبت آخرین فایل کانفیگ OpenVPN", callback_data="edu_set_latest_ovpn")],
            [ikb_btn(text="📥 دریافت آخرین فایل سرور", callback_data="download_latest_openvpn_config")],
            [ikb_btn(text="🔌 اتصال به سرور V2Ray", callback_data="v2ray_connection_menu")],
            [ikb_btn(text="🔙 بازگشت به تنظیمات", style=BUTTON_STYLE_DANGER, callback_data="back_to_settings")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [ikb_btn(text="📦 آستانه هشدار کمبود موجودی", callback_data="set_low_stock_threshold")],
        [ikb_btn(text="📊 آمار کلی", callback_data="show_bot_stats"), ikb_btn(text="📈 گزارش روزانه", callback_data="show_daily_report")],
        [ikb_btn(text="🗓 گزارش هفتگی", callback_data="show_weekly_report")],
        [ikb_btn(text="🗄 دانلود بکاپ دیتابیس", callback_data="download_db_backup")],
        [ikb_btn(text="🔙 بازگشت به تنظیمات", style=BUTTON_STYLE_DANGER, callback_data="back_to_settings")],
    ])

async def render_admin_settings(target):
    bot_status = await data_manager.get_setting('bot_status')
    shop_status = await data_manager.get_setting('shop_status')
    bank_mode = await data_manager.get_setting('bank_selection_mode')
    rep_required = await data_manager.get_setting('representative_required_balance') or '0'
    referral_enabled = await data_manager.get_setting('referral_system_enabled') or 'on'
    referral_percent = await data_manager.get_setting('referral_reward_percent') or '1'
    referral_mode = await data_manager.get_setting('referral_reward_mode') or 'first_purchase'
    globals()['_current_bot_status'] = bot_status
    globals()['_current_shop_status'] = shop_status
    globals()['_current_bank_mode_text'] = "تصادفی 🎲" if bank_mode == "random" else "ثابت (پیش‌فرض) 📌"
    globals()['_current_rep_required'] = rep_required
    globals()['_current_referral_enabled'] = referral_enabled
    globals()['_current_referral_percent'] = referral_percent
    globals()['_current_referral_mode'] = referral_mode
    text = "⚙️ تنظیمات ربات\nیکی از بخش‌های زیر را انتخاب کنید:"
    markup = build_admin_settings_menu("main")
    if hasattr(target, 'answer') and not hasattr(target, 'message'):
        return await target.answer(text, reply_markup=markup)
    if hasattr(target, 'message'):
        return await safe_edit_callback_message(target, text, reply_markup=markup)
    return await target.answer(text, reply_markup=markup)

@router.message(F.text == "⚙️ تنظیمات ربات")
async def handle_settings(message: types.Message, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        return
    await render_admin_settings(message)


@router.callback_query(F.data == "back_to_settings")
@admin_only
async def back_to_settings(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    await render_admin_settings(callback)



@router.callback_query(F.data.startswith("settings_section_"))
@admin_only
async def open_settings_section(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    section = callback.data.split("settings_section_", 1)[1]
    titles = {
        "status": "🟢 وضعیت و عملکرد",
        "payment": "💳 پرداخت و کیف پول",
        "content": "📝 محتوا و آموزش",
        "channel": "📡 کانال و فایل سرور",
        "referral": "🎯 معرفی و پورسانت",
        "reports": "📊 گزارش و نگهداری",
    }
    await safe_edit_callback_message(
        callback,
        f"{titles.get(section, '⚙️ تنظیمات')}\nگزینه موردنظر را انتخاب کنید:",
        reply_markup=build_admin_settings_menu(section),
    )



async def render_referral_settings(callback: types.CallbackQuery):
    enabled = await data_manager.get_setting('referral_system_enabled') or 'on'
    percent = await data_manager.get_setting('referral_reward_percent') or '1'
    mode = await data_manager.get_setting('referral_reward_mode') or 'first_purchase'
    globals()['_current_referral_enabled'] = enabled
    globals()['_current_referral_percent'] = percent
    globals()['_current_referral_mode'] = mode
    await safe_edit_callback_message(
        callback,
        '🎯 معرفی و پورسانت\nگزینه موردنظر را انتخاب کنید:',
        reply_markup=build_admin_settings_menu('referral'),
    )


@router.callback_query(F.data == "toggle_referral_system")
@admin_only
async def toggle_referral_system(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    current = (await data_manager.get_setting('referral_system_enabled') or 'on').strip().lower()
    new_value = 'off' if current == 'on' else 'on'
    await data_manager.set_setting('referral_system_enabled', new_value)
    await render_referral_settings(callback)


@router.callback_query(F.data == "toggle_referral_reward_mode")
@admin_only
async def toggle_referral_reward_mode(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    current = (await data_manager.get_setting('referral_reward_mode') or 'first_purchase').strip().lower()
    new_value = 'all_successful' if current == 'first_purchase' else 'first_purchase'
    await data_manager.set_setting('referral_reward_mode', new_value)
    await render_referral_settings(callback)


@router.callback_query(F.data == "set_referral_reward_percent")
@admin_only
async def set_referral_reward_percent_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        'لطفاً درصد پاداش معرفی را وارد کنید.\nمثال: 1 یا 2.5',
        reply_markup=cancel_only_button
    )
    await state.set_state(AdminStates.waiting_for_referral_reward_percent)


@router.message(AdminStates.waiting_for_referral_reward_percent)
async def set_referral_reward_percent_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer('⛔ دسترسی غیرمجاز.')
        await state.clear()
        return
    raw = (message.text or '').strip().replace('٪', '').replace('%', '')
    try:
        value = float(raw)
    except ValueError:
        await message.answer('لطفاً یک عدد معتبر وارد کنید.')
        return
    if value < 0 or value > 100:
        await message.answer('درصد باید بین 0 تا 100 باشد.')
        return
    stored = str(int(value)) if value.is_integer() else str(value)
    await data_manager.set_setting('referral_reward_percent', stored)
    await state.clear()
    await message.answer(f'✅ درصد پاداش معرفی روی {stored}% تنظیم شد.', reply_markup=admin_main_menu)


def build_referral_dashboard_markup(items: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for item in items[:10]:
        rows.append([
            ikb_btn(
                text=f"👤 {item.get('full_name','ناشناس')} | {int(item.get('referrals_count',0))} نفر | {int(item.get('total_reward',0)):,} تومان",
                callback_data=f"referral_detail_{int(item.get('user_id',0))}"
            )
        ])
    rows.append([ikb_btn(text='🔙 بازگشت به تنظیمات', style=BUTTON_STYLE_DANGER, callback_data='settings_section_referral')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "show_referral_dashboard")
@admin_only
async def show_referral_dashboard(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    items = await data_manager.get_referral_admin_report(limit=20)
    enabled = await data_manager.get_setting('referral_system_enabled') or 'on'
    percent = await data_manager.get_setting('referral_reward_percent') or '1'
    mode = await data_manager.get_setting('referral_reward_mode') or 'first_purchase'
    mode_label = 'فقط خرید اول' if mode == 'first_purchase' else 'همه خریدهای موفق'
    if not items:
        text = (
            '📊 داشبورد معرفی\n\n'
            f'سیستم: {"فعال" if enabled == "on" else "غیرفعال"}\n'
            f'درصد پاداش: {percent}%\n'
            f'حالت پاداش: {mode_label}\n\n'
            'هنوز داده‌ای برای نمایش وجود ندارد.'
        )
        await safe_edit_callback_message(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text='🔙 بازگشت به تنظیمات', style=BUTTON_STYLE_DANGER, callback_data='settings_section_referral')]]))
        return
    total_referrals = sum(int(x.get('referrals_count', 0) or 0) for x in items)
    total_reward = sum(int(x.get('total_reward', 0) or 0) for x in items)
    total_sales = sum(int(x.get('downline_sales', 0) or 0) for x in items)
    lines = [
        '📊 داشبورد معرفی',
        '',
        f'سیستم: {"فعال" if enabled == "on" else "غیرفعال"}',
        f'درصد پاداش: {percent}%',
        f'حالت پاداش: {mode_label}',
        '',
        f'تعداد معرف‌های فعال: {len(items)}',
        f'تعداد معرفی‌ها: {total_referrals}',
        f'فروش زیرمجموعه: {total_sales:,} تومان',
        f'مجموع پاداش: {total_reward:,} تومان',
        '',
        'برای دیدن جزئیات هر معرف، روی نام او بزنید.'
    ]
    await safe_edit_callback_message(callback, '\n'.join(lines), reply_markup=build_referral_dashboard_markup(items))


@router.callback_query(F.data.regexp(r'^referral_detail_\d+$'))
@admin_only
async def show_referral_detail(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    target_user_id = int((callback.data or '').rsplit('_', 1)[-1])
    user = await data_manager.get_user(target_user_id)
    if not user:
        await callback.answer('کاربر یافت نشد.', show_alert=True)
        return
    summary = await data_manager.get_referral_summary(target_user_id)
    recent_rewards = await data_manager.get_referral_admin_report(user_id=target_user_id, limit=10)
    chain = summary.get('chain', [])
    chain_text = ' ← '.join(item.get('full_name', 'ناشناس') for item in chain) if chain else 'ندارد'
    lines = [
        f"👤 جزئیات معرف: {user.get('full_name','ناشناس')}",
        f"کد معرف: {user.get('referral_code') or 'ندارد'}",
        f"تعداد معرفی کل: {summary.get('referred_count',0)} نفر",
        f"تعداد معرفی تأییدشده: {summary.get('approved_referred_count',0)} نفر",
        f"فروش زیرمجموعه: {int(summary.get('downline_sales',0)):,} تومان",
        f"مجموع پاداش: {int(summary.get('total_reward',0)):,} تومان",
        f"زنجیره معرفی: {chain_text}",
    ]
    if recent_rewards:
        lines.append('')
        lines.append('آخرین پاداش‌ها:')
        for item in recent_rewards[:5]:
            lines.append(
                f"- {item.get('referred_full_name','ناشناس')} | خرید {int(item.get('purchase_amount',0)):,} | پاداش {int(item.get('reward_amount',0)):,}"
            )
    await safe_edit_callback_message(
        callback,
        '\n'.join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text='🔙 بازگشت به داشبورد معرفی', style=BUTTON_STYLE_PRIMARY, callback_data='show_referral_dashboard')]])
    )

async def show_role_payment_methods_settings(callback: types.CallbackQuery, role_key: str):
    raw = (await data_manager.get_setting(f'{role_key}_allowed_payment_methods') or '').strip()
    if not raw:
        raw = 'card,usdt,credit' if role_key in ('admin', 'rep') else 'card,usdt'
    current = []
    for item in [x.strip().lower() for x in raw.split(',') if x.strip()]:
        if item not in current:
            current.append(item)

    role_titles = {
        'user': 'کاربران عادی',
        'rep': 'نمایندگان',
        'admin': 'ادمین‌ها',
    }
    labels = {
        'card': 'کارت به کارت',
        'usdt': 'تتر (USDT)',
        'credit': 'نسیه',
    }

    rows = []
    for key in ('card', 'usdt', 'credit'):
        enabled = key in current
        rows.append([
            ikb_btn(
                text=f"{'✅' if enabled else '❌'} {labels[key]}",
                style=BUTTON_STYLE_SUCCESS if enabled else BUTTON_STYLE_DANGER,
                callback_data=f'pm_toggle_{role_key}_{key}'
            )
        ])
    rows.append([ikb_btn(text='🔙 بازگشت به تنظیمات', style=BUTTON_STYLE_PRIMARY, callback_data='back_to_settings')])

    await safe_edit_callback_message(
        callback,
        f"⚙️ تنظیم روش‌های پرداخت برای {role_titles.get(role_key, role_key)}\n\n"
        "برای فعال/غیرفعال کردن هر روش، روی همان دکمه بزنید.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )

@router.callback_query(F.data.in_(["pm_role_user", "pm_role_rep", "pm_role_admin"]))
@admin_only
async def payment_methods_role_menu(callback: types.CallbackQuery, **kwargs):
    role_key = (callback.data or '').split('pm_role_', 1)[1]
    await show_role_payment_methods_settings(callback, role_key)

@router.callback_query(F.data.regexp(r"^pm_toggle_(user|rep|admin)_(card|usdt|credit)$"))
@admin_only
async def payment_methods_toggle(callback: types.CallbackQuery, **kwargs):
    _, _, role_key, method_key = (callback.data or '').split('_', 3)
    raw = (await data_manager.get_setting(f'{role_key}_allowed_payment_methods') or '').strip()
    if not raw:
        raw = 'card,usdt,credit' if role_key in ('admin', 'rep') else 'card,usdt'
    items = [x.strip().lower() for x in raw.split(',') if x.strip()]
    current = []
    for item in items:
        if item not in current:
            current.append(item)
    if method_key in current:
        if len(current) == 1:
            await callback.answer('حداقل یک روش پرداخت باید فعال بماند.', show_alert=True)
            return
        current.remove(method_key)
    else:
        current.append(method_key)
    await data_manager.set_setting(f'{role_key}_allowed_payment_methods', ','.join(current))
    await show_role_payment_methods_settings(callback, role_key)

@router.callback_query(F.data == "toggle_bot_status")
@admin_only
async def toggle_bot_status(callback: types.CallbackQuery, **kwargs):
    current = await data_manager.get_setting('bot_status')
    new_status = "off" if current == "on" else "on"
    await data_manager.set_setting('bot_status', new_status)
    await callback.message.edit_text(f"✅ وضعیت کلی ربات به {'خاموش 🔴' if new_status=='off' else 'روشن 🟢'} تغییر یافت.")

@router.callback_query(F.data == "toggle_shop_status")
@admin_only
async def toggle_shop_status(callback: types.CallbackQuery, **kwargs):
    current = await data_manager.get_setting('shop_status')
    new_status = "off" if current == "on" else "on"
    await data_manager.set_setting('shop_status', new_status)
    await callback.message.edit_text(f"✅ وضعیت فروشگاه به {'خاموش 🔴' if new_status=='off' else 'روشن 🟢'} تغییر یافت.")

@router.callback_query(F.data == "toggle_bank_mode")
@admin_only
async def toggle_bank_mode(callback: types.CallbackQuery, **kwargs):
    current = await data_manager.get_setting('bank_selection_mode')
    new_mode = "random" if current == "fixed" else "fixed"
    await data_manager.set_setting('bank_selection_mode', new_mode)
    mode_text = "تصادفی 🎲" if new_mode == "random" else "ثابت (پیش‌فرض) 📌"
    await callback.message.edit_text(f"✅ حالت انتخاب حساب بانکی به {mode_text} تغییر یافت.")

@router.callback_query(F.data == "set_rep_required_amount")
@admin_only
async def set_rep_required_amount_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_text("لطفاً مبلغ مورد نیاز برای درخواست نمایندگی را به تومان وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_representative_deposit_amount)

@router.message(AdminStates.waiting_for_representative_deposit_amount)
async def set_rep_required_amount_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    try:
        amount = int(message.text)
        if amount < 0:
            await message.answer("لطفاً عدد مثبت وارد کنید.")
            return
        await data_manager.set_setting('representative_required_balance', str(amount))
        await message.answer(f"✅ مبلغ مورد نیاز برای درخواست نمایندگی به {amount:,} تومان تنظیم شد.", reply_markup=admin_main_menu)
    except ValueError:
        await message.answer("لطفاً یک عدد معتبر وارد کنید.")
    await state.clear()


@router.callback_query(F.data == "set_welcome_message")
@admin_only
async def set_welcome_message_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    current = (await data_manager.get_setting('welcome_message') or '').strip() or 'تنظیم نشده'
    await callback.message.edit_text(f"پیام خوش‌آمد فعلی:\n\n{current}\n\nمتن جدید را بفرستید. برای حذف، خط تیره بفرستید.", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_welcome_message)

@router.message(AdminStates.waiting_for_welcome_message)
async def set_welcome_message_process(message: types.Message, state: FSMContext, **kwargs):
    value = '' if (message.text or '').strip() == '-' else (message.text or '').strip()
    await data_manager.set_setting('welcome_message', value)
    await message.answer('✅ پیام خوش‌آمد ذخیره شد.' if value else '✅ پیام خوش‌آمد حذف شد.', reply_markup=admin_main_menu)
    await state.clear()

@router.callback_query(F.data == "set_buy_terms")
@admin_only
async def set_buy_terms_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    current = (await data_manager.get_setting('buy_terms') or '').strip() or 'تنظیم نشده'
    await callback.message.edit_text(f"متن فعلی قوانین خرید:\n\n{current}\n\nمتن جدید را بفرستید. برای حذف، خط تیره بفرستید.", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_buy_terms)

@router.message(AdminStates.waiting_for_buy_terms)
async def set_buy_terms_process(message: types.Message, state: FSMContext, **kwargs):
    value = '' if (message.text or '').strip() == '-' else (message.text or '').strip()
    await data_manager.set_setting('buy_terms', value)
    await message.answer('✅ قوانین خرید ذخیره شد.' if value else '✅ قوانین خرید حذف شد.', reply_markup=admin_main_menu)
    await state.clear()


@router.callback_query(F.data == "set_usdt_tutorial")
@admin_only
async def set_usdt_tutorial_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    current = (await data_manager.get_setting('usdt_buy_tutorial') or '').strip() or 'تنظیم نشده'
    msg = (
        "متن فعلی آموزش خرید با تتر:\n\n"
        f"{current}\n\n"
        "متن جدید را بفرستید. برای بازگشت به متن پیش‌فرض، خط تیره بفرستید."
    )
    await callback.message.edit_text(msg, reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_usdt_tutorial_text)

@router.message(AdminStates.waiting_for_usdt_tutorial_text)
async def set_usdt_tutorial_process(message: types.Message, state: FSMContext, **kwargs):
    value = '' if (message.text or '').strip() == '-' else (message.text or '').strip()
    await data_manager.set_setting('usdt_buy_tutorial', value)
    if value:
        await message.answer('✅ آموزش خرید با تتر ذخیره شد.', reply_markup=admin_main_menu)
    else:
        await message.answer('✅ آموزش خرید با تتر به متن پیش‌فرض بازگردانده شد.', reply_markup=admin_main_menu)
    await state.clear()

@router.callback_query(F.data == "set_min_wallet_topup")
@admin_only
async def set_min_wallet_topup_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    current = int(await data_manager.get_setting('min_wallet_topup') or '10000')
    await callback.message.edit_text(f"حداقل مبلغ شارژ فعلی: {current:,} تومان\n\nمبلغ جدید را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_min_wallet_topup)

@router.message(AdminStates.waiting_for_min_wallet_topup)
async def set_min_wallet_topup_process(message: types.Message, state: FSMContext, **kwargs):
    try:
        amount = int((message.text or '0').strip())
        if amount < 0:
            raise ValueError
        await data_manager.set_setting('min_wallet_topup', str(amount))
        await message.answer(f"✅ حداقل مبلغ شارژ روی {amount:,} تومان تنظیم شد.", reply_markup=admin_main_menu)
        await state.clear()
    except ValueError:
        await message.answer('لطفاً عدد معتبر وارد کنید.')

@router.callback_query(F.data == "set_low_stock_threshold")
@admin_only
async def set_low_stock_threshold_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    current = int(await data_manager.get_setting('low_stock_threshold') or '5')
    await callback.message.edit_text(f"آستانه فعلی هشدار کمبود موجودی: {current}\n\nعدد جدید را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_low_stock_threshold)

@router.message(AdminStates.waiting_for_low_stock_threshold)
async def set_low_stock_threshold_process(message: types.Message, state: FSMContext, **kwargs):
    try:
        amount = int((message.text or '0').strip())
        if amount < 0:
            raise ValueError
        await data_manager.set_setting('low_stock_threshold', str(amount))
        await message.answer(f"✅ آستانه هشدار کمبود موجودی روی {amount} تنظیم شد.", reply_markup=admin_main_menu)
        await state.clear()
    except ValueError:
        await message.answer('لطفاً عدد معتبر وارد کنید.')

@router.callback_query(F.data == "set_pending_payment_alert_minutes")
@admin_only
async def set_pending_payment_alert_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    current = int(await data_manager.get_setting('pending_payment_alert_minutes') or '30')
    await callback.message.edit_text(f"مدت فعلی هشدار پرداخت معلق: {current} دقیقه\n\nمقدار جدید را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_pending_payment_alert)

@router.message(AdminStates.waiting_for_pending_payment_alert)
async def set_pending_payment_alert_process(message: types.Message, state: FSMContext, **kwargs):
    try:
        amount = int((message.text or '0').strip())
        if amount <= 0:
            raise ValueError
        await data_manager.set_setting('pending_payment_alert_minutes', str(amount))
        await message.answer(f"✅ بازه یادآوری پرداخت‌های معلق روی {amount} دقیقه تنظیم شد.", reply_markup=admin_main_menu)
        await state.clear()
    except ValueError:
        await message.answer('لطفاً عدد معتبر و بزرگتر از صفر وارد کنید.')

@router.callback_query(F.data == "download_db_backup")
@admin_only
async def download_db_backup(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"database_backup_manual_{timestamp}.db")
    try:
        shutil.copy2(data_manager.db_path, backup_file)
        with open(backup_file, 'rb') as f:
            await bot.send_document(callback.from_user.id, BufferedInputFile(f.read(), filename=os.path.basename(backup_file)), caption="🗄 بکاپ دیتابیس")
        await safe_edit_callback_message(callback, "✅ بکاپ دیتابیس آماده و برای شما ارسال شد.", reply_markup=build_admin_settings_menu("reports"))
    except Exception as e:
        logger.error(f"Failed to create manual backup: {e}")
        await safe_edit_callback_message(callback, "❌ ساخت بکاپ دیتابیس ناموفق بود.", reply_markup=build_admin_settings_menu("reports"))

@router.callback_query(F.data == "v2ray_connection_menu")
@admin_only
async def v2ray_connection_menu(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    address = (await data_manager.get_setting('v2ray_server_address') or '').strip()
    token = (await data_manager.get_setting('v2ray_server_token') or '').strip()
    token_preview = (token[:4] + '...' + token[-4:]) if len(token) > 10 else ('تنظیم شده' if token else 'تنظیم نشده')
    rows = [
        [ikb_btn(text=f"🌐 آدرس/API: {'✅ تنظیم شده' if address else '⚪️ تنظیم نشده'}", callback_data="v2ray_set_address")],
        [ikb_btn(text=f"🔐 توکن اتصال: {token_preview}", callback_data="v2ray_set_token")],
        [ikb_btn(text="ℹ️ اتصال آزمایشی (به‌زودی)", callback_data="v2ray_test_connection")],
        [ikb_btn(text="🔙 بازگشت به تنظیمات", style=BUTTON_STYLE_DANGER, callback_data="back_to_settings")],
    ]
    await safe_edit_callback_message(callback, "🔌 تنظیمات اتصال به سرور V2Ray\nاین بخش برای اتصال آینده آماده شده است.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data == "v2ray_set_address")
@admin_only
async def v2ray_set_address_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    await callback.message.answer("آدرس پنل/API سرور V2Ray را وارد کنید.\nمثال: https://panel.example.com/api", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_v2ray_connection_address)

@router.message(AdminStates.waiting_for_v2ray_connection_address)
async def v2ray_set_address_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await state.clear()
        return
    value = (message.text or '').strip()
    if value == '-':
        await data_manager.set_setting('v2ray_server_address', '')
        await message.answer("✅ آدرس اتصال V2Ray حذف شد.", reply_markup=admin_main_menu)
        await state.clear()
        return
    if not re.match(r'^https?://', value):
        await message.answer("❌ آدرس معتبر نیست. باید با http:// یا https:// شروع شود.")
        return
    await data_manager.set_setting('v2ray_server_address', value)
    await message.answer("✅ آدرس اتصال V2Ray ذخیره شد.", reply_markup=admin_main_menu)
    await state.clear()

@router.callback_query(F.data == "v2ray_set_token")
@admin_only
async def v2ray_set_token_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    await callback.message.answer("توکن/API Key اتصال به سرور V2Ray را وارد کنید. برای حذف، خط تیره بفرستید.", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_v2ray_connection_token)

@router.message(AdminStates.waiting_for_v2ray_connection_token)
async def v2ray_set_token_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await state.clear()
        return
    value = (message.text or '').strip()
    if value == '-':
        await data_manager.set_setting('v2ray_server_token', '')
        await message.answer("✅ توکن اتصال V2Ray حذف شد.", reply_markup=admin_main_menu)
        await state.clear()
        return
    if len(value) < 6:
        await message.answer("❌ توکن وارد شده خیلی کوتاه است.")
        return
    await data_manager.set_setting('v2ray_server_token', value)
    await message.answer("✅ توکن اتصال V2Ray ذخیره شد.", reply_markup=admin_main_menu)
    await state.clear()

@router.callback_query(F.data == "v2ray_test_connection")
@admin_only
async def v2ray_test_connection(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    address = (await data_manager.get_setting('v2ray_server_address') or '').strip()
    token = (await data_manager.get_setting('v2ray_server_token') or '').strip()
    if not address or not token:
        await safe_edit_callback_message(callback, "⚠️ برای اتصال آینده ابتدا آدرس/API و توکن V2Ray را کامل تنظیم کنید.", reply_markup=build_admin_settings_menu("channel"))
        return
    await safe_edit_callback_message(callback, "ℹ️ اطلاعات اتصال V2Ray ذخیره شده است. تست اتصال واقعی بعداً همراه با اتصال به سرور فعال می‌شود.", reply_markup=build_admin_settings_menu("channel"))

@router.callback_query(F.data == "show_daily_report")
@admin_only
async def show_daily_report(callback: types.CallbackQuery, **kwargs):
    summary = await data_manager.get_sales_summary(days=1)
    threshold = int(await data_manager.get_setting('low_stock_threshold') or '5')
    low = await data_manager.get_low_stock_products(threshold)
    text = f"📈 **گزارش روزانه**\nخرید موفق: {summary['purchase_count']}\nفروش: {summary['total_sales']:,} تومان\nپرداخت ثبت‌شده: {summary['payment_count']}\nجمع مبالغ پرداختی: {summary['total_payment_amount']:,} تومان\nپرداخت معلق: {summary['pending_payments']}\nتیکت باز: {summary['open_tickets']}\nکاربر جدید: {summary['new_users']}\nمحصولات کم‌موجودی (<= {threshold}): {len(low)}"
    await callback.message.edit_text(text, parse_mode='Markdown')

@router.callback_query(F.data == "show_weekly_report")
@admin_only
async def show_weekly_report(callback: types.CallbackQuery, **kwargs):
    summary = await data_manager.get_sales_summary(days=7)
    threshold = int(await data_manager.get_setting('low_stock_threshold') or '5')
    low = await data_manager.get_low_stock_products(threshold)
    preview = '\n'.join([f"- {item['category_name']} / {item['product_name']} : {item['stock']}" for item in low[:10]]) or 'ندارد'
    text = f"🗓 **گزارش هفتگی**\nخرید موفق: {summary['purchase_count']}\nفروش: {summary['total_sales']:,} تومان\nپرداخت ثبت‌شده: {summary['payment_count']}\nجمع مبالغ پرداختی: {summary['total_payment_amount']:,} تومان\nپرداخت معلق: {summary['pending_payments']}\nتیکت باز: {summary['open_tickets']}\nکاربر جدید: {summary['new_users']}\nمحصولات کم‌موجودی (<= {threshold}): {len(low)}\n\n{preview}"
    await callback.message.edit_text(text, parse_mode='Markdown')

@router.callback_query(F.data == "set_mandatory_join_channel")
@admin_only
async def set_mandatory_join_channel_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_text("مرحله ۱ از ۲\nآیدی عددی کانال عضویت اجباری را وارد کنید.\nمثال: -1001234567890\nبرای حذف، خط تیره بفرستید.", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_mandatory_channel)

@router.message(AdminStates.waiting_for_mandatory_channel)
async def set_mandatory_join_channel_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or '').strip()
    if raw == '-':
        await data_manager.set_setting('mandatory_join_channel', '')
        await message.answer("✅ کانال عضویت اجباری حذف شد.", reply_markup=admin_main_menu)
        await state.clear()
        return
    if not re.fullmatch(r'-100\d{5,}', raw):
        await message.answer("❌ آیدی عددی کانال معتبر نیست. مثال صحیح: -1001234567890")
        return
    await state.update_data(mandatory_channel_chat_id=raw)
    await message.answer("مرحله ۲ از ۲\nیوزرنیم کانال را وارد کنید.\nمثال: @channelusername", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_mandatory_channel_username)

@router.message(AdminStates.waiting_for_mandatory_channel_username)
async def set_mandatory_join_channel_username_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await state.clear()
        return
    raw_username = (message.text or '').strip()
    if not re.fullmatch(r'@[A-Za-z0-9_]{5,}', raw_username):
        await message.answer("❌ یوزرنیم کانال معتبر نیست. مثال صحیح: @channelusername")
        return
    state_data = await state.get_data()
    chat_id = state_data.get('mandatory_channel_chat_id', '')
    parsed = parse_channel_value(f"{raw_username}|{chat_id}", require_username=True)
    await data_manager.set_setting('mandatory_join_channel', parsed['raw'])
    await message.answer(f"✅ کانال عضویت اجباری ذخیره شد:\nیوزرنیم: {parsed.get('username') or '-'}\nآیدی: {parsed.get('chat_id') or '-'}", reply_markup=admin_main_menu)
    await state.clear()

@router.message(F.text.in_(["📢 مدیریت کانال", "مدیریت کانال", "📣 مدیریت کانال"]))
async def open_channel_management(message: types.Message, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        return
    await message.answer("مدیریت کانال‌ها و آموزش‌ها:", reply_markup=build_education_admin_menu())

@router.callback_query(F.data == "set_education_channel")
@admin_only
async def set_education_channel_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_text("کانال آموزش را با یوزرنیم و آیدی عددی وارد کنید.\nفرمت صحیح: @channel|-1001234567890\nبرای حذف، خط تیره بفرستید.", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_education_channel)

@router.message(AdminStates.waiting_for_education_channel)
async def set_education_channel_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await state.clear()
        return
    try:
        parsed = parse_channel_value((message.text or '').strip(), require_username=True)
        if not parsed.get('chat_id'):
            raise ValueError('برای کانال آموزش وارد کردن همزمان یوزرنیم و آیدی عددی اجباری است.')
        await data_manager.set_setting('education_channel', parsed['raw'])
        await message.answer(f"✅ کانال آموزش ذخیره شد:\nیوزرنیم: {parsed.get('username')}\nآیدی: {parsed.get('chat_id')}", reply_markup=admin_main_menu)
        await state.clear()
    except ValueError as e:
        await message.answer(f"❌ {e}")

@router.callback_query(F.data == "set_usdt_wallet")
@admin_only
async def set_usdt_wallet_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    primary = await get_primary_usdt_network()
    buttons = []
    for key, label in USDT_NETWORKS:
        address = (await data_manager.get_setting(get_usdt_setting_key(key)) or '').strip()
        status = '✅' if address else '⚪️'
        primary_badge = '⭐️' if key == primary else ''
        buttons.append([ikb_btn(text=f"{status} {label} {primary_badge}", style=BUTTON_STYLE_PRIMARY, callback_data=f"set_usdt_wallet_{key}")])
    buttons.append([ikb_btn(text='🔙 بازگشت', callback_data='cancel')])
    await callback.message.edit_text("کیف پول‌های تتر را مدیریت کنید.\nشبکه دارای ⭐️، شبکه اصلی است.\nبرای ویرایش هر شبکه روی دکمه آن بزنید.", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("set_usdt_wallet_"))
@admin_only
async def set_usdt_wallet_network_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    network = (callback.data or '').split('set_usdt_wallet_', 1)[1].upper()
    if network not in USDT_NETWORK_LABELS:
        await callback.answer('شبکه نامعتبر است.', show_alert=True)
        return
    current_address = (await data_manager.get_setting(get_usdt_setting_key(network)) or '').strip()
    await state.update_data(usdt_wallet_network=network)
    msg = f"آدرس فعلی {USDT_NETWORK_LABELS[network]}: `{current_address or 'تنظیم نشده'}`\n\nآدرس جدید را وارد کنید. برای حذف، خط تیره بفرستید."
    await callback.message.edit_text(msg, parse_mode='Markdown', reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_usdt_wallet_address)

@router.message(AdminStates.waiting_for_usdt_wallet_address)
async def set_usdt_wallet_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await state.clear()
        return
    state_data = await state.get_data()
    network = (state_data.get('usdt_wallet_network') or await get_primary_usdt_network()).upper()
    address = (message.text or '').strip()
    if address == '-':
        address = ''
    await data_manager.set_setting(get_usdt_setting_key(network), address)
    if network == await get_primary_usdt_network():
        await data_manager.set_setting('usdt_wallet_address', address)
    status_text = f"✅ آدرس کیف پول {USDT_NETWORK_LABELS.get(network, network)} ذخیره شد." if address else f"✅ آدرس کیف پول {USDT_NETWORK_LABELS.get(network, network)} حذف شد."
    await message.answer(status_text, reply_markup=admin_main_menu)
    await state.clear()

@router.callback_query(F.data == "toggle_usdt_network")
@admin_only
async def toggle_usdt_network(callback: types.CallbackQuery, **kwargs):
    current = await get_primary_usdt_network()
    buttons = []
    for key, label in USDT_NETWORKS:
        marker = '⭐️ شبکه اصلی' if key == current else 'انتخاب به‌عنوان اصلی'
        buttons.append([ikb_btn(text=f"{label} - {marker}", style=BUTTON_STYLE_PRIMARY if key != current else BUTTON_STYLE_SUCCESS, callback_data=f"set_usdt_primary_{key}")])
    buttons.append([ikb_btn(text='❌ لغو', style=BUTTON_STYLE_DANGER, callback_data='cancel')])
    await callback.message.edit_text('شبکه اصلی USDT را انتخاب کنید:', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("set_usdt_primary_"))
@admin_only
async def set_usdt_primary_network(callback: types.CallbackQuery, **kwargs):
    network = (callback.data or '').split('set_usdt_primary_', 1)[1].upper()
    if network not in USDT_NETWORK_LABELS:
        await callback.answer('شبکه نامعتبر است.', show_alert=True)
        return
    address = (await data_manager.get_setting(get_usdt_setting_key(network)) or '').strip()
    await data_manager.set_setting('usdt_wallet_network', network)
    await data_manager.set_setting('usdt_wallet_address', address)
    await callback.message.edit_text(f"✅ شبکه اصلی USDT روی `{network}` تنظیم شد.", parse_mode='Markdown')

@router.callback_query(F.data == "show_bot_stats")
@admin_only
async def handle_bot_stats(callback: types.CallbackQuery, **kwargs):
    stats = await data_manager.get_total_stats()
    total_users = stats['total_users']
    rep_count = stats['rep_count']
    total_debt = stats['total_debt']
    total_sales = stats['total_sales']
    stats_text = (
        f"**آمار ربات:** 📊\n"
        f"**تعداد کل اعضا:** {total_users} 👥\n"
        f"**تعداد نمایندگان:** {rep_count} 🧑‍💻\n"
        f"**مجموع کل بدهکاری‌ها:** {total_debt:,} تومان 💸\n"
        f"**مجموع مبلغ کل فروش:** {total_sales:,} تومان 💰\n"
        f"**آمار فروش محصولات:** 📦\n"
    )
    for product_name, product_stats in stats['sales_stats'].items():
        stats_text += f"  - `{escape_markdown(product_name)}`: {product_stats['count']} فروش ({product_stats['total_price']:,} تومان)\n"
    if not stats['sales_stats']:
        stats_text += "  - تاکنون فروشی انجام نشده است. 😔"
    await callback.message.edit_text(stats_text, parse_mode="Markdown")

@router.callback_query(F.data == "back_to_main")
@admin_only
async def back_to_main_menu(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    try:
        await callback.message.edit_text("به منوی اصلی بازگشتید.")
    except Exception:
        pass
    await callback.message.answer("به منوی اصلی بازگشتید.", reply_markup=admin_main_menu)

@router.message(F.text.in_(["👥 مدیریت ادمین‌ها", "🛡️ مدیریت ادمین‌ها"]))
async def manage_admins(message: types.Message, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        return
    if message.from_user.id != ADMIN_ID:
        await message.answer("تنها ادمین اصلی می‌تواند ادمین‌های دیگر را مدیریت کند.")
        return
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="➕ افزودن ادمین", callback_data="add_admin")],
            [ikb_btn(text="➖ حذف ادمین", callback_data="remove_admin")],
            [ikb_btn(text="📋 لیست ادمین‌ها", callback_data="list_admins")],
            [ikb_btn(text="🔙 بازگشت", style=BUTTON_STYLE_PRIMARY, callback_data="back_to_main")]
        ]
    )
    await message.answer("مدیریت ادمین‌ها:", reply_markup=buttons)

@router.callback_query(F.data == "add_admin")
@admin_only
async def add_admin_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("تنها ادمین اصلی می‌تواند ادمین اضافه کند.", show_alert=True)
        return
    await callback.message.edit_text("لطفاً شناسه عددی کاربر مورد نظر را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_add_admin)

@router.message(AdminStates.waiting_for_add_admin)
async def add_admin_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id) or message.from_user.id != ADMIN_ID:
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    try:
        user_id = int(message.text.strip())
        user_info = await data_manager.get_user(user_id)
        if not user_info:
            await message.answer("کاربر مورد نظر یافت نشد.")
            await state.clear()
            return
        await data_manager.add_admin(user_id, user_info['full_name'], message.from_user.id)
        await message.answer(f"✅ کاربر {user_info['full_name']} به ادمین‌ها اضافه شد.")
    except ValueError:
        await message.answer("لطفاً یک عدد معتبر وارد کنید.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data == "remove_admin")
@admin_only
async def remove_admin_start(callback: types.CallbackQuery, **kwargs):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("تنها ادمین اصلی می‌تواند ادمین حذف کند.", show_alert=True)
        return
    admins = await data_manager.get_all_admins()
    buttons = []
    for admin in admins:
        if admin['user_id'] == ADMIN_ID:
            continue
        buttons.append([InlineKeyboardButton(text=admin['full_name'], callback_data=f"remove_admin_{admin['user_id']}")])
    buttons.append([ikb_btn(text="🔙 بازگشت", style=BUTTON_STYLE_PRIMARY, callback_data="back_to_main")])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("لطفاً ادمین مورد نظر برای حذف را انتخاب کنید:", reply_markup=inline_kb)

@router.callback_query(F.data.startswith("remove_admin_"))
@admin_only
async def remove_admin_confirm(callback: types.CallbackQuery, **kwargs):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("تنها ادمین اصلی می‌تواند ادمین حذف کند.", show_alert=True)
        return
    user_id = int(callback.data.split('_')[-1])
    success = await data_manager.remove_admin(user_id)
    if success:
        await callback.message.edit_text(f"✅ ادمین با شناسه {user_id} حذف شد.")
    else:
        await callback.message.edit_text("❌ حذف ادمین ممکن نیست (احتمالاً ادمین اصلی است).")

@router.callback_query(F.data == "list_admins")
@admin_only
async def list_admins(callback: types.CallbackQuery, **kwargs):
    admins = await data_manager.get_all_admins()
    if not admins:
        text = "هیچ ادمینی وجود ندارد."
    else:
        text = "📋 لیست ادمین‌ها:\n"
        for admin in admins:
            text += f"• {admin['full_name']} (ID: {admin['user_id']})"
            if admin['is_main']:
                text += " - اصلی"
            text += "\n"
    await callback.message.edit_text(text, reply_markup=back_to_admin_inline)

@router.message(F.text.in_(["💳 مدیریت حساب‌های بانکی", "🏦 حساب‌های بانکی"]))
async def manage_bank_accounts(message: types.Message, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        return
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="➕ افزودن حساب جدید", callback_data="add_bank_account")],
            [ikb_btn(text="📋 لیست حساب‌ها", callback_data="list_bank_accounts")],
            [ikb_btn(text="₮ مدیریت کیف پول‌های تتر", callback_data="set_usdt_wallet")],
            [ikb_btn(text="🔙 بازگشت", style=BUTTON_STYLE_PRIMARY, callback_data="back_to_main")]
        ]
    )
    await message.answer("مدیریت حساب‌های بانکی:", reply_markup=buttons)

@router.callback_query(F.data == "add_bank_account")
@admin_only
async def add_bank_account_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_text("لطفاً شماره حساب را وارد کنید:")
    await state.set_state(AdminStates.waiting_for_account_number)

@router.message(AdminStates.waiting_for_account_number)
async def add_bank_account_number(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    account_number = message.text.strip()
    await state.update_data(account_number=account_number)
    await message.answer("لطفاً نام صاحب حساب را وارد کنید:")
    await state.set_state(AdminStates.waiting_for_account_owner_name)

@router.message(AdminStates.waiting_for_account_owner_name)
async def add_bank_account_owner(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    owner = message.text.strip()
    state_data = await state.get_data()
    account_number = state_data['account_number']
    await data_manager.add_bank_account(account_number, owner)
    await message.answer(f"✅ حساب بانکی با شماره {account_number} و نام {owner} اضافه شد.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data == "list_bank_accounts")
@admin_only
async def list_bank_accounts(callback: types.CallbackQuery, **kwargs):
    accounts = await data_manager.get_bank_accounts(active_only=False)
    if not accounts:
        await callback.message.edit_text("هیچ حسابی ثبت نشده است.")
    else:
        text = "📋 لیست حساب‌های بانکی:\n"
        for acc in accounts:
            text += f"🔹 {acc['account_owner']} - {acc['account_number']}"
            if acc['is_default']:
                text += " (پیش‌فرض)"
            text += "\n"
        buttons = []
        for acc in accounts:
            buttons.append([InlineKeyboardButton(text=f"⚙️ {acc['account_owner']}", callback_data=f"manage_bank_account_{acc['id']}")])
        buttons.append([ikb_btn(text="🔙 بازگشت", style=BUTTON_STYLE_PRIMARY, callback_data="back_to_main")])
        inline_kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text, reply_markup=inline_kb)

@router.callback_query(F.data.startswith("manage_bank_account_"))
@admin_only
async def manage_bank_account_detail(callback: types.CallbackQuery, **kwargs):
    account_id = int(callback.data.split('_')[-1])
    accounts = await data_manager.get_bank_accounts(active_only=False)
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        await callback.answer("حساب یافت نشد.")
        return
    btn_list = []
    if not account['is_default']:
        btn_list.append([ikb_btn(text="⭐ تنظیم به عنوان پیش‌فرض", callback_data=f"set_default_bank_{account_id}")])
    btn_list.append([ikb_btn(text="❌ حذف", callback_data=f"delete_bank_account_{account_id}")])
    btn_list.append([ikb_btn(text="🔙 بازگشت", callback_data="list_bank_accounts")])
    btn_list = [btn for btn in btn_list if btn]
    buttons = InlineKeyboardMarkup(inline_keyboard=btn_list)
    await callback.message.edit_text(f"مدیریت حساب:\n{account['account_owner']}\n{account['account_number']}", reply_markup=buttons)

@router.callback_query(F.data.startswith("set_default_bank_"))
@admin_only
async def set_default_bank_account(callback: types.CallbackQuery, **kwargs):
    account_id = int(callback.data.split('_')[-1])
    await data_manager.set_default_bank_account(account_id)
    await callback.message.edit_text("✅ حساب به عنوان پیش‌فرض تنظیم شد.")

@router.callback_query(F.data.startswith("delete_bank_account_"))
@admin_only
async def delete_bank_account(callback: types.CallbackQuery, **kwargs):
    account_id = int(callback.data.split('_')[-1])
    accounts = await data_manager.get_bank_accounts(active_only=False)
    account = next((a for a in accounts if a['id'] == account_id), None)
    await data_manager.delete_bank_account(account_id)
    await callback.message.edit_text("✅ حساب حذف شد.")

# =================================================================
