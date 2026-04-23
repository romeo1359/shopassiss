import html

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from app import data_manager
from config import BUTTON_STYLE_PRIMARY
from states.admin_states import AdminStates
from keyboards.inline import cancel_only_button, ikb_btn
from keyboards.reply import admin_main_menu
from utils.parsers import normalize_channel_ref, parse_channel_value, parse_config_file_marker
from utils.telegram_utils import admin_only, is_safe_managed_file, rate_limit, safe_callback_answer, safe_send_document
router = Router()

# 19.5 هندلر آموزش
# =================================================================

def build_education_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [ikb_btn(text="➕ پست جدید", callback_data="edu_admin_new")],
        [ikb_btn(text="📋 لیست پست‌ها", callback_data="edu_admin_list")],
        [ikb_btn(text="⚙️ تنظیم کانال آموزش", callback_data="set_education_channel")],
        [ikb_btn(text="📁 ثبت آخرین فایل OpenVPN", callback_data="edu_set_latest_ovpn")],
        [ikb_btn(text="📥 دریافت آخرین فایل سرور", callback_data="download_latest_openvpn_config")],
        [ikb_btn(text="📤 ارسال آخرین فایل OpenVPN به کانال", callback_data="edu_send_latest_ovpn")],
        [ikb_btn(text="🔙 بازگشت", style=BUTTON_STYLE_PRIMARY, callback_data="back_to_main")],
    ])


