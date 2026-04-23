import re

from .formatters import normalize_server_address


def parse_price_input(text: str):
    raw = (text or '').replace('،', '').replace(',', '').strip()
    if raw.isdigit():
        val = int(raw)
        if val > 0:
            return val
    return None


def parse_config_file_marker(value: str):
    if not value or not isinstance(value, str) or not value.startswith("FILE::"):
        return None, None
    payload = value.split("::", 1)[1]
    if "|" in payload:
        path, caption = payload.split("|", 1)
    else:
        path, caption = payload, ""
    return path, caption


def parse_approve_payment_callback(callback_data: str):
    raw = (callback_data or '').strip()
    if not raw.startswith('approve_payment_'):
        return None, 0, 0
    payload = raw[len('approve_payment_'):]
    m = re.fullmatch(r'(.+)_([0-9]+)_([0-9]+)', payload)
    if not m:
        return None, 0, 0
    payment_id = m.group(1)
    amount = int(m.group(2))
    bank_id = int(m.group(3))
    return payment_id, amount, bank_id


def parse_openvpn_defaults_text(text: str) -> dict:
    raw = (text or '').strip()
    if raw == '-' or not raw:
        return {'server': '', 'secret': '', 'download_link': ''}
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    while len(lines) < 3:
        lines.append('')
    return {
        'server': normalize_server_address(lines[0]),
        'secret': lines[1],
        'download_link': lines[2],
    }


def parse_channel_value(raw_value: str, require_username: bool = False):
    raw_value = (raw_value or '').strip()
    if raw_value == '-':
        return {'raw': '', 'username': '', 'chat_id': ''}
    if not raw_value:
        raise ValueError('مقدار کانال خالی است.')
    username = ''
    chat_id = ''
    if '|' in raw_value:
        username, chat_id = [p.strip() for p in raw_value.split('|', 1)]
    elif raw_value.startswith('@'):
        username = raw_value
    elif raw_value.startswith('-100'):
        chat_id = raw_value
    else:
        raise ValueError('فرمت کانال معتبر نیست.')
    if username and not re.fullmatch(r'@[A-Za-z0-9_]{5,}', username):
        raise ValueError('یوزرنیم کانال معتبر نیست.')
    if chat_id and not re.fullmatch(r'-100\d{5,}', chat_id):
        raise ValueError('آیدی عددی کانال معتبر نیست.')
    if require_username and not username:
        raise ValueError('یوزرنیم کانال اجباری است.')
    return {'raw': '|'.join([p for p in [username, chat_id] if p]), 'username': username, 'chat_id': chat_id}


def normalize_channel_ref(raw_value: str) -> str:
    try:
        return parse_channel_value(raw_value).get('raw', '')
    except Exception:
        return (raw_value or '').strip()
