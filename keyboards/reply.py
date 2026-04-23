from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from config import BUTTON_STYLE_PRIMARY, BUTTON_STYLE_SUCCESS

def kb_btn(*, text: str, style: str = None, **kwargs):
    params = {"text": text, **kwargs}
    if style:
        try:
            return KeyboardButton(style=style, **params)
        except TypeError:
            return KeyboardButton(**params)
    return KeyboardButton(**params)

user_main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [kb_btn(text="🛒 فروشگاه", style=BUTTON_STYLE_PRIMARY), kb_btn(text="💰 کیف پول", style=BUTTON_STYLE_SUCCESS)],
        [kb_btn(text="👤 حساب من", style=BUTTON_STYLE_PRIMARY), kb_btn(text="🛟 پشتیبانی", style=BUTTON_STYLE_PRIMARY)],
        [kb_btn(text="🎓 آموزش خرید با تتر", style=BUTTON_STYLE_PRIMARY), kb_btn(text="📥 آخرین فایل سرور", style=BUTTON_STYLE_SUCCESS)]
    ],
    resize_keyboard=True
)

rep_menu = ReplyKeyboardMarkup(
    keyboard=[
        [kb_btn(text="🛒 فروشگاه", style=BUTTON_STYLE_PRIMARY), kb_btn(text="💰 کیف پول", style=BUTTON_STYLE_SUCCESS)],
        [kb_btn(text="👤 حساب من", style=BUTTON_STYLE_PRIMARY), kb_btn(text="🛟 پشتیبانی", style=BUTTON_STYLE_PRIMARY)],
        [kb_btn(text="🎓 آموزش خرید با تتر", style=BUTTON_STYLE_PRIMARY), kb_btn(text="📥 آخرین فایل سرور", style=BUTTON_STYLE_SUCCESS)]
    ],
    resize_keyboard=True
)


admin_main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [kb_btn(text="👥 مدیریت کاربران", style=BUTTON_STYLE_PRIMARY), kb_btn(text="📦 مدیریت کالاها", style=BUTTON_STYLE_PRIMARY)],
        [kb_btn(text="⚙️ تنظیمات ربات", style=BUTTON_STYLE_SUCCESS), kb_btn(text="🛡️ مدیریت ادمین‌ها", style=BUTTON_STYLE_PRIMARY)],
        [kb_btn(text="🏦 حساب‌های بانکی", style=BUTTON_STYLE_PRIMARY), kb_btn(text="🎫 تیکت‌ها و پیام همگانی", style=BUTTON_STYLE_PRIMARY)],
        [kb_btn(text="⏳ پرداخت‌های معلق", style=BUTTON_STYLE_SUCCESS)]
    ],
    resize_keyboard=True
)

launch_reply_menu = ReplyKeyboardMarkup(
    keyboard=[[kb_btn(text="🚀 شروع ربات", style=BUTTON_STYLE_PRIMARY)]],
    resize_keyboard=True
)

def build_contact_share_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 اشتراک شماره موبایل", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
