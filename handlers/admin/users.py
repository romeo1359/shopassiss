from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app import bot, data_manager
from config import logger
from states.admin_states import AdminStates
from keyboards.inline import cancel_only_button, ikb_btn
from keyboards.reply import admin_main_menu
from utils.formatters import escape_markdown, format_persian_date, get_payment_method_label
from utils.telegram_utils import admin_only, refresh_user_role_menu, safe_callback_answer
router = Router()


@router.message((F.text == "🧑‍💻 مدیریت کاربران") | (F.text == "👥 مدیریت کاربران"))
async def manage_users(message: types.Message, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        return
    inline_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="🔎 جستجوی کاربر", callback_data="search_user_start")],
            [ikb_btn(text="🧑‍💻 نمایش نمایندگان", callback_data="show_reps")],
            [ikb_btn(text="👤 نمایش کاربران عادی", callback_data="show_normal_users")],
            [ikb_btn(text="🚫 نمایش کاربران اخراجی", callback_data="show_banned_users")],
            [ikb_btn(text="🆕 ثبت‌نام‌های منتظر", callback_data="show_pending_registrations")],
            [ikb_btn(text="💸 نمایش بدهکاران", callback_data="show_debtors_from_users")],
            [ikb_btn(text="🌳 گزارش سیستم معرفی", callback_data="show_referral_dashboard")],
                    ]
    )
    await message.answer("پنل مدیریت کاربران: 🧑‍💻", reply_markup=inline_buttons)

async def show_debtors_list(message: types.Message, debtors: list, title: str):
    buttons = []
    for user_info in debtors[:20]:
        user_id = user_info['user_id']
        debt_amount = user_info.get('debt', 0)
        full_name = user_info.get('full_name', 'ناشناس')
        button_text = f"{full_name} - {debt_amount:,} تومان"
        if len(button_text) > 40:
            button_text = button_text[:37] + "..."
        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"manage_user_{user_id}"
            )
        ])
    if len(debtors) > 20:
        buttons.append([ikb_btn(text="📄 بیشتر", callback_data="show_more_debtors")])
    buttons.append([
        ikb_btn(text="🔙 بازگشت به مدیریت کاربران", callback_data="back_to_user_management")
    ])
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    total_debt = sum(user_info.get('debt', 0) for user_info in debtors)
    header_text = (
        f"<b>{title}</b>\n"
        f"<i>تعداد: {len(debtors)} نماینده</i>\n"
        f"<code>مجموع بدهی: {total_debt:,} تومان</code>\n"
        f"برای مشاهده جزئیات و مدیریت هر نماینده، روی نام آن کلیک کنید:"
    )
    await message.answer(header_text, parse_mode="HTML", reply_markup=inline_keyboard)


@router.callback_query(F.data == "show_pending_registrations")
@admin_only
async def show_pending_registrations(callback: types.CallbackQuery, **kwargs):
    pending = await data_manager.get_pending_users()
    if not pending:
        await callback.message.edit_text("هیچ ثبت‌نام منتظری وجود ندارد.")
        return
    buttons = [[InlineKeyboardButton(text=f"{u['full_name']} ({u['user_id']})", callback_data=f"manage_pending_user_{u['user_id']}")] for u in pending[:30]]
    buttons.append([ikb_btn(text="🔙 بازگشت به مدیریت کاربران", callback_data="back_to_user_management")])
    await callback.message.edit_text("ثبت‌نام‌های منتظر:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("manage_pending_user_"))
@admin_only
async def manage_pending_user(callback: types.CallbackQuery, **kwargs):
    target_user_id = int(callback.data.rsplit("_", 1)[-1])
    user = await data_manager.get_user(target_user_id)
    if not user:
        await callback.message.edit_text("کاربر یافت نشد.")
        return
    ref_info = "ندارد"
    if user.get('referred_by'):
        ref_user = await data_manager.get_user(user.get('referred_by'))
        ref_info = f"{ref_user.get('full_name', 'ناشناس')} ({user.get('referred_by')})" if ref_user else str(user.get('referred_by'))
    text = f"نام: {user.get('full_name')}\nشناسه: {target_user_id}\nموبایل: {user.get('phone_number')}\nمعرف: {ref_info}"
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        ikb_btn(text="✅ تأیید", callback_data=f"approve_registration_{target_user_id}"),
        ikb_btn(text="❌ رد", callback_data=f"reject_registration_{target_user_id}")
    ]])
    await callback.message.edit_text(text, reply_markup=markup)

