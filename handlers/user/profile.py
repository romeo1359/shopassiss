import io
import html

import qrcode
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from app import bot, data_manager
from config import BUTTON_STYLE_DANGER, logger
from states.admin_states import AdminStates
from keyboards.inline import cancel_only_button, ikb_btn, start_button
from keyboards.reply import admin_main_menu, rep_menu, user_main_menu
from utils.formatters import format_persian_date, get_payment_method_label, get_payment_status_label
from utils.telegram_utils import copy_temp_storage, rate_limit, safe_callback_answer, safe_send_message, send_account_with_copy_buttons
router = Router()

# 11. هندلرهای اطلاعات کاربری

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
# 11. هندلرهای اطلاعات کاربری
# =================================================================
async def render_user_profile(message: types.Message, user_id: int):
    user_info = await data_manager.get_user(user_id)
    if not user_info:
        await message.answer("اطلاعات کاربری شما یافت نشد. لطفاً ربات را دوباره /start کنید. 🔄")
        return

    reg_date = format_persian_date(user_info.get('registration_date', 'نامشخص'))

    referrer_name = "ندارد"
    if user_info.get('referred_by'):
        ref_user = await data_manager.get_user(user_info.get('referred_by'))
        if ref_user:
            referrer_name = f"{ref_user.get('full_name', 'ناشناس')} ({user_info.get('referred_by')})"
    profile_text = (
        f"**اطلاعات حساب شما:**\n"
        f"**نام و نام خانوادگی:** {user_info.get('full_name', 'ناشناس')}\n"
        f"**نام فروشگاه:** {user_info.get('store_name', 'نامشخص')}\n"
        f"**شماره موبایل:** {user_info.get('phone_number', 'ثبت نشده')}\n"
        f"**تاریخ عضویت:** {reg_date}\n"
        f"**کد معرف شما:** `{user_info.get('referral_code') or 'در انتظار تأیید'}`\n"
        f"**معرف شما:** {referrer_name}\n"
    )
    user_purchases = await data_manager.get_user_purchases(user_id)
    profile_text += f"**تعداد خرید:** {len(user_purchases)} مورد\n"

    if user_info.get('is_rep'):
        profile_text += f"\n**نقش:** نماینده 🧑‍💻"
        profile_text += f"\n**میزان بدهی:** {user_info.get('debt', 0):,} تومان\n"
        profile_text += f"**سقف اعتبار نسیه:** {user_info.get('credit_limit', 0):,} تومان"
    else:
        profile_text += f"\n**نقش:** کاربر عادی 👤"

    edit_profile_button = InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="📝 ویرایش اطلاعات", callback_data="edit_profile")],
            [ikb_btn(text="👥 اطلاعات معرفی", callback_data="view_referral_info")],
            [ikb_btn(text="📋 سابقه خرید", callback_data="view_full_history")]
        ]
    )
    if not user_info.get('is_rep'):
        edit_profile_button.inline_keyboard.insert(0,
            [ikb_btn(text="🧑‍💻 درخواست نمایندگی", callback_data="request_representative")]
        )

    await message.answer(profile_text, parse_mode="Markdown", reply_markup=edit_profile_button)


@router.callback_query(F.data == "view_referral_info")
async def view_referral_info(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    user_id = callback.from_user.id
    user_info = await data_manager.get_user(user_id)
    if not user_info:
        await callback.message.edit_text("اطلاعات کاربری شما یافت نشد. لطفاً دوباره /start کنید.")
        return
    summary = await data_manager.get_referral_summary(user_id)
    referrer_text = "ندارد"
    if user_info.get('referred_by'):
        ref_user = await data_manager.get_user(int(user_info.get('referred_by')))
        if ref_user:
            referrer_text = f"{ref_user.get('full_name', 'ناشناس')} ({user_info.get('referred_by')})"
        else:
            referrer_text = str(user_info.get('referred_by'))
    reward_percent = await data_manager.get_setting('referral_reward_percent') or '1'
    lines = [
        "<b>اطلاعات سیستم معرفی</b> 👥",
        f"<b>کد معرف شما:</b> <code>{html.escape(user_info.get('referral_code') or 'در انتظار تایید')}</code>",
        f"<b>شما توسط:</b> {html.escape(referrer_text)}",
        f"<b>تعداد کل افراد معرفی‌شده:</b> {summary.get('referred_count', 0)} نفر",
        f"<b>تعداد تأییدشده‌ها:</b> {summary.get('approved_referred_count', 0)} نفر",
        f"<b>درصد پاداش معرفی:</b> {html.escape(str(reward_percent))}%",
        f"<b>فروش زیرمجموعه مستقیم:</b> {int(summary.get('downline_sales', 0)):,} تومان",
        f"<b>مجموع پاداش واریزشده:</b> {int(summary.get('total_reward', 0)):,} تومان",
    ]
    referred_users = summary.get('referred_users') or []
    if referred_users:
        lines.append("\n<b>آخرین افراد معرفی‌شده:</b>")
        for idx, item in enumerate(referred_users[:10], start=1):
            approved_date = format_persian_date(item.get('approved_date') or '') if item.get('approved_date') else 'نامشخص'
            lines.append(f"{idx}. {html.escape(item.get('full_name', 'ناشناس'))} - <code>{item.get('user_id')}</code> - {html.escape(approved_date)}")
    else:
        lines.append("\nهنوز هیچ کاربر تأییدشده‌ای را معرفی نکرده‌اید.")
    lines.append("\nپاداش معرفی بعد از خرید موفق فرد معرفی‌شده، به کیف پول شما اضافه می‌شود.")
    markup = InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text="🔙 بازگشت به پروفایل", callback_data="back_to_profile")]])
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=markup)

