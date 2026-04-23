import datetime
import os
import csv
import shutil
import time

from aiogram import Router, types
from aiogram.types import BufferedInputFile

from app import bot, data_manager
from config import ADMIN_ID, BACKUP_DIR, logger
from keyboards.inline import start_button
from keyboards.reply import admin_main_menu, launch_reply_menu, user_main_menu
from utils.formatters import escape_markdown, format_persian_date, get_payment_method_label
from utils.telegram_utils import safe_send_message
router = Router()

# 20. هندلرهای مدیریت خطا و پیام‌های غیرمتنی
# =================================================================
@router.message()
async def handle_unknown_messages(message: types.Message, **kwargs):
    if await data_manager.is_admin(message.from_user.id):
        await message.answer("دستور نامعتبر. لطفاً از منوی ادمین استفاده کنید.", reply_markup=admin_main_menu)
    else:
        user_info = await data_manager.get_user(message.from_user.id)
        if not user_info or not user_info.get('is_approved'):
            await message.answer("لطفاً برای شروع، روی دکمه زیر کلیک کنید.", reply_markup=start_button)
            await message.answer("یا از دکمه زیر استفاده کنید.", reply_markup=launch_reply_menu)
        else:
            await message.answer("دستور نامعتبر. لطفاً از منوی اصلی استفاده کنید.", reply_markup=user_main_menu)

@router.callback_query()
async def handle_unknown_callbacks(callback: types.CallbackQuery, **kwargs):
    await callback.answer("❌ این دکمه منقضی شده یا معتبر نیست.")

# =================================================================
# 21. اجرای ربات (با job پاکسازی فایل‌های منقضی)
# =================================================================
def _write_csv_file(path_value: str, headers: list, rows: list):
    with open(path_value, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)

async def export_users_snapshot_file(timestamp: str) -> str:
    users = await data_manager.get_export_users_rows()
    path_value = os.path.join(BACKUP_DIR, f"users_snapshot_{timestamp}.csv")
    headers = ['user_id', 'full_name', 'store_name', 'phone_number', 'phone_verified', 'balance', 'is_rep', 'debt', 'credit_limit', 'is_approved', 'banned', 'registration_date']
    rows = [[u.get('user_id'), u.get('full_name'), u.get('store_name'), u.get('phone_number'), int(bool(u.get('phone_verified'))), u.get('balance'), int(bool(u.get('is_rep'))), u.get('debt'), u.get('credit_limit'), int(bool(u.get('is_approved'))), int(bool(u.get('banned'))), u.get('registration_date')] for u in users]
    _write_csv_file(path_value, headers, rows)
    return path_value

async def export_products_snapshot_file(timestamp: str) -> str:
    products = await data_manager.get_export_products_rows()
    path_value = os.path.join(BACKUP_DIR, f"products_snapshot_{timestamp}.csv")
    headers = ['category_id', 'category_name', 'product_id', 'product_name', 'price', 'stock', 'description']
    rows = [[p.get('category_id'), p.get('category_name'), p.get('product_id'), p.get('product_name'), p.get('price'), p.get('stock'), p.get('description')] for p in products]
    _write_csv_file(path_value, headers, rows)
    return path_value

async def cleanup_backup_exports(max_age_days: int = 7):
    prefixes = ('backup_', 'database_backup_', 'users_snapshot_', 'products_snapshot_')
    for name in os.listdir(BACKUP_DIR):
        if not name.startswith(prefixes):
            continue
        file_path = os.path.join(BACKUP_DIR, name)
        try:
            if time.time() - os.path.getmtime(file_path) > max_age_days * 24 * 3600:
                os.remove(file_path)
        except Exception:
            pass

async def nightly_admin_update():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"database_backup_{timestamp}.db")
    try:
        shutil.copy2(data_manager.db_path, backup_file)
        users_file = await export_users_snapshot_file(timestamp)
        products_file = await export_products_snapshot_file(timestamp)
        summary = await data_manager.get_sales_summary(days=1)
        threshold = int(await data_manager.get_setting('low_stock_threshold') or '5')
        low = await data_manager.get_low_stock_products(threshold)
        text = (
            f"🌙 گزارش و بکاپ شبانه\n"
            f"تاریخ: {format_persian_date(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}\n"
            f"کاربران جدید 24 ساعت گذشته: {summary['new_users']}\n"
            f"خرید موفق 24 ساعت گذشته: {summary['purchase_count']}\n"
            f"فروش 24 ساعت گذشته: {summary['total_sales']:,} تومان\n"
            f"پرداخت‌های معلق: {summary['pending_payments']}\n"
            f"تیکت‌های باز: {summary['open_tickets']}\n"
            f"محصولات کم‌موجودی (<= {threshold}): {len(low)}"
        )
        await safe_send_message(ADMIN_ID, text)
        for path_value in (backup_file, users_file, products_file):
            if os.path.exists(path_value):
                with open(path_value, 'rb') as f:
                    await bot.send_document(ADMIN_ID, BufferedInputFile(f.read(), filename=os.path.basename(path_value)))
        await cleanup_backup_exports()
        logger.info(f"Nightly admin update created: {backup_file}")
    except Exception as e:
        logger.error(f"Failed to create nightly admin update: {e}")

async def send_pending_payments_alert():
    """Send a periodic reminder for all unresolved pending payments.

    A payment must remain in this reminder list until an admin explicitly
    approves or rejects it. The reminder interval is controlled by the
    scheduler settings, not by the age of the payment.
    """
    payments = await data_manager.get_all_debt_payments()
    pending = [p for p in payments if (p.get('status') or '').lower() == 'pending']
    if pending:
        preview = "\n".join(
            [
                f"- `{p['payment_id']}` | {int(p.get('amount') or 0):,} تومان | {get_payment_method_label(p.get('payment_method'))}"
                for p in pending[:10]
            ]
        )
        more = ''
        if len(pending) > 10:
            more = f"\n... و {len(pending) - 10} مورد دیگر"
        await safe_send_message(
            ADMIN_ID,
            f"⏰ {len(pending)} پرداخت معلق در انتظار تعیین تکلیف دارید:\n{preview}{more}",
            parse_mode='Markdown',
        )

async def send_weekly_debt_report():
    debtors = await data_manager.get_all_debtors()
    if not debtors:
        report_text = "📊 **گزارش هفتگی بدهی:**\n✅ هیچ نماینده بدهکاری وجود ندارد."
        await bot.send_message(ADMIN_ID, report_text, parse_mode="Markdown")
        return
    messages = []
    current_msg = "📊 **گزارش هفتگی بدهی:**\n"
    total_debt = 0
    for debtor in debtors:
        line = f"• {escape_markdown(debtor.get('full_name', 'ناشناس'))}: {debtor.get('debt', 0):,} تومان\n"
        if len(current_msg) + len(line) + 50 > 4096:
            messages.append(current_msg)
            current_msg = line
        else:
            current_msg += line
        total_debt += debtor.get('debt', 0)
    current_msg += f"\n💰 **مجموع بدهی‌ها:** {total_debt:,} تومان"
    messages.append(current_msg)
    for msg in messages:
        await bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")

async def cleanup_files_job():
    await data_manager.cleanup_expired_files()
