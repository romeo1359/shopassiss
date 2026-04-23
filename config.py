import logging
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

UPLOADS_DIR = "uploads"
BACKUP_DIR = "backups"

DB_CACHE_TTL_SECONDS = int(os.getenv("DB_CACHE_TTL_SECONDS", "90"))
DB_CACHE_MAX_ITEMS = int(os.getenv("DB_CACHE_MAX_ITEMS", "4000"))
SQLITE_BUSY_TIMEOUT_MS = int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "5000"))

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN or not ADMIN_ID_RAW:
    logger.error("خطا: متغیرهای BOT_TOKEN یا ADMIN_ID در فایل .env تنظیم نشده‌اند.")
    raise SystemExit(1)

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except (TypeError, ValueError):
    logger.error("خطا: مقدار ADMIN_ID باید عدد صحیح باشد.")
    raise SystemExit(1)

BUTTON_STYLE_PRIMARY = "primary"
BUTTON_STYLE_SUCCESS = "success"
BUTTON_STYLE_DANGER = "danger"

USDT_NETWORKS = [
    ('BEP20', 'BEP20 (BSC)'),
    ('TRC20', 'TRC20 (Tron)'),
    ('ERC20', 'ERC20 (Ethereum)'),
    ('TON', 'TON'),
]
USDT_NETWORK_LABELS = {key: label for key, label in USDT_NETWORKS}

SUPPORT_CATEGORIES = [
    ('general', 'عمومی'),
    ('purchase', 'خرید'),
    ('payment', 'پرداخت'),
    ('technical', 'فنی'),
    ('server_file', 'فایل سرور'),
]
SUPPORT_CATEGORY_LABELS = {key: label for key, label in SUPPORT_CATEGORIES}

SUPPORT_PRIORITIES = [('low', 'کم'), ('normal', 'عادی'), ('high', 'زیاد'), ('urgent', 'فوری')]
SUPPORT_PRIORITY_LABELS = {key: label for key, label in SUPPORT_PRIORITIES}