@router.callback_query(F.data == "show_debtors_from_users")
@admin_only
async def show_debtors_from_users(callback: types.CallbackQuery, **kwargs):
    debtors = await data_manager.get_all_debtors()
    if not debtors:
        await callback.message.edit_text("هیچ نماینده‌ای بدهی ندارد. ✅")
        return
    await show_debtors_list(callback.message, debtors, "لیست نمایندگان بدهکار 💸")

@router.callback_query(F.data == "search_user_start")
@admin_only
async def search_user_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_text("لطفاً نام، نام خانوادگی یا شماره موبایل کاربر را وارد کنید: 🔎", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_user_search)

@router.message(AdminStates.waiting_for_user_search)
async def perform_user_search(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    query = message.text.strip().lower()
    found_users = await data_manager.search_users(query)
    if not found_users:
        await message.answer("کاربری یافت نشد. 😔", reply_markup=admin_main_menu)
    else:
        buttons = []
        for user_info in found_users[:20]:
            buttons.append([
                InlineKeyboardButton(
                    text=f"{user_info.get('full_name', 'ناشناس')} (ID: {user_info['user_id']})",
                    callback_data=f"manage_user_{user_info['user_id']}"
                )
            ])
        if len(found_users) > 20:
            buttons.append([ikb_btn(text="📄 بیشتر", callback_data=f"search_more_{query}|1")])
        buttons.append([ikb_btn(text="🔙 بازگشت", callback_data="back_to_user_management")])
        await message.answer("نتایج جستجو: 🔍", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.clear()

@router.callback_query(F.data.startswith("manage_user_"))
@admin_only
async def manage_user_profile(callback: types.CallbackQuery, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    user_info = await data_manager.get_user(user_id)
    if not user_info:
        await callback.message.edit_text("کاربر مورد نظر یافت نشد. 😔")
        return
    user_purchases = await data_manager.get_user_purchases(user_id)
    purchase_count = len(user_purchases)
    all_tickets = await data_manager.get_all_support_tickets()
    support_ticket_count = len([t for t in all_tickets if t['user_id'] == user_id])
    is_rep_status = "✅ نماینده" if user_info.get('is_rep') else "❌ عادی"
    reg_date = format_persian_date(user_info.get('registration_date', 'نامشخص'))
    referrer_admin_text = "ندارد"
    if user_info.get('referred_by'):
        ref_user = await data_manager.get_user(user_info.get('referred_by'))
        referrer_admin_text = f"{ref_user.get('full_name', 'ناشناس')} ({user_info.get('referred_by')})" if ref_user else str(user_info.get('referred_by'))
    profile_text = (
        f"**جزئیات کاربر:** 👤\n"
        f"**نام و نام خانوادگی:** {escape_markdown(user_info.get('full_name', 'ناشناس'))}\n"
        f"**نام فروشگاه:** {escape_markdown(user_info.get('store_name', 'نامشخص'))}\n"
        f"**شماره موبایل:** `{escape_markdown(user_info.get('phone_number', 'ثبت نشده'))}`\n"
        f"**شناسه (ID):** `{user_id}`\n"
        f"**کد معرف:** `{user_info.get('referral_code') or '---'}`\n"
        f"**معرف:** {escape_markdown(referrer_admin_text)}\n"
        f"**وضعیت نمایندگی:** {is_rep_status}\n"
        f"**درصد تخفیف:** {user_info.get('discount_percentage', 0)}%\n"
        f"**موجودی کیف پول:** {user_info.get('balance', 0):,} تومان\n"
        f"**بدهکاری:** {user_info.get('debt', 0):,} تومان\n"
        f"**سقف اعتبار نسیه:** {user_info.get('credit_limit', 0):,} تومان\n"
        f"**تعداد خرید:** {purchase_count}\n"
        f"**تعداد پیام پشتیبانی:** {support_ticket_count}\n"
        f"**تاریخ ثبت نام:** {reg_date}"
    )
    buttons = []
    if user_info.get('banned'):
        buttons.append([ikb_btn(text="✅ بازگرداندن از اخراج", callback_data=f"unban_user_{user_id}")])
    else:
        if user_info.get('is_rep'):
            buttons.append([
                ikb_btn(text="تغییر درصد تخفیف", callback_data=f"change_discount_{user_id}"),
                ikb_btn(text="تغییر سقف اعتبار نسیه", callback_data=f"change_credit_limit_{user_id}")
            ])
            buttons.append([ikb_btn(text="حذف از نمایندگی", callback_data=f"remove_rep_{user_id}")])
        else:
            buttons.append([ikb_btn(text="ثبت به عنوان نماینده 🧑‍💻", callback_data=f"promote_to_rep_{user_id}")])
        buttons.append([
            ikb_btn(text="💰 افزایش موجودی", callback_data=f"topup_wallet_admin_{user_id}"),
            ikb_btn(text="💸 کاهش موجودی", callback_data=f"deduct_wallet_admin_{user_id}")
        ])
        buttons.append([
            ikb_btn(text="📈 افزایش بدهی", callback_data=f"increase_debt_admin_{user_id}"),
            ikb_btn(text="📉 کاهش بدهی", callback_data=f"decrease_debt_admin_{user_id}")
        ])
        buttons.append([ikb_btn(text="📩 ارسال پیام", callback_data=f"send_message_to_user_{user_id}")])
        buttons.append([ikb_btn(text="📜 مشاهده سابقه خرید", callback_data=f"view_purchase_history_{user_id}")])
        buttons.append([ikb_btn(text="🚫 اخراج از ربات", callback_data=f"ban_user_{user_id}")])
    buttons.append([ikb_btn(text="🔙 بازگشت به مدیریت کاربران", callback_data="back_to_user_management")])
    inline_buttons = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(profile_text, reply_markup=inline_buttons, parse_mode="Markdown")

@router.callback_query(F.data == "show_reps")
@admin_only
async def show_representatives(callback: types.CallbackQuery, **kwargs):
    reps = await data_manager.get_all_reps()
    if not reps:
        await callback.message.edit_text("هیچ نماینده‌ای ثبت نشده است. 😔")
        return
    buttons = []
    for user_info in reps[:20]:
        user_id = user_info['user_id']
        discount = user_info.get('discount_percentage', 0)
        full_name = user_info.get('full_name', 'ناشناس')
        button_text = f"{full_name} - {discount}% تخفیف"
        if len(button_text) > 40:
            button_text = button_text[:37] + "..."
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"manage_user_{user_id}")])
    if len(reps) > 20:
        buttons.append([ikb_btn(text="📄 بیشتر", callback_data="show_more_reps")])
    buttons.append([ikb_btn(text="🔙 بازگشت به مدیریت کاربران", callback_data="back_to_user_management")])
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    total_reps = len(reps)
    total_debt = sum(user_info.get('debt', 0) for user_info in reps)
    header_text = (
        f"<b>لیست نمایندگان</b> 🧑‍💻\n"
        f"<i>تعداد: {total_reps} نماینده</i>\n"
        f"<code>مجموع بدهی: {total_debt:,} تومان</code>\n"
        f"برای مشاهده جزئیات و مدیریت هر نماینده، روی نام آن کلیک کنید:"
    )
    await callback.message.edit_text(header_text, parse_mode="HTML", reply_markup=inline_keyboard)

