import os
import time

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app import bot, data_manager
from config import ADMIN_ID, BUTTON_STYLE_PRIMARY, UPLOADS_DIR
from states.admin_states import AdminStates
from keyboards.inline import cancel_only_button, confirm_delete_buttons, ikb_btn
from keyboards.reply import admin_main_menu
from utils.formatters import escape_markdown, normalize_server_address
from utils.parsers import parse_openvpn_defaults_text, parse_price_input
from utils.telegram_utils import admin_only, safe_edit_callback_message, safe_send_message
router = Router()

# 17. مدیریت کالاها
# =================================================================
@router.message(F.text == "📦 مدیریت کالاها")
async def handle_inventory_management(message: types.Message, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        return
    inline_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="➕ افزودن گروه کالا", callback_data="add_category_start")],
            [ikb_btn(text="📝 مشاهده/ویرایش کالاها", callback_data="view_products_start")],
        ]
    )
    await message.answer("پنل مدیریت کالاها: 📦", reply_markup=inline_buttons)

@router.callback_query(F.data == "add_category_start")
@admin_only
async def add_category_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_text("لطفاً نام گروه کالای جدید را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_category_name)

@router.message(AdminStates.waiting_for_category_name)
async def add_category_name(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    category_name = message.text.strip()
    success = await data_manager.add_category(category_name)
    if success:
        await message.answer(f"✅ گروه کالای '{category_name}' با موفقیت اضافه شد.", reply_markup=admin_main_menu)
    else:
        await message.answer("این نام گروه قبلاً استفاده شده است. لطفاً نام دیگری انتخاب کنید.")
    await state.clear()

@router.callback_query(F.data == "view_products_start")
@admin_only
async def view_products_start(callback: types.CallbackQuery, **kwargs):
    categories = await data_manager.get_categories()
    if not categories:
        await callback.message.edit_text("هنوز گروه کالایی ایجاد نشده است. 😔")
        return
    page = 0
    per_page = 5
    total_pages = (len(categories) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    cats_page = categories[start:end]
    buttons = [
        [InlineKeyboardButton(text=cat['name'], callback_data=f"select_category_to_manage_{cat['id']}")]
        for cat in cats_page
    ]
    nav_buttons = []
    if page > 0:
        nav_buttons.append(ikb_btn(text="⏪ قبلی", callback_data=f"cat_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(ikb_btn(text="⏩ بعدی", callback_data=f"cat_page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([ikb_btn(text="🔙 بازگشت", style=BUTTON_STYLE_PRIMARY, callback_data="back_to_main")])
    inline_buttons = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(f"لطفاً گروه کالای مورد نظر را انتخاب کنید: (صفحه {page+1} از {total_pages})", reply_markup=inline_buttons)

@router.callback_query(F.data.startswith("cat_page_"))
@admin_only
async def cat_page_nav(callback: types.CallbackQuery, **kwargs):
    page = int(callback.data.split('_')[-1])
    categories = await data_manager.get_categories()
    per_page = 5
    start = page * per_page
    end = start + per_page
    cats_page = categories[start:end]
    total_pages = (len(categories) + per_page - 1) // per_page
    buttons = [
        [InlineKeyboardButton(text=cat['name'], callback_data=f"select_category_to_manage_{cat['id']}")]
        for cat in cats_page
    ]
    nav_buttons = []
    if page > 0:
        nav_buttons.append(ikb_btn(text="⏪ قبلی", callback_data=f"cat_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(ikb_btn(text="⏩ بعدی", callback_data=f"cat_page_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([ikb_btn(text="🔙 بازگشت", style=BUTTON_STYLE_PRIMARY, callback_data="back_to_main")])
    inline_buttons = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(f"لطفاً گروه کالای مورد نظر را انتخاب کنید: (صفحه {page+1} از {total_pages})", reply_markup=inline_buttons)

@router.callback_query(F.data.startswith("select_category_to_manage_"))
@admin_only
async def manage_category(callback: types.CallbackQuery, **kwargs):
    category_id = int(callback.data.split('_')[-1])
    category = await data_manager.get_category_by_id(category_id)
    if not category:
        await callback.message.edit_text("گروه یافت نشد.")
        return
    total_accounts = sum(len(p.get('accounts', [])) for p in category['products'])
    response_text = f"**مدیریت گروه: {escape_markdown(category['name'])}** 📦\n"
    response_text += f"**تعداد کل اکانت‌های موجود:** {total_accounts} عدد ✅\n"
    response_text += "محصولات موجود:\n"
    if not category['products']:
        response_text += "این گروه کالایی محصولی ندارد. 😔"
    else:
        for product in category['products']:
            response_text += f"  - `{escape_markdown(product['name'])}` (موجودی: {len(product['accounts'])} عدد)\n"
    inline_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="➕ افزودن محصول جدید", callback_data=f"add_product_to_category_{category_id}")],
            [ikb_btn(text="📝 ویرایش/حذف محصولات", callback_data=f"edit_products_in_category_{category_id}")],
            [
                ikb_btn(text="📝 ویرایش نام گروه", callback_data=f"rename_category_{category_id}"),
                ikb_btn(text="🗑️ حذف کامل گروه", callback_data=f"delete_category_{category_id}")
            ],
            [ikb_btn(text="🔙 بازگشت به گروه‌ها", callback_data="view_products_start")]
        ]
    )
    await callback.message.edit_text(response_text, reply_markup=inline_buttons, parse_mode="Markdown")

@router.callback_query(F.data.startswith("delete_category_"))
@admin_only
async def delete_category_request(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    cat_id = int(callback.data.split('_')[-1])
    await state.update_data(delete_category_id=cat_id)
    await callback.message.edit_text("⚠️ آیا از حذف این گروه کالا اطمینان دارید؟ تمام محصولات و اکانت‌های آن نیز حذف خواهند شد.", reply_markup=confirm_delete_buttons)
    await state.set_state(AdminStates.waiting_for_delete_confirmation)

@router.callback_query(F.data == "confirm_delete_yes", AdminStates.waiting_for_delete_confirmation)
@admin_only
async def confirm_delete_category(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    data = await state.get_data()
    cat_id = data.get('delete_category_id')
    if cat_id:
        await data_manager.delete_category(cat_id)
        await callback.message.edit_text("✅ گروه کالا با موفقیت حذف شد.")
    else:
        await callback.message.edit_text("❌ خطا در حذف.")
    await state.clear()

@router.callback_query(F.data == "confirm_delete_no", AdminStates.waiting_for_delete_confirmation)
@admin_only
async def cancel_delete_category(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_text("❌ عملیات حذف لغو شد.")
    await state.clear()

@router.callback_query(F.data.startswith("rename_category_"))
@admin_only
async def rename_category_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    cat_id = int(callback.data.split('_')[-1])
    await state.update_data(rename_category_id=cat_id)
    await callback.message.edit_text("لطفاً نام جدید گروه را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_rename_category)

@router.message(AdminStates.waiting_for_rename_category)
async def rename_category_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    new_name = message.text.strip()
    data = await state.get_data()
    cat_id = data.get('rename_category_id')
    if cat_id:
        await data_manager.rename_category(cat_id, new_name)
        await message.answer(f"✅ نام گروه با موفقیت به '{new_name}' تغییر یافت.")
    else:
        await message.answer("❌ خطا در تغییر نام.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data.startswith("add_product_to_category_"))
@admin_only
async def add_product_to_category_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    category_id = int(callback.data.split('_')[-1])
    await state.update_data(product_info={"category_id": category_id})
    await safe_edit_callback_message(callback, "لطفاً نام محصول جدید را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_new_product_name)

@router.message(AdminStates.waiting_for_new_product_name)
async def add_new_product_name(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    product_name = message.text.strip()
    product_info = (await state.get_data()).get('product_info', {})
    product_info["name"] = product_name
    await state.update_data(product_info=product_info)
    await message.answer("لطفاً قیمت ثابت محصول را وارد کنید (مثال: 120000):", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_new_product_price)

@router.message(AdminStates.waiting_for_new_product_price)
async def add_new_product_price(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    price_value = parse_price_input(message.text)
    if not price_value:
        await message.answer("❌ فرمت قیمت نامعتبر است. فقط عدد مثبت وارد کنید. مثال: 120000")
        return
    product_info = (await state.get_data()).get('product_info', {})
    product_info["price"] = int(price_value)
    await state.update_data(product_info=product_info)
    await message.answer("لطفاً توضیحات محصول را وارد کنید (اختیاری):", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_product_description)

@router.message(AdminStates.waiting_for_product_description)
async def add_product_description(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    description = message.text.strip()
    product_info = (await state.get_data()).get('product_info', {})
    product_info["description"] = description
    category_id = product_info["category_id"]
    name = product_info["name"]
    price = product_info["price"]
    product_id = await data_manager.add_product_to_category(category_id, name, price, description)
    await state.update_data(product_info=product_info, edit_product_id=product_id, accounts=[], openvpn_defaults_mode='create')
    await message.answer(
        "اگر این محصول OpenVPN است، تنظیمات مشترک آن را در سه خط به این ترتیب ارسال کنید:\n"
        "server\nsecret\ndownload_link\n\n"
        "در غیر این صورت یا برای رد شدن از این مرحله، فقط یک خط تیره (-) بفرستید.",
        reply_markup=cancel_only_button
    )
    await state.set_state(AdminStates.waiting_for_openvpn_config)

@router.callback_query(F.data.startswith("edit_products_in_category_"))
@admin_only
async def edit_products_in_category(callback: types.CallbackQuery, **kwargs):
    category_id = int(callback.data.split('_')[-1])
    category = await data_manager.get_category_by_id(category_id)
    if not category or not category['products']:
        await callback.message.edit_text("این گروه محصولی ندارد.")
        return
    buttons = []
    for product in category['products']:
        buttons.append([InlineKeyboardButton(text=f"✏️ {product['name']}", callback_data=f"edit_product_{product['id']}")])
    buttons.append([ikb_btn(text="🔙 بازگشت", callback_data=f"select_category_to_manage_{category_id}")])
    await safe_edit_callback_message(callback, "لطفاً محصول مورد نظر برای ویرایش را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data == "edit_product_price")
@admin_only
async def edit_product_price_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_text("لطفاً قیمت جدید محصول را به صورت یک عدد ثابت وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_new_product_price_edit)

@router.message(AdminStates.waiting_for_new_product_price_edit)
async def edit_product_price_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    price_value = parse_price_input(message.text)
    if not price_value:
        await message.answer("لطفاً قیمت معتبر و مثبت وارد کنید.")
        return
    state_data = await state.get_data()
    product_id = state_data.get('edit_product_id')
    if product_id:
        await data_manager.update_product_price(product_id, int(price_value))
        await message.answer("✅ قیمت محصول با موفقیت به‌روزرسانی شد.")
    else:
        await message.answer("❌ خطا: شناسه محصول یافت نشد.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data == "edit_product_desc")
@admin_only
async def edit_product_desc_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_text("لطفاً توضیحات جدید محصول را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_product_description_edit)

@router.message(AdminStates.waiting_for_product_description_edit)
async def edit_product_desc_process(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    new_desc = message.text.strip()
    state_data = await state.get_data()
    product_id = state_data.get('edit_product_id')
    if product_id:
        await data_manager.update_product_description(product_id, new_desc)
        await message.answer("✅ توضیحات محصول با موفقیت به‌روزرسانی شد.")
    else:
        await message.answer("❌ خطا: شناسه محصول یافت نشد.")
    await state.clear()
    await message.answer("به منوی ادمین بازگشتید.", reply_markup=admin_main_menu)

@router.callback_query(F.data == "delete_product_confirm")
@admin_only
async def delete_product_confirm(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    state_data = await state.get_data()
    product_id = state_data.get('edit_product_id')
    if product_id:
        await data_manager.delete_product(product_id)
        await callback.message.edit_text("✅ محصول با موفقیت حذف شد.")
    else:
        await callback.message.edit_text("❌ خطا: محصول یافت نشد.")
    await state.clear()

@router.callback_query(F.data.regexp(r"^edit_product_\d+$"))
@admin_only
async def edit_product_menu(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    parts = callback.data.split('_')
    if len(parts) < 3:
        await callback.answer("دستور نامعتبر")
        return
    try:
        product_id = int(parts[-1])
    except ValueError:
        await callback.answer()
        return
    product = await data_manager.get_product_by_id(product_id)
    if not product:
        await callback.message.edit_text("❌ محصول یافت نشد.")
        return
    await state.update_data(edit_product_id=product_id)
    category_id = product.get('category_id')
    buttons = [
        [ikb_btn(text="💰 ویرایش قیمت", callback_data="edit_product_price")],
        [ikb_btn(text="📝 ویرایش توضیحات", callback_data="edit_product_desc")],
        [ikb_btn(text="🔐 تنظیمات مشترک OpenVPN", callback_data="edit_product_openvpn_defaults")],
        [ikb_btn(text="➕ افزودن اکانت جدید", callback_data="add_account_to_product")],
        [ikb_btn(text="🗑️ حذف محصول", callback_data="delete_product_confirm")]
    ]
    if category_id is not None:
        buttons.append([ikb_btn(text="🔙 بازگشت", callback_data=f"edit_products_in_category_{category_id}")])
    else:
        buttons.append([ikb_btn(text="🔙 بازگشت به منوی ادمین", callback_data="view_products_start")])
    inline_buttons = InlineKeyboardMarkup(inline_keyboard=buttons)
    await safe_edit_callback_message(callback, f"ویرایش محصول: {product.get('name', 'نامشخص')}", reply_markup=inline_buttons)

@router.callback_query(F.data == "edit_product_openvpn_defaults")
@admin_only
async def edit_product_openvpn_defaults(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    state_data = await state.get_data()
    product_id = state_data.get('edit_product_id')
    if not product_id:
        await callback.message.edit_text("❌ محصول مشخص نیست.")
        return
    product = await data_manager.get_product_by_id(product_id)
    if not product:
        await callback.message.edit_text("❌ محصول یافت نشد.")
        return
    current_text = (
        f"مقادیر فعلی:\n"
        f"server: {product.get('openvpn_server') or '-'}\n"
        f"secret: {product.get('openvpn_secret') or '-'}\n"
        f"download: {product.get('openvpn_download_link') or '-'}\n\n"
        "مقادیر جدید را در سه خط به ترتیب server / secret / download ارسال کنید.\n"
        "برای پاک کردن همه مقادیر، فقط - را بفرستید."
    )
    await state.update_data(openvpn_defaults_mode='edit')
    await safe_edit_callback_message(callback, current_text, reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_openvpn_config)

@router.callback_query(F.data == "add_account_to_product")
@admin_only
async def add_account_to_product_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    state_data = await state.get_data()
    product_id = state_data.get('edit_product_id')
    if not product_id:
        await callback.message.edit_text("❌ محصول برای افزودن اکانت مشخص نشده.")
        return
    await state.update_data(accounts=[])
    await callback.message.edit_text(
        "لطفاً نوع اکانت را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [ikb_btn(text="OpenVPN", callback_data="acc_type_openvpn"), ikb_btn(text="L2TP", callback_data="acc_type_l2tp")],
                [ikb_btn(text="AnyConnect", callback_data="acc_type_anyconnect"), ikb_btn(text="WireGuard", callback_data="acc_type_wireguard")],
                [ikb_btn(text="V2Ray", callback_data="acc_type_v2ray"), ikb_btn(text="سایر", callback_data="acc_type_other")],
                [ikb_btn(text="لغو", callback_data="cancel")]
            ]
        )
    )
    await state.set_state(AdminStates.waiting_for_account_type)

@router.callback_query(F.data.startswith("acc_type_"))
@admin_only
async def select_account_type(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    acc_type = callback.data.split('_')[-1]
    await state.update_data(account_type=acc_type)
    if acc_type == 'openvpn':
        await callback.message.edit_text("لطفاً نام کاربری OpenVPN را وارد کنید (در صورت عدم وجود، خط تیره بزنید):", reply_markup=cancel_only_button)
        await state.set_state(AdminStates.waiting_for_openvpn_username)
    elif acc_type == 'v2ray':
        await callback.message.edit_text("لطفاً لینک V2Ray (vmess:// یا vless://) را وارد کنید:", reply_markup=cancel_only_button)
        await state.set_state(AdminStates.waiting_for_v2ray_link)
    else:
        await callback.message.edit_text("لطفاً اطلاعات اکانت را به صورت یک خط وارد کنید:", reply_markup=cancel_only_button)
        await state.set_state(AdminStates.waiting_for_other_account)

@router.message(AdminStates.waiting_for_openvpn_username)
async def get_openvpn_username(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    username = message.text.strip()
    if username == "-":
        username = ""
    await state.update_data(temp_username=username)
    await message.answer("لطفاً رمز عبور OpenVPN را وارد کنید (در صورت عدم وجود، خط تیره بزنید):", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_openvpn_password)

@router.message(AdminStates.waiting_for_openvpn_password)
async def get_openvpn_password(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    password = message.text.strip()
    if password == "-":
        password = ""
    state_data = await state.get_data()
    product_id = state_data.get('edit_product_id')
    product = await data_manager.get_product_by_id(product_id) if product_id else None
    accounts = state_data.get('accounts', [])
    accounts.append({
        'account_type': 'openvpn',
        'username': state_data.get('temp_username', ''),
        'password': password,
        'secret': (product or {}).get('openvpn_secret', ''),
        'server': (product or {}).get('openvpn_server', ''),
        'port': 0,
        'config': await data_manager.get_latest_openvpn_config(),
        'extra_note': (product or {}).get('openvpn_download_link', '')
    })
    await state.update_data(accounts=accounts, temp_password=password)
    for k in ['temp_username', 'temp_password', 'temp_secret', 'temp_server', 'temp_port', 'temp_config']:
        await state.update_data({k: None})
    await safe_send_message(
        message.chat.id,
        f"✅ اکانت OpenVPN ذخیره شد. تعداد کل: {len(accounts)}\n"
        "فقط نام کاربری و رمز عبور از شما گرفته شد و سایر اطلاعات از تنظیمات خود محصول خوانده می‌شود.\n"
        "آیا می‌خواهید اکانت دیگری اضافه کنید؟",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[ikb_btn(text="بله", callback_data="add_single_account")], [ikb_btn(text="خیر، ثبت نهایی", callback_data="accounts_done")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_product_new_accounts)

@router.message(AdminStates.waiting_for_l2tp_username)
async def get_l2tp_username(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    username = (message.text or '').strip()
    if username == '-':
        username = ''
    await state.update_data(temp_username=username)
    await message.answer("لطفاً رمز عبور L2TP را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_l2tp_password)

@router.message(AdminStates.waiting_for_l2tp_password)
async def get_l2tp_password(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    password = (message.text or '').strip()
    if password == '-':
        password = ''
    state_data = await state.get_data()
    product = await data_manager.get_product_by_id(state_data.get('edit_product_id')) if state_data.get('edit_product_id') else None
    accounts = state_data.get('accounts', [])
    accounts.append({
        'account_type': 'l2tp',
        'username': state_data.get('temp_username', ''),
        'password': password,
        'secret': (product or {}).get('openvpn_secret', ''),
        'server': (product or {}).get('openvpn_server', ''),
        'port': 0,
        'config': '',
        'extra_note': ''
    })
    await state.update_data(accounts=accounts, temp_username=None, temp_password=None)
    await message.answer(
        f"✅ اکانت L2TP ذخیره شد. تعداد کل: {len(accounts)}\nنام کاربری و رمز عبور برای هر اکانت ثبت می‌شود و سکرت/سرور از خود محصول خوانده می‌شود.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text="افزودن اکانت بعدی", callback_data="add_single_account")],[ikb_btn(text="ثبت نهایی", callback_data="accounts_done")]])
    )
    await state.set_state(AdminStates.waiting_for_product_new_accounts)

@router.message(AdminStates.waiting_for_anyconnect_username)
async def get_anyconnect_username(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    username = (message.text or '').strip()
    if username == '-':
        username = ''
    await state.update_data(temp_username=username)
    await message.answer("لطفاً رمز عبور AnyConnect را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_anyconnect_password)

@router.message(AdminStates.waiting_for_anyconnect_password)
async def get_anyconnect_password(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    password = (message.text or '').strip()
    if password == '-':
        password = ''
    await state.update_data(temp_password=password)
    await message.answer("لطفاً آدرس سرور AnyConnect را وارد کنید (در صورت عدم وجود، خط تیره بزنید):", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_anyconnect_server)

@router.message(AdminStates.waiting_for_anyconnect_server)
async def get_anyconnect_server(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    server = normalize_server_address((message.text or '').strip())
    if server == '-':
        server = ''
    state_data = await state.get_data()
    accounts = state_data.get('accounts', [])
    accounts.append({
        'account_type': 'anyconnect',
        'username': state_data.get('temp_username', ''),
        'password': state_data.get('temp_password', ''),
        'secret': '',
        'server': server,
        'port': 0,
        'config': '',
        'extra_note': ''
    })
    await state.update_data(accounts=accounts, temp_username=None, temp_password=None)
    await message.answer(
        f"✅ اکانت AnyConnect ذخیره شد. تعداد کل: {len(accounts)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text="افزودن اکانت بعدی", callback_data="add_single_account")],[ikb_btn(text="ثبت نهایی", callback_data="accounts_done")]])
    )
    await state.set_state(AdminStates.waiting_for_product_new_accounts)

@router.message(AdminStates.waiting_for_wireguard_config)
async def get_wireguard_config(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    config_text = (message.text or '').strip()
    accounts = (await state.get_data()).get('accounts', [])
    accounts.append({
        'account_type': 'wireguard',
        'username': '',
        'password': '',
        'secret': '',
        'server': '',
        'port': 0,
        'config': config_text,
        'extra_note': ''
    })
    await state.update_data(accounts=accounts)
    await message.answer(
        f"✅ اکانت WireGuard ذخیره شد. تعداد کل: {len(accounts)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text="افزودن اکانت بعدی", callback_data="add_single_account")],[ikb_btn(text="ثبت نهایی", callback_data="accounts_done")]])
    )
    await state.set_state(AdminStates.waiting_for_product_new_accounts)

@router.message(AdminStates.waiting_for_openvpn_secret)
async def get_openvpn_secret(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    secret = message.text.strip()
    if secret == "-":
        secret = ""
    await state.update_data(temp_secret=secret)
    await message.answer("لطفاً آدرس سرور L2TP/OpenVPN را وارد کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_openvpn_server)

@router.message(AdminStates.waiting_for_openvpn_server)
async def get_openvpn_server(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    server = normalize_server_address((message.text or '').strip())
    if server == "-":
        server = ""
    accounts = (await state.get_data()).get('accounts', [])
    accounts.append({
        'account_type': 'openvpn',
        'username': (await state.get_data()).get('temp_username', ''),
        'password': (await state.get_data()).get('temp_password', ''),
        'secret': (await state.get_data()).get('temp_secret', ''),
        'server': server,
        'port': 0,
        'config': ''
    })
    await state.update_data(accounts=accounts)
    for k in ['temp_username', 'temp_password', 'temp_secret', 'temp_server', 'temp_port', 'temp_config']:
        await state.update_data({k: None})
    await message.answer(f"✅ اکانت OpenVPN/L2TP ذخیره شد. تعداد کل: {len(accounts)}\nفقط فیلدهای نام کاربری، رمز عبور، سکرت کد و آدرس سرور دریافت شد.\nآیا می‌خواهید اکانت دیگری اضافه کنید؟", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[ikb_btn(text="بله", callback_data="add_single_account")], [ikb_btn(text="خیر، ثبت نهایی", callback_data="accounts_done")]]
    ))
    await state.set_state(AdminStates.waiting_for_product_new_accounts)

@router.message(AdminStates.waiting_for_openvpn_config)
async def handle_openvpn_product_defaults(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await state.clear()
        return
    state_data = await state.get_data()
    mode = state_data.get('openvpn_defaults_mode')
    if mode not in ('create', 'edit'):
        await message.answer("این مرحله برای تنظیمات مشترک محصول استفاده می‌شود.")
        return
    product_id = state_data.get('edit_product_id')
    if not product_id:
        await message.answer("❌ شناسه محصول پیدا نشد.")
        await state.clear()
        return
    parsed = parse_openvpn_defaults_text(message.text)
    latest_cfg_value = await data_manager.get_latest_openvpn_config()
    await data_manager.update_product_openvpn_settings(
        product_id,
        server=parsed.get('server', ''),
        secret=parsed.get('secret', ''),
        download_link=parsed.get('download_link', ''),
        config_value=(latest_cfg_value if (parsed.get('server') or parsed.get('secret') or parsed.get('download_link')) else None)
    )
    await state.update_data(openvpn_defaults_mode=None)
    if mode == 'edit':
        await state.clear()
        await message.answer("✅ تنظیمات مشترک OpenVPN محصول ذخیره شد.", reply_markup=admin_main_menu)
        return
    await message.answer(
        "✅ تنظیمات مشترک محصول ذخیره شد. حالا نوع اکانت را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [ikb_btn(text="OpenVPN", callback_data="acc_type_openvpn"), ikb_btn(text="L2TP", callback_data="acc_type_l2tp")],
                [ikb_btn(text="AnyConnect", callback_data="acc_type_anyconnect"), ikb_btn(text="WireGuard", callback_data="acc_type_wireguard")],
                [ikb_btn(text="V2Ray", callback_data="acc_type_v2ray"), ikb_btn(text="سایر", callback_data="acc_type_other")],
                [ikb_btn(text="لغو", callback_data="cancel")]
            ]
        )
    )
    await state.set_state(AdminStates.waiting_for_account_type)

@router.message(AdminStates.waiting_for_latest_openvpn_config, F.document)
async def upload_latest_openvpn_config_file(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await state.clear()
        return
    file = await bot.get_file(message.document.file_id)
    raw_name = message.document.file_name or f"openvpn_latest_{int(time.time())}.ovpn"
    file_name = os.path.basename(raw_name).replace('..', '_')
    save_name = f"latest_openvpn_{int(time.time())}_{file_name}"
    save_path = os.path.join(UPLOADS_DIR, save_name)
    await bot.download_file(file.file_path, save_path)
    caption = (message.caption or 'آخرین فایل سرور OpenVPN').strip()
    await data_manager.set_latest_openvpn_config(f"FILE::{save_path}|{caption}")
    await state.clear()
    await message.answer("✅ آخرین فایل کانفیگ OpenVPN ذخیره شد.", reply_markup=admin_main_menu)

@router.message(AdminStates.waiting_for_latest_openvpn_config)
async def upload_latest_openvpn_config_invalid(message: types.Message, state: FSMContext, **kwargs):
    await message.answer("لطفاً فایل کانفیگ OpenVPN را به صورت Document ارسال کنید.", reply_markup=cancel_only_button)

@router.message(AdminStates.waiting_for_v2ray_link)
async def get_v2ray_link(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    link = message.text.strip()
    if not link.startswith(('vmess://', 'vless://', 'trojan://')):
        await message.answer("لینک وارد شده معتبر نیست. لطفاً لینک vmess:// یا vless:// را وارد کنید.", reply_markup=cancel_only_button)
        return
    await state.update_data(temp_config=link)
    accounts = (await state.get_data()).get('accounts', [])
    accounts.append({
        'account_type': 'v2ray',
        'config': link,
        'username': '',
        'password': '',
        'server': '',
        'port': 0
    })
    await state.update_data(accounts=accounts)
    await state.update_data(temp_config=None)
    await message.answer(f"✅ اکانت V2Ray ذخیره شد. تعداد کل: {len(accounts)}\nآیا می‌خواهید اکانت دیگری اضافه کنید؟", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="بله", callback_data="add_single_account")],
            [ikb_btn(text="خیر، ثبت نهایی", callback_data="accounts_done")]
        ]
    ))
    await state.set_state(AdminStates.waiting_for_product_new_accounts)

@router.message(AdminStates.waiting_for_other_account)
async def get_other_account(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await message.answer("⛔ دسترسی غیرمجاز.")
        await state.clear()
        return
    text = message.text.strip()
    accounts = (await state.get_data()).get('accounts', [])
    accounts.append({
        'account_type': 'other',
        'config': text,
        'username': '',
        'password': '',
        'server': '',
        'port': 0
    })
    await state.update_data(accounts=accounts)
    await message.answer(f"✅ اکانت ذخیره شد. تعداد کل: {len(accounts)}\nآیا می‌خواهید اکانت دیگری اضافه کنید؟", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [ikb_btn(text="بله", callback_data="add_single_account")],
            [ikb_btn(text="خیر، ثبت نهایی", callback_data="accounts_done")]
        ]
    ))
    await state.set_state(AdminStates.waiting_for_product_new_accounts)

@router.callback_query(F.data == "add_single_account")
@admin_only
async def add_single_account_start(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_text("لطفاً نوع اکانت را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [ikb_btn(text="OpenVPN", callback_data="acc_type_openvpn"), ikb_btn(text="L2TP", callback_data="acc_type_l2tp")],
                [ikb_btn(text="AnyConnect", callback_data="acc_type_anyconnect"), ikb_btn(text="WireGuard", callback_data="acc_type_wireguard")],
                [ikb_btn(text="V2Ray", callback_data="acc_type_v2ray"), ikb_btn(text="سایر", callback_data="acc_type_other")],
                [ikb_btn(text="لغو", callback_data="cancel")]
            ]
        )
    )
    await state.set_state(AdminStates.waiting_for_account_type)

@router.callback_query(F.data == "accounts_done")
@router.callback_query(F.data == "accounts_done_existing")
@admin_only
async def accounts_done(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    state_data = await state.get_data()
    accounts = state_data.get('accounts', [])
    product_id = state_data.get('edit_product_id')
    if not product_id:
        await callback.message.edit_text("❌ خطا: محصول برای افزودن اکانت مشخص نشده.")
        await state.clear()
        return
    if not accounts:
        await callback.message.edit_text("❌ هیچ اکانتی اضافه نشد.")
        await state.clear()
        return
    before_count = await data_manager.get_product_accounts_count(product_id)
    await data_manager.add_accounts_to_product(product_id, accounts)
    after_count = await data_manager.get_product_accounts_count(product_id)
    product = await data_manager.get_product_by_id(product_id)
    if before_count == 0 and after_count > 0 and product:
        subscribers = await data_manager.get_product_stock_subscribers(product_id)
        for uid in subscribers:
            try:
                await bot.send_message(uid, f"✅ محصول «{product.get('name', 'نامشخص')}» دوباره موجود شد و آماده خرید است.")
            except Exception:
                pass
        if subscribers:
            await data_manager.clear_product_stock_subscribers(product_id)
        try:
            await bot.send_message(ADMIN_ID, f"🔔 محصول «{product.get('name', 'نامشخص')}» دوباره موجود شد. موجودی فعلی: {after_count}")
        except Exception:
            pass
    await callback.message.edit_text(f"✅ {len(accounts)} اکانت با موفقیت به محصول اضافه شد.")
    await state.clear()

# =================================================================
