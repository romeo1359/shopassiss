import datetime
import io

import qrcode
from aiogram import F, Router, types
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from app import bot, data_manager
from config import ADMIN_ID, BUTTON_STYLE_SUCCESS, logger
from keyboards.inline import ikb_btn
from utils.formatters import escape_markdown, escape_markdown_code, format_persian_date, normalize_server_address
from utils.telegram_utils import check_rate_limit, rate_limit, send_account_with_copy_buttons
router = Router()

# 13. هندلرهای فروشگاه (با بررسی مجدد موجودی)
# =================================================================
@router.message(F.text == "🛒 فروشگاه")
@rate_limit(10)
async def show_store(message: types.Message, **kwargs):
    bot_status = await data_manager.get_setting('bot_status')
    shop_status = await data_manager.get_setting('shop_status')
    if bot_status == "off" or shop_status == "off":
        await message.answer("فروشگاه در حال حاضر غیرفعال است. 🛠️")
        return
    categories = await data_manager.get_categories()
    if not categories:
        await message.answer("هنوز محصولی برای نمایش وجود ندارد. 😔")
        return
    page = 0
    per_page = 5
    total_pages = (len(categories) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    cats_page = categories[start:end]
    buttons = []
    for cat in cats_page:
        buttons.append([InlineKeyboardButton(text=cat['name'], callback_data=f"show_category_{cat['id']}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(ikb_btn(text="⏪ قبلی", callback_data=f"store_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(ikb_btn(text="⏩ بعدی", callback_data=f"store_page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    inline_buttons = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(f"لطفا گروه کالای مورد نظر را انتخاب کنید: 👇 (صفحه {page+1} از {total_pages})", reply_markup=inline_buttons)

@router.callback_query(F.data.startswith("store_page_"))
async def store_page_nav(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    page = int(callback.data.split('_')[-1])
    categories = await data_manager.get_categories()
    per_page = 5
    start = page * per_page
    end = start + per_page
    cats_page = categories[start:end]
    buttons = []
    for cat in cats_page:
        buttons.append([InlineKeyboardButton(text=cat['name'], callback_data=f"show_category_{cat['id']}")])
    total_pages = (len(categories) + per_page - 1) // per_page
    nav_buttons = []
    if page > 0:
        nav_buttons.append(ikb_btn(text="⏪ قبلی", callback_data=f"store_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(ikb_btn(text="⏩ بعدی", callback_data=f"store_page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    inline_buttons = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(f"لطفا گروه کالای مورد نظر را انتخاب کنید: 👇 (صفحه {page+1} از {total_pages})", reply_markup=inline_buttons)

@router.callback_query(F.data.startswith("show_category_"))
async def show_products_in_category(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    category_id = int(callback.data.split('_')[-1])
    category = await data_manager.get_category_by_id(category_id)
    if not category or not category['products']:
        await callback.message.edit_text(f"گروه '{category['name']}' محصولی ندارد. 😔")
        return
    page = 0
    per_page = 5
    products = category['products']
    total_pages = (len(products) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    prods_page = products[start:end]
    buttons = []
    for product in prods_page:
        stock = len(product['accounts'])
        button_text = f"{product['name']} - موجودی: {stock} - قیمت: {int(product.get('price', 0) or 0):,} تومان"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"details_{category['id']}_{product['id']}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(ikb_btn(text="⏪ قبلی", callback_data=f"category_page_{category_id}_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(ikb_btn(text="⏩ بعدی", callback_data=f"category_page_{category_id}_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([ikb_btn(text="🔙 بازگشت به فروشگاه", callback_data="back_to_store")])
    inline_buttons = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(f"محصولات گروه '{category['name']}': (صفحه {page+1} از {total_pages})", reply_markup=inline_buttons)

@router.callback_query(F.data.startswith("category_page_"))
async def category_page_nav(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    parts = callback.data.split('_')
    category_id = int(parts[2])
    page = int(parts[3])
    category = await data_manager.get_category_by_id(category_id)
    if not category:
        await callback.answer("گروه یافت نشد.")
        return
    products = category['products']
    per_page = 5
    start = page * per_page
    end = start + per_page
    prods_page = products[start:end]
    total_pages = (len(products) + per_page - 1) // per_page
    buttons = []
    for product in prods_page:
        stock = len(product['accounts'])
        button_text = f"{product['name']} - موجودی: {stock} - قیمت: {int(product.get('price', 0) or 0):,} تومان"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"details_{category['id']}_{product['id']}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(ikb_btn(text="⏪ قبلی", callback_data=f"category_page_{category_id}_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(ikb_btn(text="⏩ بعدی", callback_data=f"category_page_{category_id}_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([ikb_btn(text="🔙 بازگشت به فروشگاه", callback_data="back_to_store")])
    inline_buttons = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(f"محصولات گروه '{category['name']}': (صفحه {page+1} از {total_pages})", reply_markup=inline_buttons)

@router.callback_query(F.data == "back_to_store")
async def back_to_store(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    await show_store(callback.message)

@router.callback_query(F.data.startswith("details_"))
async def show_product_details(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    _, category_id, product_id = callback.data.split('_')
    category_id = int(category_id)
    product_id = int(product_id)
    category = await data_manager.get_category_by_id(category_id)
    product = None
    for p in category['products']:
        if p['id'] == product_id:
            product = p
            break
    if not product:
        await callback.message.edit_text("محصول یافت نشد.")
        return
    user_id = callback.from_user.id
    user_info = await data_manager.get_user(user_id)
    discount_percentage = user_info.get('discount_percentage', 0) if user_info.get('is_rep') else 0
    base_price = int(product.get('price', 0) or 0)
    if base_price > 0:
        discounted_price = int(base_price - (base_price * discount_percentage / 100))
        raw_price_text = f"`{base_price:,}` تومان"
        discount_price_text = f"`{discounted_price:,}` تومان"
    else:
        raw_price_text = "`متغیر`"
        discount_price_text = "`پس از ثبت خرید محاسبه می‌شود`"
    message_text = (
        f"**مشخصات محصول:**\n"
        f"**نام:** `{escape_markdown(product['name'])}`\n"
        f"**قیمت نمایش داده شده:** {raw_price_text}\n"
        f"**قیمت شما:** {discount_price_text}"
    )
    if product.get('description'):
        message_text += f"\n**توضیحات:**\n{escape_markdown(product['description'])}"
    if product.get('openvpn_server'):
        message_text += f"\n**سرور مشترک OpenVPN:** `{escape_markdown_code(normalize_server_address(product['openvpn_server']))}`"
    if product.get('openvpn_download_link'):
        message_text += "\n**لینک دانلود کلاینت:** از طریق دکمه‌های بعد از خرید ارسال می‌شود"
    if len(product['accounts']) > 0:
        message_text += f"\n**موجودی:** `{len(product['accounts'])}` عدد ✅"
    else:
        message_text += f"\n**موجودی:** `ناموجود` ❌"
    buttons = []
    if len(product['accounts']) > 0:
        buttons.append([InlineKeyboardButton(text='🛒 خرید', callback_data=f'buy_{category_id}_{product_id}')])
    else:
        buttons.append([ikb_btn(text='🔔 خبرم کن وقتی موجود شد', style=BUTTON_STYLE_SUCCESS, callback_data=f'notify_when_available_{product_id}')])
    buttons.append([ikb_btn(text='🔙 بازگشت به محصولات', callback_data=f'show_category_{category_id}')])
    reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")

@router.callback_query(F.data.startswith('notify_when_available_'))
async def notify_when_available(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    try:
        product_id = int((callback.data or '').split('notify_when_available_', 1)[1])
    except Exception:
        await callback.message.edit_text('❌ محصول نامعتبر است.')
        return
    await data_manager.subscribe_product_stock(callback.from_user.id, product_id)
    await callback.message.edit_text('✅ ثبت شد. به محض موجود شدن این محصول، به شما اطلاع می‌دهیم.')

async def _execute_product_purchase(callback: types.CallbackQuery, category_id: int, product_id: int):
    bot_status = await data_manager.get_setting('bot_status')
    shop_status = await data_manager.get_setting('shop_status')
    if bot_status == "off" or shop_status == "off":
        await callback.message.edit_text("فروشگاه در حال حاضر غیرفعال است. 🛠️")
        return
    user_id = callback.from_user.id
    user_info = await data_manager.get_user(user_id)
    if not user_info:
        await callback.message.edit_text("اطلاعات کاربری شما یافت نشد. لطفا ربات را دوباره /start کنید. 🔄")
        return
    category = await data_manager.get_category_by_id(category_id)
    product = None
    for p in (category or {}).get('products', []):
        if p['id'] == product_id:
            product = p
            break
    if not product:
        await callback.message.edit_text("محصول مورد نظر یافت نشد. 😔")
        return
    if len(product['accounts']) == 0:
        await data_manager.subscribe_product_stock(user_id, product_id)
        await callback.message.edit_text('متاسفانه موجودی این محصول به پایان رسیده است. 😔\nشما در لیست اعلان موجود شدن ثبت شدید.')
        await bot.send_message(ADMIN_ID, f"⚠️ موجودی محصول «{product['name']}» در گروه «{category['name']}» به پایان رسید.")
        return
    discount_percentage = user_info.get('discount_percentage', 0) if user_info.get('is_rep') else 0
    base_price = int(product.get('price', 0) or 0)
    final_price = int(base_price - (base_price * discount_percentage / 100))
    user_balance = user_info.get('balance', 0)
    if user_balance < final_price:
        shortage = int(final_price) - int(user_balance)
        await callback.message.edit_text(
            f"موجودی کیف پول شما کافی نیست. ❌\n"
            f"موجودی شما: {user_balance:,} تومان\n"
            f"قیمت محصول: {int(final_price):,} تومان\n"
            f"میزان کسری: {shortage:,} تومان"
        )
        return
    purchased_account = await data_manager.pop_account_from_product(product_id)
    if purchased_account is None:
        await callback.message.edit_text("متاسفانه محصول در لحظه آخر به اتمام رسید. لطفاً دوباره تلاش کنید.")
        return
    await data_manager.update_user_balance(user_id, final_price, operation="subtract")
    tracking_code = await data_manager.get_unique_tracking_code()
    await data_manager.add_purchase(user_id, product['name'], int(final_price), purchased_account, tracking_code, bank_account_number='از موجودی کیف پول', payment_method='wallet', approved_by=0, group_name=category.get('name', ''))
    admin_report = (
        f"🛒 **خرید جدید!**\n"
        f"**کاربر:** {escape_markdown(user_info.get('full_name', 'ناشناس'))} (ID: `{user_id}`)\n"
        f"**گروه:** {escape_markdown(category.get('name', 'نامشخص'))}\n"
        f"**محصول:** {escape_markdown(product['name'])}\n"
        f"**قیمت:** {int(final_price):,} تومان\n"
        f"**شماره پیگیری:** `{tracking_code}`\n"
        f"**تاریخ:** {escape_markdown(format_persian_date(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))}\n"
        f"**حساب مقصد:** از موجودی کیف پول\n"
        f"**اکانت:**\n`{escape_markdown(purchased_account)}`"
    )
    await bot.send_message(ADMIN_ID, admin_report, parse_mode="Markdown")
    if purchased_account.startswith(("vmess://", "vless://", "trojan://", "ss://", "ssr://")):
        try:
            img = qrcode.make(purchased_account)
            buffer = io.BytesIO()
            img.save(buffer, 'PNG')
            qr_bytes = buffer.getvalue()
            await bot.send_photo(ADMIN_ID, photo=BufferedInputFile(qr_bytes, filename="qrcode_admin.png"), caption=f"QR Code خرید جدید - شماره پیگیری: {tracking_code}")
        except Exception as e:
            logger.error(f"Failed to send QR to admin: {e}")
            await bot.send_message(ADMIN_ID, f"⚠️ خطا در ساخت QR Code برای خرید جدید: {e}")
    purchase_message = (
        f"✅ <b>خرید شما با موفقیت انجام شد.</b>\n"
        f"<b>محصول:</b> {product['name']}\n"
        f"<b>قیمت نهایی:</b> {int(final_price):,} تومان\n"
        f"<b>شماره پیگیری:</b> <code>{tracking_code}</code>\n"
        f"<b>اطلاعات اکانت شما:</b>\n"
    )
    await callback.message.edit_text(purchase_message, parse_mode="HTML")
    account_dict = {}
    lines = purchased_account.split('\n')
    for line in lines:
        if ': ' in line:
            key, val = line.split(': ', 1)
            account_dict[key] = val
    await send_account_with_copy_buttons(callback.message.chat.id, {
        'account_type': 'openvpn' if 'نام کاربری' in account_dict else 'v2ray' if purchased_account.startswith(('vmess://', 'vless://', 'trojan://')) else 'other',
        'username': account_dict.get('نام کاربری', ''),
        'password': account_dict.get('رمز عبور', ''),
        'secret': account_dict.get('کلید (Secret)', ''),
        'server': account_dict.get('آدرس سرور', ''),
        'port': '',
        'config': purchased_account if purchased_account.startswith(('vmess://', 'vless://', 'trojan://')) else account_dict.get('فایل کانفیگ', '')
    })
    if purchased_account.startswith(("vmess://", "vless://", "trojan://", "ss://", "ssr://")):
        try:
            img = qrcode.make(purchased_account)
            buffer = io.BytesIO()
            img.save(buffer, 'PNG')
            await bot.send_photo(callback.from_user.id, photo=BufferedInputFile(buffer.getvalue(), filename="qrcode.png"), caption="✅ کد QR اکانت شما:")
        except Exception as e:
            logger.error(f"Failed to generate QR code: {e}")
            await bot.send_message(callback.from_user.id, "خطا در ساخت QR Code. 😔")

@router.callback_query(F.data.startswith("buy_"))
async def handle_buy_callback(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    if not await check_rate_limit(callback.from_user.id):
        await callback.answer("لطفاً کمی صبر کنید و سپس دوباره تلاش کنید.", show_alert=True)
        return
    _, category_id, product_id = callback.data.split('_')
    category_id = int(category_id)
    product_id = int(product_id)
    category = await data_manager.get_category_by_id(category_id)
    product = None
    for p in (category or {}).get('products', []):
        if p['id'] == product_id:
            product = p
            break
    if not product:
        await callback.message.edit_text("محصول مورد نظر یافت نشد. 😔")
        return
    if product.get('description'):
        extra_terms = (await data_manager.get_setting('buy_terms') or '').strip()
        text = (
            f"**قبل از خرید، توضیحات زیر را کامل مطالعه کنید:**\n\n"
            f"{escape_markdown(product['description'])}\n\n"
        )
        if extra_terms:
            text += f"**قوانین کلی خرید:**\n{escape_markdown(extra_terms)}\n\n"
        text += "در صورت قبول توضیحات و شرایط این محصول، روی دکمه تأیید بزنید."
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [ikb_btn(text="✅ توضیحات را خواندم و قبول دارم", style=BUTTON_STYLE_SUCCESS, callback_data=f"accept_buy_{category_id}_{product_id}")],
            [ikb_btn(text="🔙 بازگشت", callback_data=f"details_{category_id}_{product_id}")]
        ])
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)
        return
    await _execute_product_purchase(callback, category_id, product_id)

@router.callback_query(F.data.startswith("accept_buy_"))
async def accept_buy_callback(callback: types.CallbackQuery, **kwargs):
    await callback.answer("تأیید شد. خرید در حال انجام است.")
    _, _, category_id, product_id = callback.data.split('_')
    await _execute_product_purchase(callback, int(category_id), int(product_id))

# =================================================================
