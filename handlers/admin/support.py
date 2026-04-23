import datetime

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InlineKeyboardMarkup

from app import bot, data_manager
from states.admin_states import AdminStates
from states.user_states import UserStates
from keyboards.inline import admin_support_menu, broadcast_targets, cancel_only_button, ikb_btn
from keyboards.reply import admin_main_menu
from utils.formatters import escape_markdown, format_persian_date
from utils.parsers import parse_config_file_marker
from utils.settings_helpers import get_configured_usdt_networks, get_primary_usdt_network, get_support_category_label, get_support_priority_label
from utils.telegram_utils import admin_only, is_safe_managed_file, rate_limit, safe_callback_answer, safe_send_document
router = Router()

# 19. هندلر مدیریت پشتیبانی (ادمین)
# =================================================================
@router.message(F.text.in_(["📬 پشتیبانی", "🛟 پشتیبانی", "🎫 تیکت‌ها و پیام همگانی"]))
async def admin_support_panel(message: types.Message, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        return
    await message.answer("پنل تیکت‌ها و پیام همگانی:", reply_markup=admin_support_menu)

@router.callback_query(F.data == "broadcast_menu")
@admin_only
async def broadcast_menu(callback: types.CallbackQuery, **kwargs):
    await callback.message.edit_text("لطفاً گروه مقصد را انتخاب کنید:", reply_markup=broadcast_targets)

@router.callback_query(F.data == "list_open_tickets")
@admin_only
async def list_open_tickets(callback: types.CallbackQuery, **kwargs):
    tickets = await data_manager.get_unanswered_support_tickets()
    if not tickets:
        await callback.message.edit_text('✅ هیچ تیکت بازی وجود ندارد.')
        return
    buttons = []
    for ticket in tickets[:20]:
        label = f"{get_support_priority_label(ticket.get('priority'))} | {get_support_category_label(ticket.get('category'))} | {ticket.get('full_name','کاربر')}"
        buttons.append([ikb_btn(text=label[:60], callback_data=f"open_ticket_{ticket['id']}")])
    buttons.append([ikb_btn(text='🔙 بازگشت', callback_data='back_to_main')])
    await callback.message.edit_text('تیکت‌های باز:', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("open_ticket_"))
@admin_only
async def open_ticket_detail(callback: types.CallbackQuery, **kwargs):
    ticket_id = int((callback.data or '').split('_')[-1])
    tickets = await data_manager.get_all_support_tickets()
    ticket = next((t for t in tickets if t['id'] == ticket_id), None)
    if not ticket:
        await callback.answer('تیکت پیدا نشد.', show_alert=True)
        return
    text = f"🎫 **تیکت #{ticket['id']}**\nکاربر: {escape_markdown(ticket.get('full_name','کاربر'))} (`{ticket.get('user_id')}`)\nدسته‌بندی: {escape_markdown(get_support_category_label(ticket.get('category')))}\nاولویت: {escape_markdown(get_support_priority_label(ticket.get('priority')))}\nوضعیت: {escape_markdown(ticket.get('status','open'))}\nتاریخ: {escape_markdown(format_persian_date(ticket.get('date','')))}\nمتن:\n{escape_markdown(ticket.get('message_text',''))}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text='➡️ پاسخ به کاربر', callback_data=f"reply_to_user_{ticket['user_id']}_{ticket['id']}")],[ikb_btn(text='✅ بستن تیکت', callback_data=f"close_ticket_{ticket['id']}")],[ikb_btn(text='🔙 بازگشت', callback_data='list_open_tickets')]])
    await callback.message.edit_text(text, parse_mode='Markdown', reply_markup=kb)

@router.callback_query(F.data.startswith("close_ticket_"))
@admin_only
async def close_ticket(callback: types.CallbackQuery, **kwargs):
    ticket_id = int((callback.data or '').split('_')[-1])
    await data_manager.update_support_ticket_status(ticket_id, 'closed')
    await callback.message.edit_text('✅ تیکت بسته شد.')

@router.callback_query(F.data == "manage_tracking_code")
@admin_only
async def manage_tracking_code_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_text("لطفاً کد رهگیری را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_tracking_code)

@router.message(AdminStates.waiting_for_tracking_code)
async def manage_tracking_code_search(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    try:
        tracking_code = int(message.text.strip())
    except (TypeError, ValueError, AttributeError):
        await message.answer("لطفاً فقط کد رهگیری عددی وارد کنید.")
        return
    record = await data_manager.find_record_by_tracking_code(tracking_code)
    if not record:
        await message.answer("کد رهگیری معتبر نیست یا یافت نشد. ❌")
        await state.clear()
        return
    if record['type'] == 'purchase':
        data = record['data']
        greg_date = datetime.datetime.strptime(data['date'], "%Y-%m-%d %H:%M:%S")
        j_date = jdatetime.datetime.fromgregorian(datetime=greg_date)
        history_text = (
            f"<b>نوع:</b> خرید محصول 🛒\n"
            f"<b>محصول:</b> {data['product_name']}\n"
            f"<b>قیمت:</b> {data['price']:,} تومان\n"
            f"<b>تاریخ:</b> {j_date.strftime('%Y/%m/%d - %H:%M:%S')}\n"
            f"<b>شماره پیگیری:</b> <code>{data['tracking_code']}</code>\n"
            f"<b>حساب مقصد:</b> {data.get('bank_account_number', 'نامشخص')}\n"
            f"<b>اکانت:</b>\n<code>{data['account']}</code>"
        )
        await message.answer(history_text, parse_mode="HTML")
    await state.clear()

@router.callback_query(F.data.startswith("broadcast_"))
@admin_only
async def broadcast_target_selected(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    target = callback.data.split('_')[1]
    await state.update_data(broadcast_target=target)
    await callback.message.edit_text("لطفاً متن پیام را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_broadcast_message)

@router.message(AdminStates.waiting_for_broadcast_message)
async def send_broadcast_message(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    state_data = await state.get_data()
    target = state_data['broadcast_target']
    all_users = await data_manager.get_all_users()
    users_to_send = []
    if target == "all":
        users_to_send = [u['user_id'] for u in all_users if not u.get('banned', False)]
    elif target == "regulars":
        users_to_send = [u['user_id'] for u in all_users if not u.get('banned', False) and not u.get('is_rep', False)]
    elif target == "debtors":
        debtors = await data_manager.get_all_debtors()
        users_to_send = [u['user_id'] for u in debtors if not u.get('banned', False)]
    elif target == "reps":
        reps = await data_manager.get_all_reps()
        users_to_send = [u['user_id'] for u in reps if not u.get('banned', False)]
    users_to_send = list(dict.fromkeys(users_to_send))
    success_count = 0
    for uid in users_to_send:
        try:
            await bot.send_message(uid, f"**📢 اطلاعیه همگانی:**\n{escape_markdown(message.text)}", parse_mode="Markdown")
            success_count += 1
        except:
            pass
    await message.answer(f"✅ پیام به {success_count} کاربر ارسال شد.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data.startswith("reply_to_user_"))
@admin_only
async def reply_to_user_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    parts = callback.data.split('_')
    user_id = int(parts[3])
    ticket_id = int(parts[4]) if len(parts) > 4 else None
    await state.update_data(reply_to_user_id=user_id, reply_ticket_id=ticket_id)
    await callback.message.edit_text(
        f"لطفاً پاسخ خود را برای کاربر با شناسه `{user_id}` وارد کنید: ✍️",
        parse_mode="Markdown",
        reply_markup=cancel_only_button
    )
    await state.set_state(AdminStates.waiting_for_support_reply)

@router.message(AdminStates.waiting_for_support_reply)
async def send_support_reply(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    state_data = await state.get_data()
    user_id = state_data['reply_to_user_id']
    ticket_id = state_data.get('reply_ticket_id')
    if ticket_id:
        await data_manager.mark_support_ticket_as_answered(ticket_id)
    try:
        await bot.send_message(user_id, f"**📩 پاسخ پشتیبانی:**\n`{escape_markdown(message.text)}`", parse_mode="Markdown")
        await message.answer(f"✅ پاسخ شما با موفقیت برای کاربر `{user_id}` ارسال شد.", reply_markup=admin_main_menu)
    except Exception as e:
        await message.answer(f"❌ ارسال پیام به کاربر با شناسه `{user_id}` ناموفق بود. خطا: {e}", reply_markup=admin_main_menu)
    await state.clear()


@router.callback_query(F.data == "download_latest_openvpn_config")
async def download_latest_openvpn_config(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    latest_config = await data_manager.get_latest_openvpn_config()
    if not latest_config:
        await callback.message.answer("❌ هنوز فایل کانفیگ نهایی ثبت نشده است.")
        return
    cfg_path, cfg_caption = parse_config_file_marker(latest_config)
    if not cfg_path or not is_safe_managed_file(cfg_path):
        await callback.message.answer("❌ فایل کانفیگ روی سرور پیدا نشد. با پشتیبانی تماس بگیرید.")
        return
    await safe_send_document(callback.from_user.id, FSInputFile(cfg_path), caption=(cfg_caption or 'آخرین فایل کانفیگ OpenVPN'))


@router.message(F.text == "📥 آخرین فایل سرور")
@rate_limit(5)
async def latest_server_file_from_menu(message: types.Message, **kwargs):
    latest_config = await data_manager.get_latest_openvpn_config()
    if not latest_config:
        await message.answer("❌ هنوز فایل سرور نهایی توسط ادمین ثبت نشده است.")
        return
    cfg_path, cfg_caption = parse_config_file_marker(latest_config)
    if not cfg_path or not is_safe_managed_file(cfg_path):
        await message.answer("❌ فایل سرور روی هاست پیدا نشد. لطفاً با پشتیبانی تماس بگیرید.")
        return
    await safe_send_document(message.chat.id, FSInputFile(cfg_path), caption=(cfg_caption or 'آخرین فایل سرور OpenVPN'))


async def get_default_usdt_tutorial_text() -> str:
    primary_network = await get_primary_usdt_network()
    configured = await get_configured_usdt_networks()
    available = '، '.join(item['label'] for item in configured) if configured else USDT_NETWORK_LABELS.get(primary_network, primary_network)
    return (
        f"🎓 **آموزش خرید و پرداخت با تتر (USDT)**\n\n"
        f"1) از منوی **کیف پول** گزینه **پرداخت با تتر** را انتخاب کنید.\n"
        f"2) شبکه مورد نظر خود را انتخاب کنید. شبکه اصلی فروشگاه: **{USDT_NETWORK_LABELS.get(primary_network, primary_network)}**\n"
        f"3) آدرس کیف پول نمایش داده شده را دقیق کپی کنید و فقط روی همان شبکه واریز انجام دهید.\n"
        f"4) پس از واریز، مبلغ معادل تومانی را در ربات وارد کنید.\n"
        f"5) اسکرین‌شات یا رسید پرداخت را بفرستید.\n"
        f"6) در مرحله آخر، **TXID / Hash** تراکنش را ارسال کنید تا پرداخت شما سریع‌تر بررسی شود.\n\n"
        f"**شبکه‌های فعال فعلی:** {available}\n\n"
        f"⚠️ در صورت ارسال روی شبکه اشتباه، مسئولیت با کاربر است.\n"
        f"💬 برای هر ابهام از بخش پشتیبانی پیام بفرستید."
    )

@router.message(F.text == "🎓 آموزش خرید با تتر")
@rate_limit(5)
async def show_usdt_tutorial(message: types.Message, **kwargs):
    custom_text = (await data_manager.get_setting('usdt_buy_tutorial') or '').strip()
    text = custom_text if custom_text else await get_default_usdt_tutorial_text()
    await message.answer(text, parse_mode='Markdown')


@router.callback_query(F.data.startswith("support_purchase_"))
async def support_purchase_callback(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    try:
        tracking_code = int(callback.data.rsplit('_', 1)[-1])
    except ValueError:
        await callback.message.answer("کد رهگیری نامعتبر است.")
        return
    record = await data_manager.find_record_by_tracking_code(tracking_code, user_id=callback.from_user.id)
    if not record:
        await callback.message.answer("سفارش مورد نظر پیدا نشد.")
        return
    await state.update_data(support_tracking_code=tracking_code, support_category='purchase', support_priority='high')
    await state.set_state(UserStates.waiting_for_support_with_tracking)
    await callback.message.answer(f"پیام پشتیبانی خود را برای سفارش با کد رهگیری {tracking_code} ارسال کنید:", reply_markup=cancel_only_button)

@router.callback_query(F.data.startswith("support_payment_"))
async def support_payment_callback(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    payment_id = (callback.data or '').split('support_payment_', 1)[1]
    payment = await data_manager.get_debt_payment_by_id(payment_id)
    if not payment or payment.get('user_id') != callback.from_user.id:
        await callback.message.answer("پرداخت مورد نظر پیدا نشد.")
        return
    await state.update_data(support_tracking_code=None, support_payment_id=payment_id, support_category='payment', support_priority='high')
    await state.set_state(UserStates.waiting_for_support_with_tracking)
    await callback.message.answer(f"پیام پشتیبانی خود را برای پرداخت با شناسه {payment_id} ارسال کنید:", reply_markup=cancel_only_button)

# =================================================================
