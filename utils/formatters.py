import datetime
import re

import jdatetime


def escape_markdown(text: str) -> str:
    if not text:
        return text
    if text.startswith(('vmess://', 'vless://', 'trojan://', 'ss://', 'ssr://', 'http://', 'https://')):
        return text
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


def escape_markdown_code(text: str) -> str:
    return ('' if text is None else str(text)).replace('`', '\\`')


def format_persian_date(date_str: str) -> str:
    try:
        if date_str and date_str != 'نامشخص':
            greg_date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            j_date = jdatetime.datetime.fromgregorian(datetime=greg_date)
            return j_date.strftime("%Y/%m/%d - %H:%M:%S")
    except (TypeError, ValueError):
        pass
    return date_str


def normalize_phone(phone: str) -> str:
    phone = (phone or '').strip().replace(' ', '').replace('-', '')
    digits = ''.join(ch for ch in phone if ch.isdigit() or ch == '+')
    if digits.startswith('+98'):
        digits = '0' + digits[3:]
    elif digits.startswith('98') and len(digits) >= 12:
        digits = '0' + digits[2:]
    return digits


def normalize_server_address(value: str) -> str:
    value = (value or '').strip()
    value = value.replace('\\.', '.').replace('\\/', '/').replace('\\_', '_').replace('\\-', '-')
    value = re.sub(r'\\(?=[.\-_/])', '', value)
    return value


def get_payment_method_label(payment_method: str) -> str:
    method = (payment_method or 'card').lower()
    if method == 'usdt':
        return 'تتر (USDT)'
    if method == 'wallet':
        return 'کیف پول'
    if method == 'credit':
        return 'نسیه'
    return 'کارت به کارت'


def get_payment_status_label(status: str) -> str:
    status = (status or 'pending').lower()
    if status == 'approved':
        return 'تایید شده ✅'
    if status == 'rejected':
        return 'رد شده ❌'
    return 'در انتظار بررسی ⏳'