@router.callback_query(F.data == "show_normal_users")
@admin_only
async def show_normal_users(callback: types.CallbackQuery, **kwargs):
    all_users = await data_manager.get_all_users()
    normal_users = [user for user in all_users if not user.get('is_rep', False) and not user.get('banned', False) and True]
    if not normal_users:
        await callback.message.edit_text("هیچ کاربر عادی ثبت نشده است. 😔")
        return
    buttons = []
    for user_info in normal_users[:20]:
        user_id = user_info['user_id']
        full_name = user_info.get('full_name', 'ناشناس')
        button_text = f"{full_name}"
        if len(button_text) > 40:
            button_text = button_text[:37] + "..."
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"manage_user_{user_id}")])
    if len(normal_users) > 20:
        buttons.append([ikb_btn(text="📄 بیشتر", callback_data="show_more_normal_users")])
    buttons.append([ikb_btn(text="🔙 بازگشت به مدیریت کاربران", callback_data="back_to_user_management")])
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    header_text = (
        f"<b>لیست کاربران عادی</b> 👤\n"
        f"<i>تعداد: {len(normal_users)} کاربر</i>\n"
        f"برای مشاهده جزئیات و مدیریت هر کاربر، روی نام آن کلیک کنید:"
    )
    await callback.message.edit_text(header_text, parse_mode="HTML", reply_markup=inline_keyboard)

