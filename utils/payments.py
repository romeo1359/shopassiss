from typing import Any, Iterable, List, Sequence
from aiogram.types import InlineKeyboardMarkup

from app import data_manager
from keyboards.inline import ikb_btn
from config import BUTTON_STYLE_DANGER, BUTTON_STYLE_PRIMARY, BUTTON_STYLE_SUCCESS

PAYMENT_METHOD_LABELS = {
    "card": "💳 کارت به کارت",
    "usdt": "₮ پرداخت با تتر",
    "wallet": "💰 کیف پول",
    "credit": "🤝 درخواست شارژ نسیه",
    "pay_debt": "💸 پرداخت بدهی",
}

PAYMENT_CALLBACKS = {
    "card": "topup_card_to_card",
    "usdt": "topup_usdt",
    "wallet": "topup_wallet",
    "credit": "topup_credit",
}

async def _resolve_role_key(user_or_id: Any) -> str:
    if isinstance(user_or_id, dict):
        user_info = user_or_id
        user_id = int(user_info.get("user_id") or 0)
    else:
        user_id = int(user_or_id or 0)
        user_info = await data_manager.get_user(user_id) if user_id else None

    if user_id and await data_manager.is_admin(user_id):
        return "admin"
    if user_info and user_info.get("is_rep"):
        return "rep"
    return "user"

async def get_role_payment_methods(user_or_id: Any) -> List[str]:
    role_key = await _resolve_role_key(user_or_id)
    raw = (await data_manager.get_setting(f"{role_key}_allowed_payment_methods") or "").strip().lower()
    if not raw:
        raw = "card,usdt,credit" if role_key in ("admin", "rep") else "card,usdt"
    items: List[str] = []
    for item in [x.strip() for x in raw.split(",") if x.strip()]:
        if item not in items:
            items.append(item)

    if role_key == "rep" and "pay_debt" not in items:
        items.append("pay_debt")
    return items

async def is_payment_method_allowed(user_or_id: Any, method_key: str) -> bool:
    method_key = (method_key or "").strip().lower()
    return method_key in await get_role_payment_methods(user_or_id)

def build_payment_methods_markup(methods: Sequence[str], is_rep: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for key in methods:
        if key == "pay_debt":
            rows.append([ikb_btn(text=PAYMENT_METHOD_LABELS[key], callback_data="pay_debt")])
            continue
        callback_data = PAYMENT_CALLBACKS.get(key)
        if not callback_data:
            continue
        style = BUTTON_STYLE_SUCCESS if key in ("usdt", "wallet") else BUTTON_STYLE_PRIMARY
        rows.append([ikb_btn(text=PAYMENT_METHOD_LABELS.get(key, key), style=style, callback_data=callback_data)])
    if is_rep and "credit" not in methods:
        rows.append([ikb_btn(text=PAYMENT_METHOD_LABELS["pay_debt"], callback_data="pay_debt")])
    rows.append([ikb_btn(text="❌ لغو", style=BUTTON_STYLE_DANGER, callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
