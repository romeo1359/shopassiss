from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import (
    BUTTON_STYLE_DANGER,
    BUTTON_STYLE_PRIMARY,
    BUTTON_STYLE_SUCCESS,
    SUPPORT_CATEGORIES,
    SUPPORT_PRIORITIES,
)

def ikb_btn(*, text: str, style: str = None, **kwargs):
    params = {"text": text, **kwargs}
    if style:
        try:
            return InlineKeyboardButton(style=style, **params)
        except TypeError:
            return InlineKeyboardButton(**params)
    return InlineKeyboardButton(**params)

def build_support_category_markup(prefix: str = 'support_category_') -> InlineKeyboardMarkup:
    rows = [[ikb_btn(text=f'📂 {label}', callback_data=f'{prefix}{key}')] for key, label in SUPPORT_CATEGORIES]
    rows.append([ikb_btn(text='❌ لغو', style=BUTTON_STYLE_DANGER, callback_data='cancel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def build_support_priority_markup(prefix: str = 'support_priority_') -> InlineKeyboardMarkup:
    rows = [[ikb_btn(text=f'⚡ {label}', callback_data=f'{prefix}{key}')] for key, label in SUPPORT_PRIORITIES]
    rows.append([ikb_btn(text='❌ لغو', style=BUTTON_STYLE_DANGER, callback_data='cancel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

admin_support_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [ikb_btn(text="📢 ارسال پیام همگانی", style=BUTTON_STYLE_PRIMARY, callback_data="broadcast_menu")],
        [ikb_btn(text="🎫 تیکت‌های باز", style=BUTTON_STYLE_SUCCESS, callback_data="list_open_tickets")],
        [ikb_btn(text="🔍 مدیریت کد رهگیری", style=BUTTON_STYLE_PRIMARY, callback_data="manage_tracking_code")],
        [ikb_btn(text="🔙 بازگشت", style=BUTTON_STYLE_PRIMARY, callback_data="back_to_main")]
    ]
)

broadcast_targets = InlineKeyboardMarkup(
    inline_keyboard=[
        [ikb_btn(text="👥 همه کاربران", style=BUTTON_STYLE_PRIMARY, callback_data="broadcast_all")],
        [ikb_btn(text="🙍 کاربران عادی", style=BUTTON_STYLE_PRIMARY, callback_data="broadcast_regulars")],
        [ikb_btn(text="🧑‍💻 نمایندگان", style=BUTTON_STYLE_SUCCESS, callback_data="broadcast_reps")],
        [ikb_btn(text="💸 بدهکاران", style=BUTTON_STYLE_PRIMARY, callback_data="broadcast_debtors")],
                [ikb_btn(text="❌ لغو", style=BUTTON_STYLE_DANGER, callback_data="cancel")]
    ]
)

cancel_only_button = InlineKeyboardMarkup(
    inline_keyboard=[[ikb_btn(text="❌ لغو", style=BUTTON_STYLE_DANGER, callback_data="cancel")]]
)

done_buttons_for_new_product = InlineKeyboardMarkup(
    inline_keyboard=[
        [ikb_btn(text="✅ ثبت نهایی", style=BUTTON_STYLE_SUCCESS, callback_data="accounts_done")],
        [ikb_btn(text="❌ لغو", style=BUTTON_STYLE_DANGER, callback_data="cancel")]
    ]
)

done_buttons_for_existing_product = InlineKeyboardMarkup(
    inline_keyboard=[
        [ikb_btn(text="✅ ثبت نهایی", style=BUTTON_STYLE_SUCCESS, callback_data="accounts_done_existing")],
        [ikb_btn(text="❌ لغو", style=BUTTON_STYLE_DANGER, callback_data="cancel")]
    ]
)

representative_wallet_buttons = InlineKeyboardMarkup(
    inline_keyboard=[
        [ikb_btn(text="💳 شارژ از طریق کارت به کارت", style=BUTTON_STYLE_PRIMARY, callback_data="topup_card_to_card")],
        [ikb_btn(text="₮ پرداخت با تتر (USDT)", style=BUTTON_STYLE_SUCCESS, callback_data="topup_usdt")],
        [ikb_btn(text="🤝 درخواست شارژ نسیه", callback_data="topup_credit")],
        [ikb_btn(text="💸 پرداخت بدهی", callback_data="pay_debt")],
        [ikb_btn(text="❌ لغو", style=BUTTON_STYLE_DANGER, callback_data="cancel")]
    ]
)

credit_limit_buttons = InlineKeyboardMarkup(
    inline_keyboard=[
        [ikb_btn(text="۵۰۰,۰۰۰", callback_data="set_credit_limit_500000")],
        [ikb_btn(text="۱,۰۰۰,۰۰۰", callback_data="set_credit_limit_1000000")],
        [ikb_btn(text="۲,۰۰۰,۰۰۰", callback_data="set_credit_limit_2000000")],
        [ikb_btn(text="۵,۰۰۰,۰۰۰", callback_data="set_credit_limit_5000000")],
        [ikb_btn(text="❌ لغو", style=BUTTON_STYLE_DANGER, callback_data="cancel")]
    ]
)

back_to_admin_inline = InlineKeyboardMarkup(
    inline_keyboard=[[ikb_btn(text="🔙 بازگشت به منوی ادمین", callback_data="back_to_main")]]
)

start_button = InlineKeyboardMarkup(
    inline_keyboard=[[ikb_btn(text="🚀 شروع ربات", style=BUTTON_STYLE_PRIMARY, callback_data="start_bot")]]
)

confirm_delete_buttons = InlineKeyboardMarkup(
    inline_keyboard=[
        [ikb_btn(text="✅ بله، حذف شود", style=BUTTON_STYLE_DANGER, callback_data="confirm_delete_yes")],
        [ikb_btn(text="❌ خیر، انصراف", style=BUTTON_STYLE_PRIMARY, callback_data="confirm_delete_no")]
    ]
)
