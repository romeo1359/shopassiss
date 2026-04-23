from aiogram.types import InlineKeyboardMarkup

from app import data_manager
from config import BUTTON_STYLE_DANGER, BUTTON_STYLE_PRIMARY, SUPPORT_CATEGORY_LABELS, SUPPORT_PRIORITY_LABELS, USDT_NETWORK_LABELS, USDT_NETWORKS
from keyboards.inline import ikb_btn


def get_usdt_setting_key(network: str) -> str:
    return f"usdt_wallet_address_{(network or '').strip().lower()}"


async def get_primary_usdt_network() -> str:
    primary = (await data_manager.get_setting('usdt_wallet_network') or 'BEP20').strip().upper()
    valid = {key for key, _ in USDT_NETWORKS}
    return primary if primary in valid else 'BEP20'


async def get_configured_usdt_networks():
    primary = await get_primary_usdt_network()
    configured = []
    for key, label in USDT_NETWORKS:
        address = (await data_manager.get_setting(get_usdt_setting_key(key)) or '').strip()
        if address:
            configured.append({'key': key, 'label': label, 'address': address})
    if not configured:
        legacy = (await data_manager.get_setting('usdt_wallet_address') or '').strip()
        if legacy:
            configured.append({'key': primary, 'label': USDT_NETWORK_LABELS.get(primary, primary), 'address': legacy})
    configured.sort(key=lambda item: (item['key'] != primary, item['key']))
    return configured


def build_usdt_network_selector_markup(prefix: str, configured_items):
    buttons = []
    for item in configured_items:
        buttons.append([ikb_btn(text=f"₮ {item['label']}", style=BUTTON_STYLE_PRIMARY, callback_data=f"{prefix}{item['key']}")])
    buttons.append([ikb_btn(text='❌ لغو', style=BUTTON_STYLE_DANGER, callback_data='cancel')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_support_category_label(category: str) -> str:
    return SUPPORT_CATEGORY_LABELS.get((category or '').strip().lower(), 'عمومی')


def get_support_priority_label(priority: str) -> str:
    return SUPPORT_PRIORITY_LABELS.get((priority or '').strip().lower(), 'عادی')