def build_tutorial_list_keyboard(tutorials: list, is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for t in tutorials:
        rows.append([InlineKeyboardButton(text=f"📘 {t['title']}", callback_data=f"edu_view_{t['id']}")])
        if is_admin:
            rows.append([InlineKeyboardButton(text=f"🗑 حذف: {t['title']}", callback_data=f"edu_delete_{t['id']}")])
    rows.append([ikb_btn(text="🔙 بازگشت", style=BUTTON_STYLE_PRIMARY, callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "edu_set_latest_ovpn")
@admin_only
async def education_set_latest_ovpn(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    await callback.message.edit_text("فایل کانفیگ جدید OpenVPN را به صورت Document ارسال کنید.", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_latest_openvpn_config)

@router.callback_query(F.data == "edu_send_latest_ovpn")
@admin_only
async def education_send_latest_ovpn(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    education_channel = normalize_channel_ref(await data_manager.get_setting('education_channel'))
    latest_config = await data_manager.get_latest_openvpn_config()
    if not education_channel:
        await callback.message.edit_text("ابتدا کانال آموزش را با فرمت @username|-100id تنظیم کنید.", reply_markup=build_education_admin_menu())
        return
    if not latest_config:
        await callback.message.edit_text("ابتدا آخرین فایل OpenVPN را ثبت کنید.", reply_markup=build_education_admin_menu())
        return
    parsed_channel = parse_channel_value(education_channel, require_username=True)
    cfg_path, cfg_caption = parse_config_file_marker(latest_config)
    if not cfg_path or not is_safe_managed_file(cfg_path):
        await callback.message.edit_text("فایل ذخیره شده پیدا نشد. لطفاً دوباره فایل را ثبت کنید.", reply_markup=build_education_admin_menu())
        return
    target_chat = parsed_channel.get('chat_id') or parsed_channel.get('username')
    await safe_send_document(target_chat, FSInputFile(cfg_path), caption=(cfg_caption or 'آخرین فایل سرور OpenVPN'))
    await callback.message.edit_text("✅ آخرین فایل سرور OpenVPN در کانال آموزشی ارسال شد.", reply_markup=build_education_admin_menu())

@router.message(F.text == "📚 آموزش")
@rate_limit(5)
async def handle_education_menu(message: types.Message, **kwargs):
    await message.answer("بخش آموزش از ربات حذف شده است.")


@router.callback_query(F.data == "edu_admin_new")
@admin_only
async def education_admin_new(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await safe_callback_answer(callback)
    await callback.message.edit_text("عنوان پست آموزشی را ارسال کنید:", reply_markup=cancel_only_button)
    await state.set_state(AdminStates.waiting_for_tutorial_title)


@router.message(AdminStates.waiting_for_tutorial_title)
async def tutorial_title_received(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await state.clear()
        return
    title = (message.text or '').strip()
    if len(title) < 2:
        await message.answer("عنوان معتبر وارد کنید.")
        return
    await state.update_data(tutorial_title=title)
    await state.set_state(AdminStates.waiting_for_tutorial_content)
    await message.answer("متن پست آموزشی را ارسال کنید:", reply_markup=cancel_only_button)


@router.message(AdminStates.waiting_for_tutorial_content)
async def tutorial_content_received(message: types.Message, state: FSMContext, **kwargs):
    if not await data_manager.is_admin(message.from_user.id):
        await state.clear()
        return
    content = (message.text or '').strip()
    if len(content) < 2:
        await message.answer("متن معتبر وارد کنید.")
        return
    data = await state.get_data()
    title = data.get('tutorial_title', 'بدون عنوان')
    tutorial_id = await data_manager.add_tutorial(title, content, message.from_user.id)
    await state.clear()
    await message.answer(f"✅ پست آموزشی با شناسه {tutorial_id} ثبت شد.", reply_markup=admin_main_menu)


@router.callback_query(F.data == "edu_admin_list")
@admin_only
async def education_admin_list(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    tutorials = await data_manager.get_tutorials(active_only=False)
    if not tutorials:
        await callback.message.edit_text("هیچ پست آموزشی ثبت نشده است.", reply_markup=build_education_admin_menu())
        return
    await callback.message.edit_text("لیست پست‌های آموزشی:", reply_markup=build_tutorial_list_keyboard(tutorials, is_admin=True))


@router.callback_query(F.data.startswith("edu_view_"))
async def education_view(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    try:
        tutorial_id = int(callback.data.split("_")[-1])
    except Exception:
        await callback.message.answer("شناسه آموزش نامعتبر است.")
        return
    tutorial = await data_manager.get_tutorial_by_id(tutorial_id)
    if not tutorial or (not tutorial.get('is_active') and not await data_manager.is_admin(callback.from_user.id)):
        await callback.message.answer("این آموزش یافت نشد.")
        return
    title = html.escape(tutorial['title'])
    content = html.escape(tutorial['content'])
    created_at = tutorial.get('created_at', 'نامشخص')
    text = f"<b>{title}</b>\n\n{content}\n\n<code>{created_at}</code>"
    back_markup = InlineKeyboardMarkup(inline_keyboard=[[ikb_btn(text="🔙 بازگشت", callback_data="edu_admin_list" if await data_manager.is_admin(callback.from_user.id) else "edu_back_list")]])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_markup)


@router.callback_query(F.data == "edu_back_list")
async def education_back_list(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    tutorials = await data_manager.get_tutorials(active_only=True)
    if not tutorials:
        await callback.message.edit_text("هیچ آموزشی ثبت نشده است.")
        return
    await callback.message.edit_text("لیست آموزش‌ها:", reply_markup=build_tutorial_list_keyboard(tutorials, is_admin=False))


@router.callback_query(F.data.startswith("edu_delete_"))
@admin_only
async def education_delete(callback: types.CallbackQuery, **kwargs):
    await safe_callback_answer(callback)
    try:
        tutorial_id = int(callback.data.split("_")[-1])
    except Exception:
        await callback.message.answer("شناسه آموزش نامعتبر است.")
        return
    tutorial = await data_manager.get_tutorial_by_id(tutorial_id)
    if not tutorial:
        await callback.message.edit_text("این پست دیگر وجود ندارد.", reply_markup=build_education_admin_menu())
        return
    await data_manager.delete_tutorial(tutorial_id)
    tutorials = await data_manager.get_tutorials(active_only=False)
    if tutorials:
        await callback.message.edit_text("✅ پست آموزشی حذف شد.\n\nلیست پست‌های آموزشی:", reply_markup=build_tutorial_list_keyboard(tutorials, is_admin=True))
    else:
        await callback.message.edit_text("✅ پست آموزشی حذف شد. دیگر پستی باقی نمانده است.", reply_markup=build_education_admin_menu())


# =================================================================