@router.message(F.text.in_(["👤 اطلاعات حساب من", "👤 حساب من"]))
@rate_limit(10)
async def show_user_profile(message: types.Message, **kwargs):
    user_id = message.from_user.id
    await render_user_profile(message, user_id)

@router.callback_query(F.data == "edit_profile")
async def edit_profile_start(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="ویرایش نام و نام خانوادگی", callback_data="edit_full_name")],
            [ikb_btn(text="ویرایش نام فروشگاه", callback_data="edit_store_name")],
            [ikb_btn(text="❌ لغو", style=BUTTON_STYLE_DANGER, callback_data="cancel")]
        ]
    )
    await callback.message.edit_text("لطفاً فیلدی که می‌خواهید ویرایش کنید را انتخاب کنید:", reply_markup=buttons)
    await callback.answer()

@router.callback_query(F.data == "edit_full_name")
async def edit_full_name_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    await callback.message.edit_text("لطفاً نام و نام خانوادگی جدید خود را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_edit_full_name)

@router.message(AdminStates.waiting_for_edit_full_name)
async def edit_full_name_process(message: types.Message, state: FSMContext, **kwargs):
    if not message.text or len(message.text.strip()) < 3:
        await message.answer("لطفاً یک نام معتبر (حداقل ۳ کاراکتر) وارد کنید.")
        return
    user_id = message.from_user.id
    await data_manager.update_user(user_id, full_name=message.text.strip())
    await message.answer("✅ نام و نام خانوادگی با موفقیت به‌روزرسانی شد.")
    await state.clear()
    user_info = await data_manager.get_user(user_id)
    if user_info.get('is_rep'):
        await message.answer("به منوی نماینده بازگشتید.", reply_markup=rep_menu)
    else:
        await message.answer("به منوی اصلی بازگشتید.", reply_markup=user_main_menu)

@router.callback_query(F.data == "edit_store_name")
async def edit_store_name_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    await callback.message.edit_text("لطفاً نام فروشگاه جدید خود را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_edit_store_name)

@router.message(AdminStates.waiting_for_edit_store_name)
async def edit_store_name_process(message: types.Message, state: FSMContext, **kwargs):
    user_id = message.from_user.id
    await data_manager.update_user(user_id, store_name=message.text.strip())
    await message.answer("✅ نام فروشگاه با موفقیت به‌روزرسانی شد.")
    await state.clear()
    user_info = await data_manager.get_user(user_id)
    if user_info.get('is_rep'):
        await message.answer("به منوی نماینده بازگشتید.", reply_markup=rep_menu)
    else:
        await message.answer("به منوی اصلی بازگشتید.", reply_markup=user_main_menu)

@router.callback_query(F.data == "view_full_history")
async def view_full_history(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    user_id = callback.from_user.id
    user_purchases = await data_manager.get_user_purchases(user_id)
    user_payments = await data_manager.get_user_debt_payments(user_id)
    purchase_count = len(user_purchases)
    payment_count = len(user_payments)

    buttons = []
    if purchase_count > 0:
        buttons.append([InlineKeyboardButton(text=f"🛒 خریدها ({purchase_count} مورد)", callback_data="show_purchase_history")])
    if payment_count > 0:
        buttons.append([InlineKeyboardButton(text=f"💳 سابقه پرداخت ({payment_count} مورد)", callback_data="show_payment_history")])
    if not buttons:
        buttons.append([ikb_btn(text="📭 هیچ سابقه‌ای وجود ندارد", callback_data="no_history")])
    buttons.append([ikb_btn(text="🔙 بازگشت به پروفایل", callback_data="back_to_profile")])
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    header_text = (
        f"<b>سوابق شما</b> 📋\n"
        f"🛒 <b>تعداد خریدها:</b> {purchase_count} مورد\n"
        f"💳 <b>تعداد پرداخت‌ها:</b> {payment_count} مورد\n"
        f"لطفاً نوع سابقه مورد نظر را انتخاب کنید:"
    )
    await callback.message.edit_text(header_text, parse_mode="HTML", reply_markup=inline_keyboard)

@router.callback_query(F.data == "show_purchase_history")
async def show_purchase_history(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    user_id = callback.from_user.id
    user_purchases = await data_manager.get_user_purchases(user_id)
    if not user_purchases:
        await callback.message.edit_text("📭 شما هیچ خریدی نداشته‌اید.")
        return
    page = 0
    per_page = 10
    total_pages = (len(user_purchases) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    purchases_page = user_purchases[start:end]
    buttons = []
    for purchase in purchases_page:
        product_name = purchase['product_name']
        price = purchase['price']
        tracking_code = purchase['tracking_code']
        button_text = f"{product_name} - {price:,} تومان"
        if len(button_text) > 40:
            button_text = button_text[:37] + "..."
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"purchase_detail_{tracking_code}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(ikb_btn(text="⏪ قبلی", callback_data=f"purchase_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(ikb_btn(text="⏩ بعدی", callback_data=f"purchase_page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([ikb_btn(text="🔙 بازگشت به سابقه", callback_data="view_full_history")])
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    total_spent = sum(p['price'] for p in user_purchases)
    header_text = (
        f"<b>سابقه خریدهای شما</b> 🛒\n"
        f"📊 <b>تعداد کل خریدها:</b> {len(user_purchases)} مورد\n"
        f"💰 <b>مجموع هزینه‌ها:</b> {total_spent:,} تومان\n"
        f"صفحه {page+1} از {total_pages}\n"
        f"برای مشاهده جزئیات هر خرید، روی آن کلیک کنید:"
    )
    await callback.message.edit_text(header_text, parse_mode="HTML", reply_markup=inline_keyboard)

@router.callback_query(F.data.startswith("purchase_page_"))
async def purchase_page_nav(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    page = int(callback.data.split('_')[-1])
    user_id = callback.from_user.id
    user_purchases = await data_manager.get_user_purchases(user_id)
    per_page = 10
    start = page * per_page
    end = start + per_page
    purchases_page = user_purchases[start:end]
    buttons = []
    for purchase in purchases_page:
        product_name = purchase['product_name']
        price = purchase['price']
        tracking_code = purchase['tracking_code']
        button_text = f"{product_name} - {price:,} تومان"
        if len(button_text) > 40:
            button_text = button_text[:37] + "..."
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"purchase_detail_{tracking_code}")])
    total_pages = (len(user_purchases) + per_page - 1) // per_page
    nav_buttons = []
    if page > 0:
        nav_buttons.append(ikb_btn(text="⏪ قبلی", callback_data=f"purchase_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(ikb_btn(text="⏩ بعدی", callback_data=f"purchase_page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([ikb_btn(text="🔙 بازگشت به سابقه", callback_data="view_full_history")])
    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    total_spent = sum(p['price'] for p in user_purchases)
    header_text = (
        f"<b>سابقه خریدهای شما</b> 🛒\n"
        f"📊 <b>تعداد کل خریدها:</b> {len(user_purchases)} مورد\n"
        f"💰 <b>مجموع هزینه‌ها:</b> {total_spent:,} تومان\n"
        f"صفحه {page+1} از {total_pages}\n"
        f"برای مشاهده جزئیات هر خرید، روی آن کلیک کنید:"
    )
    await callback.message.edit_text(header_text, parse_mode="HTML", reply_markup=inline_keyboard)

@router.callback_query(F.data.startswith("purchase_detail_"))
async def show_purchase_detail(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    tracking_code = int(callback.data.split('_')[-1])
    user_id = callback.from_user.id
    purchase = await data_manager.get_purchase_by_tracking_code(tracking_code)
    if not purchase or purchase['user_id'] != user_id:
        await callback.answer("❌ خرید مورد نظر یافت نشد یا متعلق به شما نیست.")
        return
    persian_date = format_persian_date(purchase['date'])
    account_text = purchase['account']
    
    account_data = {}
    lines = account_text.split('\n')
    for line in lines:
        if ': ' in line:
            key, value = line.split(': ', 1)
            account_data[key] = value
    
    inferred_account_type = 'other'
    if account_text.startswith(('vmess://', 'vless://', 'trojan://')):
        inferred_account_type = 'v2ray'
    elif 'فایل کانفیگ' in account_text:
        inferred_account_type = 'openvpn'
    elif ('آدرس سرور' in account_text) or ('کلید (Secret)' in account_text):
        inferred_account_type = 'l2tp'

    await send_account_with_copy_buttons(callback.message.chat.id, {
        'account_type': inferred_account_type,
        'username': account_data.get('نام کاربری', ''),
        'password': account_data.get('رمز عبور', ''),
        'secret': account_data.get('کلید (Secret)', ''),
        'server': account_data.get('آدرس سرور', ''),
        'port': '',
        'config': account_text if account_text.startswith(('vmess://', 'vless://', 'trojan://')) else account_data.get('فایل کانفیگ', '')
    }, extra_buttons=[[ikb_btn(text="🆘 پشتیبانی این خرید", callback_data=f"support_purchase_{tracking_code}")], [ikb_btn(text="📊 حجم و زمان باقی مانده", callback_data=f"usage_info_{tracking_code}")]])
    
    if account_text.startswith(('vmess://', 'vless://', 'trojan://')):
        try:
            img = qrcode.make(account_text)
            buffer = io.BytesIO()
            img.save(buffer, 'PNG')
            buffer.seek(0)
            await callback.message.answer_photo(photo=BufferedInputFile(buffer.read(), filename="qrcode.png"), caption="🔗 QR Code لینک اکانت:")
        except Exception as e:
            logger.error(f"Failed to generate QR code: {e}")
            await callback.message.answer("خطا در ساخت QR Code. 😔")
    await callback.answer()

@router.callback_query(F.data.startswith("usage_info_"))
async def show_usage_info_placeholder(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    tracking_code = (callback.data or '').split('usage_info_', 1)[1]
    await safe_send_message(
        callback.message.chat.id,
        f"📊 اطلاعات حجم و زمان باقی‌مانده برای خرید `{tracking_code}` در نسخه‌های بعدی پس از اتصال ربات به سرور نمایش داده می‌شود.",
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "show_payment_history")
async def show_payment_history(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    user_id = callback.from_user.id
    user_payments = await data_manager.get_user_debt_payments(user_id)
    if not user_payments:
        await callback.message.edit_text("📭 شما هنوز هیچ پرداختی ثبت نکرده‌اید.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text="🔙 بازگشت به سابقه", callback_data="view_full_history")]]))
        return
    page = 0
    per_page = 10
    total_pages = (len(user_payments) + per_page - 1) // per_page
    payments_page = user_payments[page * per_page:(page + 1) * per_page]
    buttons = []
    for payment in payments_page:
        method = get_payment_method_label(payment.get('payment_method'))
        status = get_payment_status_label(payment.get('status'))
        label = f"{method} - {payment['amount']:,} تومان - {status}"
        if len(label) > 56:
            label = label[:53] + "..."
        buttons.append([ikb_btn(text=label, callback_data=f"payment_detail_{payment['payment_id']}")])
    if total_pages > 1:
        buttons.append([ikb_btn(text="⏩ بعدی", callback_data="payment_page_1")])
    buttons.append([ikb_btn(text="🔙 بازگشت به سابقه", callback_data="view_full_history")])
    total_amount = sum(int(p.get('amount') or 0) for p in user_payments)
    pending_count = sum(1 for p in user_payments if (p.get('status') or '').lower() == 'pending')
    text = (
        f"<b>سابقه پرداخت‌های شما</b> 💳\n"
        f"📊 <b>تعداد کل:</b> {len(user_payments)} مورد\n"
        f"💰 <b>جمع مبالغ:</b> {total_amount:,} تومان\n"
        f"⏳ <b>در انتظار بررسی:</b> {pending_count} مورد\n"
        f"صفحه 1 از {total_pages}"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("payment_page_"))
async def payment_page_nav(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    page = int((callback.data or 'payment_page_0').split('_')[-1])
    user_id = callback.from_user.id
    user_payments = await data_manager.get_user_debt_payments(user_id)
    if not user_payments:
        await callback.message.edit_text("📭 شما هنوز هیچ پرداختی ثبت نکرده‌اید.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text="🔙 بازگشت به سابقه", callback_data="view_full_history")]]))
        return
    per_page = 10
    total_pages = (len(user_payments) + per_page - 1) // per_page
    if page < 0:
        page = 0
    if page > total_pages - 1:
        page = total_pages - 1
    payments_page = user_payments[page * per_page:(page + 1) * per_page]
    buttons = []
    for payment in payments_page:
        method = get_payment_method_label(payment.get('payment_method'))
        status = get_payment_status_label(payment.get('status'))
        label = f"{method} - {payment['amount']:,} تومان - {status}"
        if len(label) > 56:
            label = label[:53] + "..."
        buttons.append([ikb_btn(text=label, callback_data=f"payment_detail_{payment['payment_id']}")])
    nav = []
    if page > 0:
        nav.append(ikb_btn(text="⏪ قبلی", callback_data=f"payment_page_{page-1}"))
    if page < total_pages - 1:
        nav.append(ikb_btn(text="⏩ بعدی", callback_data=f"payment_page_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([ikb_btn(text="🔙 بازگشت به سابقه", callback_data="view_full_history")])
    total_amount = sum(int(p.get('amount') or 0) for p in user_payments)
    pending_count = sum(1 for p in user_payments if (p.get('status') or '').lower() == 'pending')
    text = (
        f"<b>سابقه پرداخت‌های شما</b> 💳\n"
        f"📊 <b>تعداد کل:</b> {len(user_payments)} مورد\n"
        f"💰 <b>جمع مبالغ:</b> {total_amount:,} تومان\n"
        f"⏳ <b>در انتظار بررسی:</b> {pending_count} مورد\n"
        f"صفحه {page+1} از {total_pages}"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("payment_detail_"))
async def payment_detail(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    payment_id = (callback.data or '').split('payment_detail_', 1)[1]
    payment = await data_manager.get_debt_payment_by_id(payment_id)
    if not payment or payment.get('user_id') != callback.from_user.id:
        await callback.answer("❌ پرداخت مورد نظر یافت نشد یا متعلق به شما نیست.", show_alert=True)
        return
    method = get_payment_method_label(payment.get('payment_method'))
    status = get_payment_status_label(payment.get('status'))
    network = payment.get('payment_network') or '---'
    destination = payment.get('payment_destination') or '---'
    text = (
        f"<b>جزئیات پرداخت</b> 💳\n"
        f"🆔 <b>شناسه:</b> <code>{html.escape(payment.get('payment_id', ''))}</code>\n"
        f"💰 <b>مبلغ:</b> {int(payment.get('amount') or 0):,} تومان\n"
        f"💼 <b>روش پرداخت:</b> {html.escape(method)}\n"
        f"🌐 <b>شبکه:</b> {html.escape(network)}\n"
        f"🎯 <b>مقصد:</b> <code>{html.escape(destination)}</code>\n"
        f"🔗 <b>TXID:</b> <code>{html.escape(payment.get('txid') or '---')}</code>\n"
        f"📌 <b>وضعیت:</b> {html.escape(status)}\n"
        f"🕒 <b>تاریخ:</b> {html.escape(format_persian_date(payment.get('date', 'نامشخص')))}"
    )
    buttons = [[ikb_btn(text="🆘 پشتیبانی این پرداخت", callback_data=f"support_payment_{payment.get('payment_id', '')}")],[ikb_btn(text="🔙 بازگشت به پرداخت‌ها", callback_data="show_payment_history")]]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("copy_"))
async def copy_account_field(callback: types.CallbackQuery, **kwargs):
    data_id = callback.data
    value = copy_temp_storage.get(data_id)
    if value:
        await bot.send_message(callback.from_user.id, f"```\n{value}\n```", parse_mode="Markdown")
        await callback.answer("✅ کپی شد", show_alert=True)
    else:
        await callback.answer("❌ منقضی شده. دوباره تلاش کنید.", show_alert=True)

@router.callback_query(F.data == "back_to_purchase")
async def back_to_purchase(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    await callback.message.delete()
    await show_purchase_history(callback)

@router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    await render_user_profile(callback.message, callback.from_user.id)

@router.callback_query(F.data == "no_history")
async def no_history(callback: types.CallbackQuery, **kwargs):
    await callback.answer("شما هیچ سابقه‌ای ندارید", show_alert=True)

# =================================================================