@router.callback_query(F.data == "show_banned_users")
@admin_only
async def show_banned_users(callback: types.CallbackQuery, **kwargs):
    banned_users = await data_manager.get_all_banned_users()
    if not banned_users:
        await callback.message.edit_text("هیچ کاربر اخراجی وجود ندارد. ✅")
        return
    buttons = []
    for user_info in banned_users[:20]:
        user_id = user_info['user_id']
        full_name = user_info.get('full_name', 'ناشناس')
        button_text = f"{full_name}"
        if len(button_text) > 40:
            button_text = button_text[:37] + "..."
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"manage_user_{user_id}")])
    if len(banned_users) > 20:
        buttons.append([ikb_btn(text="📄 بیشتر", callback_data="show_more_banned")])
    buttons.append([ikb_btn(text="🔙 بازگشت به مدیریت کاربران", callback_data="back_to_user_management")])
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    header_text = (
        f"<b>لیست کاربران اخراجی</b> 🚫\n"
        f"<i>تعداد: {len(banned_users)} کاربر</i>\n"
        f"برای مشاهده جزئیات و مدیریت هر کاربر، روی نام آن کلیک کنید:"
    )
    await callback.message.edit_text(header_text, parse_mode="HTML", reply_markup=inline_keyboard)


async def _build_user_list_markup(items: list, callback_builder, title: str, empty_text: str, back_callback: str, page: int = 0, item_label_builder=None, page_size: int = 20):
    if not items:
        return empty_text, None
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    chunk = items[start:start + page_size]
    buttons = []
    for item in chunk:
        label = item_label_builder(item) if item_label_builder else str(item)
        if len(label) > 40:
            label = label[:37] + '...'
        buttons.append([InlineKeyboardButton(text=label, callback_data=callback_builder(item))])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text='⏪ قبلی', callback_data=f'{back_callback}_{page-1}'))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text='⏩ بعدی', callback_data=f'{back_callback}_{page+1}'))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text='🔙 بازگشت به مدیریت کاربران', callback_data='back_to_user_management')])
    return f"{title}\n\nصفحه {page + 1} از {total_pages}", InlineKeyboardMarkup(inline_keyboard=buttons)



@router.callback_query(F.data.startswith('show_more_reps'))
@admin_only
async def show_more_reps(callback: types.CallbackQuery, **kwargs):
    page = int(callback.data.rsplit('_', 1)[-1]) if callback.data.rsplit('_', 1)[-1].isdigit() else 1
    reps = await data_manager.get_all_reps()
    text, markup = await _build_user_list_markup(
        reps,
        lambda item: f"manage_user_{item['user_id']}",
        '🧑‍💻 لیست نمایندگان',
        'هیچ نماینده‌ای ثبت نشده است. 😔',
        'show_more_reps',
        page=page,
        item_label_builder=lambda item: f"🧑‍💻 {item.get('full_name', 'ناشناس')} - {item.get('discount_percentage', 0)}% تخفیف"
    )
    await callback.message.edit_text(text, reply_markup=markup)

@router.callback_query(F.data.startswith('show_more_debtors'))
@admin_only
async def show_more_debtors(callback: types.CallbackQuery, **kwargs):
    page = int(callback.data.rsplit('_', 1)[-1]) if callback.data.rsplit('_', 1)[-1].isdigit() else 1
    debtors = await data_manager.get_all_debtors()
    text, markup = await _build_user_list_markup(
        debtors,
        lambda item: f"manage_user_{item['user_id']}",
        '💸 لیست نمایندگان بدهکار',
        'هیچ نماینده‌ای بدهکار نیست. ✅',
        'show_more_debtors',
        page=page,
        item_label_builder=lambda item: f"💸 {item.get('full_name', 'ناشناس')} - {item.get('debt', 0):,} تومان"
    )
    await callback.message.edit_text(text, reply_markup=markup)

@router.callback_query(F.data.startswith('show_more_financial'))
@admin_only
async def show_more_financial(callback: types.CallbackQuery, **kwargs):
    page = int(callback.data.rsplit('_', 1)[-1]) if callback.data.rsplit('_', 1)[-1].isdigit() else 1
    admins = []
    text, markup = await _build_user_list_markup(
        admins,
        lambda item: f"manage_user_{item['user_id']}",
        '💰 لیست ادمین',
        'هیچ ادمین ثبت نشده است. 😔',
        'show_more_financial',
        page=page,
        item_label_builder=lambda item: f"💰 {item.get('full_name', 'ناشناس')}"
    )
    await callback.message.edit_text(text, reply_markup=markup)

