import datetime
import os
import random
import re
import mimetypes
import hashlib
import html

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup

from app import bot, data_manager
from config import ADMIN_ID, UPLOADS_DIR, logger
from states.user_states import UserStates
from keyboards.inline import cancel_only_button, ikb_btn
from keyboards.reply import rep_menu
from utils.formatters import escape_markdown, escape_markdown_code, format_persian_date, get_payment_method_label
from utils.parsers import parse_approve_payment_callback
from utils.settings_helpers import build_usdt_network_selector_markup, get_configured_usdt_networks, get_primary_usdt_network
from utils.telegram_utils import notify_financial_admins_and_admin, rate_limit, safe_edit_callback_message, safe_send_message, schedule_photo_deletion
from utils.payments import build_payment_methods_markup, get_role_payment_methods, is_payment_method_allowed
router = Router()

# 14. هندلرهای کیف پول (با تأیید ادمین) - نسخه کامل و اصلاح شده
# =================================================================

async def notify_financial_admins_and_admin(message_text: str, photo_id: str = None, reply_markup: InlineKeyboardMarkup = None, target_manager_user_id: int = 0, payment_id: str = None):
    try:
        if photo_id:
            sent = await bot.send_photo(ADMIN_ID, photo=photo_id, caption=message_text, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            sent = await bot.send_message(ADMIN_ID, message_text, parse_mode="Markdown", reply_markup=reply_markup)
        if payment_id and sent is not None:
            await data_manager.add_payment_notification(payment_id, ADMIN_ID, sent.message_id)
        return [sent] if sent else []
    except Exception as e:
        logger.warning(f'Failed to notify admin {ADMIN_ID}: {e}')
        return []


async def disable_payment_notification_buttons(payment_id: str, final_text: str):
    notifications = await data_manager.get_payment_notifications(payment_id)
    for item in notifications:
        try:
            await bot.edit_message_reply_markup(chat_id=item['chat_id'], message_id=item['message_id'], reply_markup=None)
            await bot.edit_message_caption(chat_id=item['chat_id'], message_id=item['message_id'], caption=final_text, parse_mode='Markdown', reply_markup=None)
        except Exception:
            try:
                await bot.edit_message_text(chat_id=item['chat_id'], message_id=item['message_id'], text=final_text, parse_mode='Markdown', reply_markup=None)
            except Exception:
                pass


@router.message(F.text == "💰 کیف پول")
@rate_limit(10)
async def handle_wallet(message: types.Message, **kwargs):
    user_id = message.from_user.id
    user_info = await data_manager.get_user(user_id)
    balance = user_info.get('balance', 0)
    allowed_methods = await get_role_payment_methods(user_info)
    if user_info.get('is_rep'):
        await message.answer(f"موجودی کیف پول شما: {balance:,} تومان 💰", reply_markup=build_payment_methods_markup(allowed_methods, is_rep=True))
    else:
        await message.answer(f"موجودی کیف پول شما: {balance:,} تومان 💰")
        await message.answer("برای شارژ حساب می‌توانید از روش‌های مجاز زیر استفاده کنید. 👇", reply_markup=build_payment_methods_markup(allowed_methods, is_rep=False))

@router.message(F.text.in_(["💳 درخواست‌های پرداخت", "💳 درخواست های پرداخت", "درخواست‌های پرداخت", "درخواست های پرداخت", "⏳ پرداخت‌های معلق", "⏳ پرداخت های معلق", "پرداخت‌های معلق", "پرداخت های معلق"]))
@rate_limit(10)
async def list_financial_requests(message: types.Message, **kwargs):
    user_id = message.from_user.id
    is_admin_user = (user_id == ADMIN_ID) or await data_manager.is_admin(user_id)
    if not is_admin_user:
        await message.answer("شما دسترسی به این بخش ندارید.")
        return

    pending_payments = await data_manager.get_all_debt_payments()
    pending = [p for p in pending_payments if p['status'] == 'pending']

    if not pending:
        await message.answer("هیچ درخواست مالی در انتظار تأیید برای شما وجود ندارد.")
        return

    for p in pending:
        user = await data_manager.get_user(p['user_id'])
        user_name = user['full_name'] if user else 'ناشناس'
        bank = await data_manager.get_bank_account_by_id(p.get('target_bank_id', 0)) if p.get('target_bank_id') else None
        target_manager_name = ''
        if bank and bank.get('user_id'):
            manager_user = await data_manager.get_user(bank['user_id'])
            target_manager_name = manager_user.get('full_name', 'ادمین') if manager_user else 'ادمین'
        method_label = get_payment_method_label(p.get('payment_method', 'card'))
        text = (
            f"<b>درخواست #{html.escape(str(p['payment_id']))}</b>\n"
            f"<b>کاربر:</b> {html.escape(str(user_name))} (ID: <code>{int(p['user_id'])}</code>)\n"
            f"<b>روش پرداخت:</b> {html.escape(str(method_label))}\n"
            f"<b>مبلغ:</b> {int(p['amount']):,} تومان\n"
            f"<b>تاریخ:</b> {html.escape(str(format_persian_date(p['date'])))}\n"
            f"<b>وضعیت:</b> در انتظار"
        )
        if p.get('payment_network'):
            text += f"\n<b>شبکه:</b> <code>{html.escape(str(p.get('payment_network', '')))}</code>"
        if p.get('payment_destination'):
            text += f"\n<b>مقصد پرداخت:</b> <code>{html.escape(str(p.get('payment_destination', '')))}</code>"

        if bank:
            text += f"\n<b>حساب مقصد:</b> {html.escape(str(bank['account_number']))} - {html.escape(str(bank['account_owner']))}"
        if target_manager_name:
            text += f"\n<b>مدیر مسئول:</b> {html.escape(str(target_manager_name))}"
        buttons = InlineKeyboardMarkup(
            inline_keyboard=[[
                ikb_btn(text="✅ تأیید", callback_data=f"approve_payment_{p['payment_id']}_{p['amount']}_{p.get('target_bank_id', 0)}"),
                ikb_btn(text="❌ رد", callback_data=f"reject_payment_{p['payment_id']}_{p.get('target_bank_id', 0)}")
            ]]
        )
        file_path = os.path.join(UPLOADS_DIR, p['file_name'])
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                sent = await bot.send_photo(message.chat.id, photo=BufferedInputFile(f.read(), filename=p['file_name']), caption=text, reply_markup=buttons, parse_mode="HTML")
        else:
            sent = await message.answer(text, reply_markup=buttons, parse_mode="HTML")
        await data_manager.add_payment_notification(p['payment_id'], message.chat.id, sent.message_id)


@router.callback_query(F.data == "topup_card_to_card")
async def topup_card_to_card_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    user_info = await data_manager.get_user(callback.from_user.id)
    if not await is_payment_method_allowed(user_info, 'card'):
        await callback.message.edit_text('⛔ کارت به کارت برای نقش شما فعال نیست.')
        return
    bank_account = await data_manager.get_default_bank_account()
    if not bank_account:
        await callback.message.edit_text("⚠️ هیچ حساب بانکی فعالی تنظیم نشده است. لطفاً با پشتیبانی تماس بگیرید.")
        return
    await state.update_data(selected_bank=bank_account, payment_method='card', payment_destination=bank_account.get('account_number', ''))
    await callback.message.edit_text(
        f"💳 **برای شارژ حساب، مبلغ مورد نظر را به شماره حساب زیر واریز کنید:**\n"
        f"**شماره حساب:** `{bank_account['account_number']}`\n"
        f"**به نام:** {escape_markdown(bank_account['account_owner'])}\n"
        f"سپس تصویر فیش واریزی را ارسال کنید.\n"
        f"لطفاً مبلغ واریزی را به تومان وارد کنید:",
        parse_mode="Markdown",
        reply_markup=cancel_only_button
    )
    await state.set_state(UserStates.waiting_for_topup_amount_from_user)


@router.callback_query(F.data == "topup_usdt")
async def topup_usdt_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    user_info = await data_manager.get_user(callback.from_user.id)
    if not await is_payment_method_allowed(user_info, 'usdt'):
        await callback.message.edit_text('⛔ پرداخت تتری برای نقش شما فعال نیست.')
        return
    configured = await get_configured_usdt_networks()
    if not configured:
        await callback.message.edit_text("⚠️ هنوز هیچ آدرس کیف پول تتری توسط ادمین ثبت نشده است. لطفاً با پشتیبانی تماس بگیرید.")
        return
    primary = await get_primary_usdt_network()
    text = (
        "₮ **شارژ با تتر (USDT)**\n"
        f"**شبکه اصلی:** `{primary}`\n\n"
        "لطفاً شبکه‌ای که با آن واریز می‌کنید را انتخاب کنید:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=build_usdt_network_selector_markup('topup_usdt_network_', configured))

@router.callback_query(F.data.startswith("topup_usdt_network_"))
async def topup_usdt_choose_network(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    network = (callback.data or '').split('topup_usdt_network_', 1)[1].upper()
    configured = await get_configured_usdt_networks()
    selected = next((item for item in configured if item['key'] == network), None)
    if not selected:
        await callback.message.edit_text("⚠️ آدرس این شبکه تنظیم نشده است. لطفاً شبکه دیگری را انتخاب کنید.", reply_markup=build_usdt_network_selector_markup('topup_usdt_network_', configured))
        return
    await state.update_data(selected_bank=None, payment_method='usdt', payment_destination=selected['address'], payment_network=selected['key'])
    text = (
        "₮ **شارژ با تتر (USDT)**\n"
        f"**شبکه انتخابی:** `{selected['key']}`\n"
        f"**آدرس کیف پول:** `{selected['address']}`\n\n"
        "پس از انتقال، مبلغ معادل تومانی را وارد کنید و سپس اسکرین‌شات یا رسید تراکنش را ارسال نمایید."
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=cancel_only_button)
    await state.set_state(UserStates.waiting_for_topup_amount_from_user)


@router.message(UserStates.waiting_for_topup_amount_from_user)
async def get_topup_amount_from_user(message: types.Message, state: FSMContext, **kwargs):
    try:
        amount = int(message.text)
        if amount <= 0:
            await message.answer("لطفاً مبلغ معتبر وارد کنید.")
            return
        state_data = await state.get_data()
        payment_method = state_data.get('payment_method', 'card')
        min_topup = int(await data_manager.get_setting('min_wallet_topup') or '0')
        if amount < min_topup:
            await message.answer(f"حداقل مبلغ شارژ {min_topup:,} تومان است.")
            return
        await state.update_data(amount=amount)
        receipt_prompt = 'لطفاً تصویر فیش واریزی را ارسال کنید:' if payment_method != 'usdt' else 'لطفاً اسکرین‌شات یا رسید پرداخت تتر را ارسال کنید:'
        await message.answer(receipt_prompt, reply_markup=cancel_only_button)
        await state.set_state(UserStates.waiting_for_photo_receipt)
    except ValueError:
        await message.answer("لطفاً عدد معتبر وارد کنید.")


async def finalize_wallet_payment_request(message: types.Message, state: FSMContext, txid: str = ''):
    state_data = await state.get_data()
    amount = state_data['amount']
    selected_bank = state_data.get('selected_bank') or {}
    payment_method = (state_data.get('payment_method') or 'card').lower()
    payment_network = state_data.get('payment_network', '')
    payment_destination = state_data.get('payment_destination', '')
    user_id = message.from_user.id
    local_path = state_data.get('receipt_local_path', '')
    receipt_file_id = state_data.get('receipt_file_id', '')
    if not local_path or not os.path.exists(local_path):
        await message.answer('❌ فایل رسید پیدا نشد. لطفاً دوباره تلاش کنید.')
        await state.clear()
        return
    prefix = 'usdt_topup' if payment_method == 'usdt' else 'topup'
    payment_id = f"{prefix}_{random.randint(100000, 999999)}"
    filename = os.path.basename(local_path)
    await data_manager.create_debt_payment(
        user_id, amount, filename, payment_id,
        target_bank_id=selected_bank.get('id', 0),
        payment_method=payment_method,
        payment_network=payment_network,
        payment_destination=payment_destination,
    )
    if txid:
        await data_manager.update_debt_payment_txid(payment_id, txid)
    await schedule_photo_deletion(filename, 30, user_id, 'شارژ کیف پول' if payment_method != 'usdt' else 'شارژ کیف پول با تتر')
    method_label = get_payment_method_label(payment_method)
    destination_text = f"{selected_bank.get('account_number', 'نامشخص')} - {selected_bank.get('account_owner', 'نامشخص')}" if payment_method != 'usdt' else payment_destination
    admin_message = (
        f"📥 **درخواست شارژ کیف پول**\n"
        f"**کاربر:** {escape_markdown(message.from_user.full_name)} (ID: `{user_id}`)\n"
        f"**روش پرداخت:** {escape_markdown(method_label)}\n"
        f"**مبلغ:** {amount:,} تومان\n"
        f"**مقصد پرداخت:** `{escape_markdown_code(destination_text)}`\n"
        f"**تاریخ:** {escape_markdown(format_persian_date(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))}\n"
        f"**شناسه پرداخت:** `{payment_id}`"
    )
    if payment_network:
        admin_message += f"\n**شبکه:** `{escape_markdown_code(payment_network)}`"
    if txid:
        admin_message += f"\n**TXID:** `{escape_markdown_code(txid)}`"
    approve_buttons = InlineKeyboardMarkup(inline_keyboard=[[
        ikb_btn(text='✅ تأیید', callback_data=f"approve_payment_{payment_id}_{amount}_{selected_bank.get('id', 0)}"),
        ikb_btn(text='❌ رد', callback_data=f"reject_payment_{payment_id}_{selected_bank.get('id', 0)}")
    ]])
    await notify_financial_admins_and_admin(admin_message, receipt_file_id, approve_buttons, target_manager_user_id=selected_bank.get('user_id', 0), payment_id=payment_id)
    success_text = '✅ درخواست شارژ شما برای بررسی ادمین ارسال شد. پس از تأیید، موجودی حساب شما افزایش خواهد یافت.' if payment_method != 'usdt' else '✅ درخواست شارژ تتری شما برای بررسی ادمین ارسال شد. پس از بررسی و تأیید، معادل تومانی به کیف پول شما اضافه می‌شود.'
    await message.answer(success_text)
    await state.clear()

@router.message(UserStates.waiting_for_photo_receipt)
async def get_photo_receipt(message: types.Message, state: FSMContext, **kwargs):
    if not message.photo:
        await message.answer('لطفاً تصویر فیش واریزی را ارسال کنید.')
        return
    state_data = await state.get_data()
    payment_method = (state_data.get('payment_method') or 'card').lower()
    user_id = message.from_user.id
    file = await bot.get_file(message.photo[-1].file_id)
    file_path = file.file_path
    safe_id = hashlib.md5(str(user_id).encode()).hexdigest()[:8]
    timestamp = int(datetime.datetime.now().timestamp())
    filename = f"{payment_method}_{safe_id}_{timestamp}.jpg"
    local_path = os.path.join(UPLOADS_DIR, filename)
    await bot.download_file(file_path, local_path)
    mime = mimetypes.guess_type(local_path)[0]
    if not mime or not mime.startswith('image/'):
        os.remove(local_path)
        await message.answer('❌ فایل ارسالی معتبر نیست. لطفاً یک تصویر واقعی ارسال کنید.')
        return
    await state.update_data(receipt_local_path=local_path, receipt_file_id=message.photo[-1].file_id)
    if payment_method == 'usdt':
        await message.answer('لطفاً TXID / Hash تراکنش تتر را ارسال کنید. اگر ندارید، یک خط تیره بفرستید.', reply_markup=cancel_only_button)
        await state.set_state(UserStates.waiting_for_payment_txid)
        return
    await finalize_wallet_payment_request(message, state)

@router.message(UserStates.waiting_for_payment_txid)
async def get_payment_txid(message: types.Message, state: FSMContext, **kwargs):
    txid = (message.text or '').strip()
    if txid != '-':
        txid = txid.replace(' ', '')
        if len(txid) < 8:
            await message.answer('TXID معتبر نیست. دوباره بفرستید یا خط تیره ارسال کنید.')
            return
    else:
        txid = ''
    await finalize_wallet_payment_request(message, state, txid=txid)

@router.callback_query(F.data.startswith("approve_payment_"))
async def approve_payment(callback: types.CallbackQuery, **kwargs):
    user_id = callback.from_user.id
    user_info = await data_manager.get_user(user_id)
    is_main_admin = (user_id == ADMIN_ID) or await data_manager.is_admin(user_id)
    payment_id, _, bank_id = parse_approve_payment_callback(callback.data)
    if not payment_id:
        await callback.answer("ساختار درخواست نامعتبر است.", show_alert=True)
        return

    payment = await data_manager.get_debt_payment_by_id(payment_id)
    if not payment:
        await safe_edit_callback_message(callback, '❌ پرداخت یافت نشد.')
        return

    bank_id = int(bank_id or payment.get('target_bank_id') or 0)
    if not is_main_admin:
        await callback.answer("فقط ادمین می‌تواند این فیش را تأیید کند.", show_alert=True)
        return

    if payment['status'] != 'pending':
        processed_by = payment.get('approved_by', 0)
        approver = await data_manager.get_user(processed_by) if processed_by else None
        approver_name = approver.get('full_name', 'کاربر دیگر') if approver else 'کاربر دیگر'
        await callback.answer(f"این درخواست قبلاً پردازش شده است. توسط {approver_name}", show_alert=True)
        return
    if payment['user_id'] == user_id:
        await callback.answer("شما نمی‌توانید درخواست خود را تأیید کنید.", show_alert=True)
        return

    success = await data_manager.update_debt_payment_status(payment_id, 'approved', approved_by=user_id)
    if not success:
        latest = await data_manager.get_debt_payment_by_id(payment_id)
        processed_by = latest.get('approved_by', 0) if latest else 0
        approver = await data_manager.get_user(processed_by) if processed_by else None
        approver_name = approver.get('full_name', 'شخص دیگر') if approver else 'شخص دیگر'
        await callback.answer(f"این درخواست قبلاً توسط {approver_name} پردازش شده است.", show_alert=True)
        return

    if payment_id.startswith("pay_"):
        await data_manager.update_user_debt(payment['user_id'], payment['amount'], operation="subtract")
        user_message = f"✅ پرداخت بدهی شما به مبلغ {payment['amount']:,} تومان تأیید شد و از بدهی شما کسر شد."
    else:
        await data_manager.update_user_balance(payment['user_id'], payment['amount'], operation="add")
        method_label = get_payment_method_label(payment.get('payment_method', 'card'))
        user_message = f"✅ درخواست شارژ کیف پول شما از طریق {method_label} به مبلغ {payment['amount']:,} تومان تأیید شد و به موجودی شما اضافه شد."

    await safe_send_message(payment['user_id'], user_message)
    approver_name = "ادمین اصلی" if is_main_admin and user_id == ADMIN_ID else (user_info.get('full_name', 'ناشناس') if user_info else 'ناشناس')
    final_text = f"✅ پرداخت `{payment_id}` به مبلغ {payment['amount']:,} تومان توسط *{escape_markdown(approver_name)}* تأیید شد."
    await disable_payment_notification_buttons(payment_id, final_text)
    await notify_financial_admins_and_admin(f"✅ پرداخت کاربر {payment['user_id']} با مبلغ {payment['amount']:,} تومان توسط {approver_name} تأیید شد.")
    await callback.answer("پرداخت با موفقیت تأیید شد.")


@router.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(callback: types.CallbackQuery, **kwargs):
    user_id = callback.from_user.id
    user_info = await data_manager.get_user(user_id)
    is_main_admin = (user_id == ADMIN_ID) or await data_manager.is_admin(user_id)
    m = re.fullmatch(r'reject_payment_(.+?)_(\d+)', callback.data or '')
    if not m:
        await callback.answer("ساختار درخواست نامعتبر است.", show_alert=True)
        return
    payment_id = m.group(1)
    bank_id = int(m.group(2))

    payment = await data_manager.get_debt_payment_by_id(payment_id)
    if not payment:
        await safe_edit_callback_message(callback, '❌ پرداخت یافت نشد.')
        return

    bank_id = int(bank_id or payment.get('target_bank_id') or 0)
    if not is_main_admin:
        await callback.answer("فقط ادمین می‌تواند این فیش را رد کند.", show_alert=True)
        return

    if payment['status'] != 'pending':
        processed_by = payment.get('approved_by', 0)
        approver = await data_manager.get_user(processed_by) if processed_by else None
        approver_name = approver.get('full_name', 'کاربر دیگر') if approver else 'کاربر دیگر'
        await callback.answer(f"این درخواست قبلاً پردازش شده است. توسط {approver_name}", show_alert=True)
        return
    if payment['user_id'] == user_id:
        await callback.answer("شما نمی‌توانید درخواست خود را رد کنید.", show_alert=True)
        return

    success = await data_manager.update_debt_payment_status(payment_id, 'rejected', approved_by=user_id)
    if not success:
        latest = await data_manager.get_debt_payment_by_id(payment_id)
        processed_by = latest.get('approved_by', 0) if latest else 0
        approver = await data_manager.get_user(processed_by) if processed_by else None
        approver_name = approver.get('full_name', 'شخص دیگر') if approver else 'شخص دیگر'
        await callback.answer(f"این درخواست قبلاً توسط {approver_name} پردازش شده است.", show_alert=True)
        return

    reject_method = get_payment_method_label(payment.get('payment_method', 'card'))
    await safe_send_message(payment['user_id'], f"❌ درخواست {reject_method} شما رد شد. لطفاً با پشتیبانی تماس بگیرید.")
    approver_name = "ادمین اصلی" if is_main_admin and user_id == ADMIN_ID else (user_info.get('full_name', 'ناشناس') if user_info else 'ناشناس')
    final_text = f"❌ پرداخت `{payment_id}` به مبلغ {payment['amount']:,} تومان توسط *{escape_markdown(approver_name)}* رد شد."
    await disable_payment_notification_buttons(payment_id, final_text)
    await notify_financial_admins_and_admin(f"❌ پرداخت کاربر {payment['user_id']} با مبلغ {payment['amount']:,} تومان توسط {approver_name} رد شد.")
    await callback.answer("پرداخت رد شد.")


@router.callback_query(F.data == "topup_credit")
async def topup_credit_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    user_id = callback.from_user.id
    user_info = await data_manager.get_user(user_id)
    credit_limit = user_info.get('credit_limit', 0)
    current_debt = user_info.get('debt', 0)
    available_credit = credit_limit - current_debt
    if available_credit <= 0:
        await callback.message.edit_text("سقف اعتبار نسیه شما پر شده است. ❌")
        return
    await callback.message.edit_text(f"مبلغ قابل درخواست: تا {available_credit:,} تومان\nلطفاً مبلغ را وارد کنید:")
    await state.set_state(UserStates.waiting_for_credit_topup_amount)


@router.message(UserStates.waiting_for_credit_topup_amount)
async def process_credit_topup(message: types.Message, state: FSMContext, **kwargs):
    try:
        amount = int(message.text)
        user_id = message.from_user.id
        user_info = await data_manager.get_user(user_id)
        credit_limit = user_info.get('credit_limit', 0)
        current_debt = user_info.get('debt', 0)
        if amount <= 0 or amount > (credit_limit - current_debt):
            await message.answer(f"مبلغ باید بین 1 تا {credit_limit - current_debt:,} تومان باشد.")
            return
        await data_manager.update_user_debt(user_id, amount, operation="add")
        await data_manager.update_user_balance(user_id, amount, operation="add")
        await message.answer(f"✅ شارژ نسیه {amount:,} تومان با موفقیت انجام شد.")
        await message.answer("به منوی اصلی بازگشتید.", reply_markup=rep_menu)
    except ValueError:
        await message.answer("لطفاً عدد معتبر وارد کنید.")
    await state.clear()


@router.callback_query(F.data == "pay_debt")
async def pay_debt_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    user_id = callback.from_user.id
    user_info = await data_manager.get_user(user_id)
    debt = user_info.get('debt', 0)
    if debt == 0:
        await callback.message.edit_text("شما بدهی ندارید. ✅")
        return
    await callback.message.edit_text(f"مبلغ بدهی شما: {debt:,} تومان\nلطفاً مبلغ پرداختی را وارد کنید:")
    await state.set_state(UserStates.waiting_for_debt_payment_amount)


@router.message(UserStates.waiting_for_debt_payment_amount)
async def get_debt_payment_amount(message: types.Message, state: FSMContext, **kwargs):
    try:
        amount = int(message.text)
        user_id = message.from_user.id
        user_info = await data_manager.get_user(user_id)
        debt = user_info.get('debt', 0)
        if amount <= 0 or amount > debt:
            await message.answer(f"مبلغ باید بین 1 تا {debt:,} تومان باشد.")
            return
        await state.update_data(pay_amount=amount)
        await message.answer("لطفاً تصویر فیش پرداخت را ارسال کنید:")
        await state.set_state(UserStates.waiting_for_debt_payment_photo)
    except Exception as e:
        await message.answer("خطایی در پردازش مبلغ رخ داد. لطفاً دوباره تلاش کنید.")
        logger.error(f"Error in get_debt_payment_amount: {e}")


@router.message(UserStates.waiting_for_debt_payment_photo)
async def get_debt_payment_photo(message: types.Message, state: FSMContext, **kwargs):
    if not message.photo:
        await message.answer("لطفاً یک عکس ارسال کنید.")
        return
    state_data = await state.get_data()
    amount = state_data['pay_amount']
    user_id = message.from_user.id
    file = await bot.get_file(message.photo[-1].file_id)
    file_path = file.file_path
    safe_id = hashlib.md5(str(user_id).encode()).hexdigest()[:8]
    timestamp = int(datetime.datetime.now().timestamp())
    filename = f"debt_{safe_id}_{timestamp}.jpg"
    local_path = os.path.join(UPLOADS_DIR, filename)
    await bot.download_file(file_path, local_path)
    mime = mimetypes.guess_type(local_path)[0]
    if not mime or not mime.startswith('image/'):
        os.remove(local_path)
        await message.answer("❌ فایل ارسالی معتبر نیست. لطفاً یک تصویر واقعی ارسال کنید.")
        return
    payment_id = f"pay_{random.randint(100000, 999999)}"
    selected_bank = await data_manager.get_default_bank_account()
    await data_manager.create_debt_payment(user_id, amount, filename, payment_id, target_bank_id=(selected_bank or {}).get('id', 0))
    await schedule_photo_deletion(filename, 30, user_id, "پرداخت بدهی")

    admin_msg = (
        f"💸 **پرداخت بدهی**\n"
        f"**کاربر:** {escape_markdown(message.from_user.full_name)} (ID: `{user_id}`)\n"
        f"**مبلغ:** {amount:,} تومان\n"
        f"**شناسه پرداخت:** `{payment_id}`"
    )
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                ikb_btn(text="✅ تأیید", callback_data=f"approve_payment_{payment_id}_{amount}_{(selected_bank or {}).get('id', 0)}"),
                ikb_btn(text="❌ رد", callback_data=f"reject_payment_{payment_id}_{(selected_bank or {}).get('id', 0)}")
            ]
        ]
    )
    await notify_financial_admins_and_admin(admin_msg, message.photo[-1].file_id, buttons, target_manager_user_id=(selected_bank or {}).get('user_id', 0), payment_id=payment_id)
    await message.answer("✅ فیش پرداخت ارسال شد. پس از تأیید، بدهی شما کاهش خواهد یافت.")
    await state.clear()

# =================================================================