@router.callback_query(F.data.startswith('show_more_normal_users'))
@admin_only
async def show_more_normal_users(callback: types.CallbackQuery, **kwargs):
    page = int(callback.data.rsplit('_', 1)[-1]) if callback.data.rsplit('_', 1)[-1].isdigit() else 1
    all_users = await data_manager.get_all_users()
    users = [u for u in all_users if not u.get('is_rep', False) and not u.get('banned', False) and not u.get('is_financial_admin', False)]
    text, markup = await _build_user_list_markup(
        users,
        lambda item: f"manage_user_{item['user_id']}",
        '👤 لیست کاربران عادی',
        'هیچ کاربر عادی ثبت نشده است. 😔',
        'show_more_normal_users',
        page=page,
        item_label_builder=lambda item: f"👤 {item.get('full_name', 'ناشناس')}"
    )
    await callback.message.edit_text(text, reply_markup=markup)

@router.callback_query(F.data.startswith('show_more_banned'))
@admin_only
async def show_more_banned(callback: types.CallbackQuery, **kwargs):
    page = int(callback.data.rsplit('_', 1)[-1]) if callback.data.rsplit('_', 1)[-1].isdigit() else 1
    users = await data_manager.get_all_banned_users()
    text, markup = await _build_user_list_markup(
        users,
        lambda item: f"manage_user_{item['user_id']}",
        '🚫 لیست کاربران اخراجی',
        'هیچ کاربر اخراجی وجود ندارد. ✅',
        'show_more_banned',
        page=page,
        item_label_builder=lambda item: f"🚫 {item.get('full_name', 'ناشناس')}"
    )
    await callback.message.edit_text(text, reply_markup=markup)

@router.callback_query(F.data.startswith('search_more_'))
@admin_only
async def search_more_results(callback: types.CallbackQuery, **kwargs):
    payload = callback.data[len('search_more_'):]
    page = 1
    query = payload
    if '|' in payload:
        query, page_raw = payload.rsplit('|', 1)
        if page_raw.isdigit():
            page = int(page_raw)
    found_users = await data_manager.search_users(query)
    if not found_users:
        await callback.message.edit_text('کاربری یافت نشد. 😔')
        return
    page_size = 20
    total_pages = max(1, (len(found_users) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    chunk = found_users[start:start + page_size]
    buttons = []
    for user_info in chunk:
        buttons.append([InlineKeyboardButton(text=f"👤 {user_info.get('full_name', 'ناشناس')} ({user_info['user_id']})", callback_data=f"manage_user_{user_info['user_id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text='⏪ قبلی', callback_data=f'search_more_{query}|{page-1}'))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text='⏩ بعدی', callback_data=f'search_more_{query}|{page+1}'))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text='🔙 بازگشت به مدیریت کاربران', callback_data='back_to_user_management')])
    await callback.message.edit_text(f'🔎 نتایج جستجو برای: {query}\n\nصفحه {page + 1} از {total_pages}', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))



@router.callback_query(F.data.in_(['set_credit_limit_500000', 'set_credit_limit_1000000', 'set_credit_limit_2000000', 'set_credit_limit_5000000']))
@admin_only
async def set_credit_limit_quick(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    value = int(callback.data.rsplit('_', 1)[-1])
    state_data = await state.get_data()
    user_id = state_data.get('target_user_id')
    if not user_id:
        await callback.message.edit_text('ابتدا کاربر موردنظر را انتخاب کنید.')
        return
    await data_manager.update_user_credit_limit(user_id, value)
    await callback.message.edit_text(f'✅ سقف اعتبار کاربر {user_id} روی {value:,} تومان تنظیم شد.')
    try:
        await bot.send_message(user_id, f'✅ سقف اعتبار نسیه شما روی {value:,} تومان تنظیم شد.')
    except Exception:
        pass
    await state.clear()
@router.callback_query(F.data == "back_to_user_management")
@admin_only
async def back_to_user_management(callback: types.CallbackQuery, **kwargs):
    inline_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="🔎 جستجوی کاربر", callback_data="search_user_start")],
            [ikb_btn(text="🧑‍💻 نمایش نمایندگان", callback_data="show_reps")],
            [ikb_btn(text="👤 نمایش کاربران عادی", callback_data="show_normal_users")],
            [ikb_btn(text="🚫 نمایش کاربران اخراجی", callback_data="show_banned_users")],
            [ikb_btn(text="🆕 ثبت‌نام‌های منتظر", callback_data="show_pending_registrations")],
            [ikb_btn(text="💸 نمایش بدهکاران", callback_data="show_debtors_from_users")],
            [ikb_btn(text="🌳 گزارش سیستم معرفی", callback_data="show_referral_dashboard")],
                    ]
    )
    await callback.message.edit_text("پنل مدیریت کاربران: 🧑‍💻", reply_markup=inline_buttons)

@router.callback_query(F.data.startswith("promote_to_rep_"))
@admin_only
async def promote_to_representative(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text(
        "لطفاً درصد تخفیف نماینده جدید را وارد کنید (عدد بین 0 تا 100):",
        reply_markup=cancel_only_button
    )
    await state.set_state(AdminStates.waiting_for_rep_discount)

@router.message(AdminStates.waiting_for_rep_discount)
async def set_rep_discount_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    try:
        discount = int(message.text)
        if discount < 0 or discount > 100:
            await message.answer("لطفاً عددی بین 0 تا 100 وارد کنید.")
            return
        state_data = await state.get_data()
        user_id = state_data['target_user_id']
        await data_manager.update_user_rep_status(user_id, True, discount)
        await refresh_user_role_menu(user_id, f"✅ نقش شما به نماینده تغییر کرد.\nدرصد تخفیف شما: {discount}%")
        await message.answer(f"کاربر با شناسه {user_id} به نماینده ارتقا یافت.")
    except ValueError:
        await message.answer("لطفاً عدد معتبر وارد کنید.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data.startswith("remove_rep_"))
@admin_only
async def remove_representative(callback: types.CallbackQuery, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    await data_manager.update_user_rep_status(user_id, False, 0)
    await data_manager.update_user_credit_limit(user_id, 0)
    await callback.message.edit_text(f"کاربر با شناسه {user_id} از نمایندگی حذف شد. ❌")
    try:
        await refresh_user_role_menu(user_id, "❌ نقش نمایندگی شما برداشته شد و منوی جدید اعمال شد.")
    except:
        pass

@router.callback_query(F.data.startswith("promote_financial_"))
@admin_only
async def promote_financial_admin(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback, "این قابلیت از پروژه حذف شده است.", show_alert=True)

@router.callback_query(F.data.startswith("remove_financial_"))
@admin_only
async def remove_financial_admin(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback, "این قابلیت از پروژه حذف شده است.", show_alert=True)

@router.callback_query(F.data.startswith("change_discount_"))
@admin_only
async def change_discount_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text("لطفاً درصد تخفیف جدید را وارد کنید (0-100):", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_new_user_discount)

@router.message(AdminStates.waiting_for_new_user_discount)
async def change_discount_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    try:
        discount = int(message.text)
        if discount < 0 or discount > 100:
            await message.answer("لطفاً عددی بین 0 تا 100 وارد کنید.")
            return
        state_data = await state.get_data()
        user_id = state_data['target_user_id']
        user_info = await data_manager.get_user(user_id)
        if user_info:
            await data_manager.update_user(user_id, discount_percentage=discount)
            await bot.send_message(user_id, f"✅ درصد تخفیف شما به {discount}% تغییر یافت.")
            await message.answer(f"درصد تخفیف کاربر {user_id} به {discount}% تغییر یافت.")
        else:
            await message.answer("کاربر یافت نشد.")
    except ValueError:
        await message.answer("لطفاً عدد معتبر وارد کنید.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data.startswith("change_credit_limit_"))
@admin_only
async def change_credit_limit_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text("لطفاً سقف اعتبار نسیه جدید را به تومان وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_credit_topup_amount_admin)

@router.message(AdminStates.waiting_for_credit_topup_amount_admin)
async def change_credit_limit_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    try:
        limit = int(message.text)
        if limit < 0:
            await message.answer("لطفاً عدد مثبت وارد کنید.")
            return
        state_data = await state.get_data()
        user_id = state_data['target_user_id']
        await data_manager.update_user_credit_limit(user_id, limit)
        await bot.send_message(user_id, f"✅ سقف اعتبار نسیه شما به {limit:,} تومان تغییر یافت.")
        await message.answer(f"سقف اعتبار نسیه کاربر {user_id} به {limit:,} تومان تغییر یافت.")
    except ValueError:
        await message.answer("لطفاً عدد معتبر وارد کنید.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data.startswith("ban_user_"))
@admin_only
async def ban_user(callback: types.CallbackQuery, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    await data_manager.update_user_banned_status(user_id, True)
    await callback.message.edit_text(f"کاربر با شناسه {user_id} اخراج شد. 🚫")
    try:
        await bot.send_message(user_id, "⛔ شما از استفاده از ربات محروم شده‌اید.")
    except:
        pass

@router.callback_query(F.data.startswith("unban_user_"))
@admin_only
async def unban_user(callback: types.CallbackQuery, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    await data_manager.update_user_banned_status(user_id, False)
    await callback.message.edit_text(f"کاربر با شناسه {user_id} بازگردانده شد. ✅")
    try:
        await bot.send_message(user_id, "✅ دسترسی شما به ربات بازگردانده شد.")
    except:
        pass

@router.callback_query(F.data.startswith("topup_wallet_admin_"))
@admin_only
async def topup_wallet_admin_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text("مبلغ افزایش موجودی را به تومان وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_wallet_topup_amount)

@router.message(AdminStates.waiting_for_wallet_topup_amount)
async def topup_wallet_admin_amount(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    try:
        amount = int(message.text)
        state_data = await state.get_data()
        user_id = state_data['target_user_id']
        await data_manager.update_user_balance(user_id, amount, operation="add")
        await bot.send_message(user_id, f"✅ موجودی کیف پول شما به مبلغ {amount:,} تومان افزایش یافت.")
        await message.answer(f"موجودی کاربر {user_id} با موفقیت افزایش یافت.")
    except ValueError:
        await message.answer("لطفاً عدد معتبر وارد کنید.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data.startswith("deduct_wallet_admin_"))
@admin_only
async def deduct_wallet_admin_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text("مبلغ کاهش موجودی را به تومان وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_wallet_deduct_amount)

@router.message(AdminStates.waiting_for_wallet_deduct_amount)
async def deduct_wallet_admin_amount(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    try:
        amount = int(message.text)
        state_data = await state.get_data()
        user_id = state_data['target_user_id']
        user_info = await data_manager.get_user(user_id)
        current_balance = user_info.get('balance', 0)
        if amount > current_balance:
            await message.answer(f"موجودی کاربر فقط {current_balance:,} تومان است.")
        else:
            await data_manager.update_user_balance(user_id, amount, operation="subtract")
            await bot.send_message(user_id, f"⚠️ از موجودی کیف پول شما {amount:,} تومان کسر شد.")
            await message.answer(f"موجودی کاربر {user_id} با موفقیت کاهش یافت.")
    except ValueError:
        await message.answer("لطفاً عدد معتبر وارد کنید.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data.startswith("increase_debt_admin_"))
@admin_only
async def increase_debt_admin_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text("مبلغ افزایش بدهی را به تومان وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_debt_increase_amount)

@router.message(AdminStates.waiting_for_debt_increase_amount)
async def increase_debt_admin_amount(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    try:
        amount = int(message.text)
        state_data = await state.get_data()
        user_id = state_data['target_user_id']
        await data_manager.update_user_debt(user_id, amount, operation="add")
        await bot.send_message(user_id, f"⚠️ بدهی شما به مبلغ {amount:,} تومان افزایش یافت.")
        await message.answer(f"بدهی کاربر {user_id} با موفقیت افزایش یافت.")
    except ValueError:
        await message.answer("لطفاً عدد معتبر وارد کنید.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data.startswith("decrease_debt_admin_"))
@admin_only
async def decrease_debt_admin_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text("مبلغ کاهش بدهی را به تومان وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_debt_decrease_amount)

@router.message(AdminStates.waiting_for_debt_decrease_amount)
async def decrease_debt_admin_amount(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    try:
        amount = int(message.text)
        state_data = await state.get_data()
        user_id = state_data['target_user_id']
        user_info = await data_manager.get_user(user_id)
        current_debt = user_info.get('debt', 0)
        if amount > current_debt:
            await message.answer(f"بدهی فعلی کاربر فقط {current_debt:,} تومان است.")
        else:
            await data_manager.update_user_debt(user_id, amount, operation="subtract")
            await bot.send_message(user_id, f"✅ از بدهی شما {amount:,} تومان کسر شد.")
            await message.answer(f"بدهی کاربر {user_id} با موفقیت کاهش یافت.")
    except ValueError:
        await message.answer("لطفاً عدد معتبر وارد کنید.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data.startswith("view_purchase_history_"))
@admin_only
async def view_user_purchase_history(callback: types.CallbackQuery, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    user_purchases = await data_manager.get_user_purchases(user_id)
    if not user_purchases:
        await callback.message.edit_text("این کاربر سابقه خریدی ندارد. 📭")
        return
    page = 0
    per_page = 5
    total_pages = (len(user_purchases) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    purchases_page = user_purchases[start:end]
    history_text = f"**سابقه خرید کاربر `{user_id}`:** 📜\n"
    for item in purchases_page:
        persian_date = format_persian_date(item['date'])
        tracking_code = item['tracking_code']
        history_text += (
            f"🗂 **گروه:** {escape_markdown(item.get('group_name') or 'نامشخص')}\n"
            f"🛒 **محصول:** {escape_markdown(item['product_name'])}\n"
            f"💰 **قیمت:** {item['price']:,} تومان\n"
            f"🗓 **تاریخ:** {persian_date}\n"
            f"🔗 **شماره پیگیری:** `{tracking_code}`\n"
            f"💳 **روش پرداخت:** {escape_markdown(get_payment_method_label(item.get('payment_method', 'card')))}\n"
            f"🏦 **حساب مقصد:** {item.get('bank_account_number', 'نامشخص')}\n"
            f"---------------------------------\n"
        )
    buttons = []
    if page > 0:
        buttons.append(ikb_btn(text="⏪ قبلی", callback_data=f"admin_purchase_page_{user_id}_{page-1}"))
    if page < total_pages - 1:
        buttons.append(ikb_btn(text="⏩ بعدی", callback_data=f"admin_purchase_page_{user_id}_{page+1}"))
    if buttons:
        await callback.message.edit_text(history_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[buttons, [ikb_btn(text="🔙 بازگشت به پروفایل کاربر", callback_data=f"manage_user_{user_id}")]]))
    else:
        await callback.message.edit_text(history_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text="🔙 بازگشت به پروفایل کاربر", callback_data=f"manage_user_{user_id}")]]))

@router.callback_query(F.data.startswith("admin_purchase_page_"))
@admin_only
async def admin_purchase_page_nav(callback: types.CallbackQuery, **kwargs):
    parts = callback.data.split('_')
    user_id = int(parts[3])
    page = int(parts[4])
    user_purchases = await data_manager.get_user_purchases(user_id)
    per_page = 5
    start = page * per_page
    end = start + per_page
    purchases_page = user_purchases[start:end]
    total_pages = (len(user_purchases) + per_page - 1) // per_page
    history_text = f"**سابقه خرید کاربر `{user_id}`:** 📜\n"
    for item in purchases_page:
        persian_date = format_persian_date(item['date'])
        tracking_code = item['tracking_code']
        history_text += (
            f"🗂 **گروه:** {escape_markdown(item.get('group_name') or 'نامشخص')}\n"
            f"🛒 **محصول:** {escape_markdown(item['product_name'])}\n"
            f"💰 **قیمت:** {item['price']:,} تومان\n"
            f"🗓 **تاریخ:** {persian_date}\n"
            f"🔗 **شماره پیگیری:** `{tracking_code}`\n"
            f"💳 **روش پرداخت:** {escape_markdown(get_payment_method_label(item.get('payment_method', 'card')))}\n"
            f"🏦 **حساب مقصد:** {item.get('bank_account_number', 'نامشخص')}\n"
            f"---------------------------------\n"
        )
    buttons = []
    if page > 0:
        buttons.append(ikb_btn(text="⏪ قبلی", callback_data=f"admin_purchase_page_{user_id}_{page-1}"))
    if page < total_pages - 1:
        buttons.append(ikb_btn(text="⏩ بعدی", callback_data=f"admin_purchase_page_{user_id}_{page+1}"))
    if buttons:
        await callback.message.edit_text(history_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[buttons, [ikb_btn(text="🔙 بازگشت به پروفایل کاربر", callback_data=f"manage_user_{user_id}")]]))
    else:
        await callback.message.edit_text(history_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text="🔙 بازگشت به پروفایل کاربر", callback_data=f"manage_user_{user_id}")]]))

@router.callback_query(F.data.startswith("send_message_to_user_"))
@admin_only
async def send_message_to_user_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(admin_target_user_id=user_id)
    await callback.message.edit_text("لطفاً پیام خود را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_user_message)

@router.message(AdminStates.waiting_for_user_message)
async def send_message_to_user_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    try:
        state_data = await state.get_data()
        user_id = state_data.get('admin_target_user_id') or state_data.get('target_user_id')
        if not user_id:
            await message.answer("❌ اطلاعات کاربر یافت نشد. لطفاً از منوی کاربران دوباره اقدام کنید.")
            await state.clear()
            await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)
            return
        await bot.send_message(
            user_id,
            f"**📩 پیام ادمین:**\n{escape_markdown(message.text)}",
            parse_mode="Markdown"
        )
        await message.answer("✅ پیام ارسال شد.")
    except Exception as e:
        logger.error(f"Error in send_message_to_user_process: {e}")
        await message.answer(f"❌ خطا در ارسال: {e}")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

# =================================================================
