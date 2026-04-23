# data_manager.py
import asyncio
import datetime
import hashlib
import logging
import os
import random
import time

import aiosqlite
from cryptography.fernet import Fernet

from config import DB_CACHE_MAX_ITEMS, DB_CACHE_TTL_SECONDS, SQLITE_BUSY_TIMEOUT_MS
from utils.cache import TTLCache

logger = logging.getLogger(__name__)


class DataManager:
    def __init__(self, db_path: str = "bot_database.db", admin_id: int = None, encryption_key: str = None):
        self.db_path = db_path
        self.admin_id = admin_id
        self.cache = TTLCache(max_size=DB_CACHE_MAX_ITEMS, default_ttl=DB_CACHE_TTL_SECONDS)
        self.settings_cache = TTLCache(max_size=256, default_ttl=max(30, DB_CACHE_TTL_SECONDS * 2))
        self.cipher = None
        self._db = None
        self._db_lock = asyncio.Lock()
        if encryption_key:
            try:
                self.cipher = Fernet(encryption_key.encode())
            except Exception as e:
                logger.warning(f"Invalid encryption key: {e}")

    def _cache_key(self, func_name, *args, **kwargs):
        return f"{func_name}:{args}:{kwargs}"

    async def _get_cached(self, key):
        return self.cache.get(key)

    async def _set_cached(self, key, value, ttl: int | None = None):
        return self.cache.set(key, value, ttl=ttl)

    async def _invalidate_cache(self, pattern=None):
        if pattern is None:
            self.cache.clear()
            self.settings_cache.clear()
        else:
            self.cache.invalidate_prefixes([pattern])
            if pattern.startswith("settings") or pattern == "get_setting":
                self.settings_cache.clear()

    async def _get_db(self):
        async with self._db_lock:
            if self._db is None:
                self._db = await aiosqlite.connect(self.db_path)
                self._db.row_factory = aiosqlite.Row
                await self._db.execute("PRAGMA foreign_keys = ON;")
                await self._db.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS};")
                await self._db.execute("PRAGMA synchronous=NORMAL;")
                await self._db.execute("PRAGMA temp_store=MEMORY;")
                await self._db.execute("PRAGMA cache_size=-20000;")
                await self._db.execute("PRAGMA mmap_size=268435456;")
            return self._db

    async def _fetchone(self, query: str, params: tuple = ()):
        db = await self._get_db()
        async with db.execute(query, params) as cursor:
            return await cursor.fetchone()

    async def _fetchall(self, query: str, params: tuple = ()):
        db = await self._get_db()
        async with db.execute(query, params) as cursor:
            return await cursor.fetchall()

    async def _execute(self, query: str, params: tuple = (), *, commit: bool = False):
        db = await self._get_db()
        cursor = await db.execute(query, params)
        if commit:
            await db.commit()
        return cursor

    def _encrypt(self, data: str) -> str:
        if not self.cipher or not data:
            return data
        return self.cipher.encrypt(data.encode()).decode()

    def _decrypt(self, data: str) -> str:
        if not self.cipher or not data:
            return data
        try:
            return self.cipher.decrypt(data.encode()).decode()
        except Exception as exc:
            logger.warning(f"Decrypt failed, returning raw data: {exc}")
            return data

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS};")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA temp_store=MEMORY;")
            await db.execute("PRAGMA cache_size=-20000;")
            await db.execute("PRAGMA mmap_size=268435456;")

            await db.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tutorials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    published_channel TEXT DEFAULT '',
                    published_message_id INTEGER DEFAULT 0
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    full_name TEXT NOT NULL DEFAULT 'ناشناس',
                    store_name TEXT DEFAULT 'نامشخص',
                    email TEXT DEFAULT 'ثبت نشده',
                    card_number TEXT DEFAULT 'ثبت نشده',
                    phone_number TEXT DEFAULT 'ثبت نشده',
                    phone_verified BOOLEAN DEFAULT 0,
                    balance INTEGER DEFAULT 0,
                    is_rep BOOLEAN DEFAULT 0,
                    discount_percentage INTEGER DEFAULT 0,
                    debt INTEGER DEFAULT 0,
                    credit_limit INTEGER DEFAULT 0,
                    registration_date TEXT,
                    banned BOOLEAN DEFAULT 0,
                    last_request_time TEXT,
                    is_financial_admin BOOLEAN DEFAULT 0,
                    is_approved BOOLEAN DEFAULT 0,
                    approved_by INTEGER DEFAULT 0,
                    approved_date TEXT,
                    referral_code TEXT UNIQUE,
                    referred_by INTEGER DEFAULT 0,
                    registration_status TEXT DEFAULT 'new',
                    rejection_reason TEXT DEFAULT ''
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    price INTEGER NOT NULL CHECK(price >= 0),
                    price_min INTEGER DEFAULT 0,
                    price_max INTEGER DEFAULT 0,
                    description TEXT,
                    openvpn_server TEXT DEFAULT '',
                    openvpn_secret TEXT DEFAULT '',
                    openvpn_download_link TEXT DEFAULT '',
                    openvpn_config TEXT DEFAULT '',
                    FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS product_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    account_type TEXT NOT NULL DEFAULT 'other',
                    username TEXT,
                    password TEXT,
                    secret TEXT DEFAULT '',
                    server TEXT,
                    port INTEGER,
                    config TEXT,
                    extra_note TEXT,
                    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS purchase_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    product_name TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    account TEXT NOT NULL,
                    date TEXT NOT NULL,
                    tracking_code INTEGER NOT NULL UNIQUE,
                    bank_account_number TEXT DEFAULT 'نامشخص',
                    payment_method TEXT DEFAULT 'wallet',
                    status TEXT DEFAULT 'success',
                    approved_by INTEGER DEFAULT 0
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    full_name TEXT NOT NULL,
                    message_text TEXT NOT NULL,
                    date TEXT NOT NULL,
                    is_answered BOOLEAN DEFAULT 0,
                    tracking_code INTEGER,
                    category TEXT DEFAULT 'general',
                    priority TEXT DEFAULT 'normal',
                    status TEXT DEFAULT 'open',
                    related_payment_id TEXT DEFAULT '',
                    answered_at TEXT DEFAULT '',
                    closed_at TEXT DEFAULT ''
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS debt_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payment_id TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
                    approved_by INTEGER DEFAULT 0,
                    target_bank_id INTEGER DEFAULT 0,
                    payment_method TEXT DEFAULT 'card',
                    payment_network TEXT DEFAULT '',
                    payment_destination TEXT DEFAULT '',
                    txid TEXT DEFAULT ''
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS payment_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payment_id TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    UNIQUE(payment_id, chat_id, message_id)
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS stock_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, product_id)
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS referral_rewards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_user_id INTEGER NOT NULL,
                    referred_user_id INTEGER NOT NULL,
                    purchase_id INTEGER NOT NULL UNIQUE,
                    tracking_code INTEGER NOT NULL,
                    purchase_amount INTEGER NOT NULL,
                    reward_percent REAL NOT NULL DEFAULT 1,
                    reward_amount INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    full_name TEXT,
                    added_by INTEGER,
                    added_date TEXT,
                    is_main BOOLEAN DEFAULT 0
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS bank_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_number TEXT NOT NULL,
                    account_owner TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    is_default BOOLEAN DEFAULT 0,
                    user_id INTEGER DEFAULT 0
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS file_cleanup (
                    file_name TEXT PRIMARY KEY,
                    expiry_date TEXT NOT NULL,
                    user_id INTEGER,
                    purpose TEXT
                )
            ''')

            # اضافه کردن ستون‌های جدید برای سازگاری
            for alter in [
                "ALTER TABLE users ADD COLUMN is_financial_admin BOOLEAN DEFAULT 0",
                "ALTER TABLE users ADD COLUMN phone_verified BOOLEAN DEFAULT 0",
                "ALTER TABLE support_tickets ADD COLUMN category TEXT DEFAULT 'general'",
                "ALTER TABLE support_tickets ADD COLUMN priority TEXT DEFAULT 'normal'",
                "ALTER TABLE support_tickets ADD COLUMN status TEXT DEFAULT 'open'",
                "ALTER TABLE support_tickets ADD COLUMN related_payment_id TEXT DEFAULT ''",
                "ALTER TABLE support_tickets ADD COLUMN answered_at TEXT DEFAULT ''",
                "ALTER TABLE support_tickets ADD COLUMN closed_at TEXT DEFAULT ''",
                "ALTER TABLE users ADD COLUMN is_approved BOOLEAN DEFAULT 0",
                "ALTER TABLE users ADD COLUMN approved_by INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN approved_date TEXT",
                "ALTER TABLE users ADD COLUMN referral_code TEXT",
                "ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN registration_status TEXT DEFAULT 'new'",
                "ALTER TABLE users ADD COLUMN rejection_reason TEXT DEFAULT ''",
                "ALTER TABLE admins ADD COLUMN is_main BOOLEAN DEFAULT 0",
                "ALTER TABLE product_accounts ADD COLUMN extra_note TEXT DEFAULT ''",
                "ALTER TABLE products ADD COLUMN price_min INTEGER DEFAULT 0",
                "ALTER TABLE products ADD COLUMN price_max INTEGER DEFAULT 0",
                "ALTER TABLE products ADD COLUMN openvpn_server TEXT DEFAULT ''",
                "ALTER TABLE products ADD COLUMN openvpn_secret TEXT DEFAULT ''",
                "ALTER TABLE products ADD COLUMN openvpn_download_link TEXT DEFAULT ''",
                "ALTER TABLE products ADD COLUMN openvpn_config TEXT DEFAULT ''",
                "ALTER TABLE purchase_history ADD COLUMN payment_method TEXT DEFAULT 'wallet'",
                "ALTER TABLE purchase_history ADD COLUMN status TEXT DEFAULT 'success'",
                "ALTER TABLE purchase_history ADD COLUMN approved_by INTEGER DEFAULT 0",
                "ALTER TABLE purchase_history ADD COLUMN group_name TEXT DEFAULT ''",
                "ALTER TABLE debt_payments ADD COLUMN approved_by INTEGER DEFAULT 0",
                "ALTER TABLE debt_payments ADD COLUMN target_bank_id INTEGER DEFAULT 0",
                "ALTER TABLE debt_payments ADD COLUMN payment_method TEXT DEFAULT 'card'",
                "ALTER TABLE debt_payments ADD COLUMN payment_network TEXT DEFAULT ''",
                "ALTER TABLE debt_payments ADD COLUMN payment_destination TEXT DEFAULT ''"
            ]:
                try:
                    await db.execute(alter)
                except aiosqlite.OperationalError:
                    pass

            await db.execute('''
                INSERT OR IGNORE INTO settings (key, value) VALUES
                ('bot_status', 'on'),
                ('shop_status', 'on'),
                ('bank_selection_mode', 'fixed'),
                ('representative_required_balance', '0'),
                ('mandatory_join_channel', ''),
                ('education_channel', ''),
                ('latest_openvpn_config', ''),
                ('usdt_wallet_address', ''),
                ('usdt_wallet_network', 'BEP20'),
                ('usdt_wallet_address_bep20', ''),
                ('usdt_wallet_address_trc20', ''),
                ('usdt_wallet_address_erc20', ''),
                ('usdt_wallet_address_ton', ''),
                ('usdt_buy_tutorial', ''),
                ('referral_system_enabled', 'on'),
                ('referral_reward_percent', '1'),
                ('referral_reward_mode', 'first_purchase')
            ''')

            if self.admin_id:
                await db.execute('''
                    INSERT OR IGNORE INTO admins (user_id, full_name, added_by, added_date, is_main)
                    VALUES (?, ?, ?, ?, ?)
                ''', (self.admin_id, "Admin", self.admin_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 1))

            await db.execute("CREATE INDEX IF NOT EXISTS idx_purchase_user ON purchase_history(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_purchase_tracking ON purchase_history(tracking_code)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone_number)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_approved ON users(is_approved, registration_status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_reg_status ON users(registration_status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_product_category ON products(category_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_ticket_tracking ON support_tickets(tracking_code)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_pa_product ON product_accounts(product_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_debt_user ON debt_payments(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_debt_target_bank ON debt_payments(target_bank_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_payment_notifications_payment ON payment_notifications(payment_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_stock_subscriptions_product ON stock_subscriptions(product_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_stock_subscriptions_user ON stock_subscriptions(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_referral_rewards_referrer ON referral_rewards(referrer_user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_referral_rewards_referred ON referral_rewards(referred_user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_purchase_product_date ON purchase_history(product_name, date)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tickets_unanswered ON support_tickets(is_answered) WHERE is_answered = 0")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tickets_user_date ON support_tickets(user_id, date)")

            await db.commit()

    # -------------------------------------------------------------
    # توابع مدیریت تنظیمات
    # -------------------------------------------------------------
    async def get_setting(self, key: str):
        cached = self.settings_cache.get(key)
        if cached is not None:
            return cached
        row = await self._fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        value = row[0] if row else None
        self.settings_cache.set(key, value)
        return value

    async def set_setting(self, key: str, value: str):
        await self._execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value), commit=True)
        self.settings_cache.set(key, value)
        await self._invalidate_cache("settings")

    # -------------------------------------------------------------
    # توابع مدیریت کاربران (با کش)
    # -------------------------------------------------------------
    async def get_user(self, user_id: int):
        cache_key = self._cache_key("get_user", user_id)
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached
        row = await self._fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if row:
            user = {
                'user_id': row[0], 'full_name': row[1], 'store_name': row[2], 'email': row[3],
                'card_number': row[4], 'phone_number': row[5], 'phone_verified': bool(row[6]) if len(row) > 6 else False, 'balance': row[7], 'is_rep': bool(row[8]),
                'discount_percentage': row[9], 'debt': row[10], 'credit_limit': row[11],
                'registration_date': row[12], 'banned': bool(row[13]), 'last_request_time': row[14],
                'is_financial_admin': bool(row[15]) if len(row) > 15 else False,
                'is_approved': bool(row[16]) if len(row) > 16 else False,
                'approved_by': row[17] if len(row) > 17 and row[17] is not None else 0,
                'approved_date': row[18] if len(row) > 18 else None,
                'referral_code': row[19] if len(row) > 19 else None,
                'referred_by': row[20] if len(row) > 20 and row[20] is not None else 0,
                'registration_status': row[21] if len(row) > 21 else 'new',
                'rejection_reason': row[22] if len(row) > 22 else ''
            }
            await self._set_cached(cache_key, user)
            return user
        return None

    async def create_user(self, user_id: int, full_name: str, phone_number: str):
        registration_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR IGNORE INTO users (user_id, full_name, phone_number, phone_verified, registration_date, is_approved, registration_status)
                VALUES (?, ?, ?, 0, ?, 0, 'new')
            ''', (user_id, full_name, phone_number, registration_date))
            await db.commit()
        await self._invalidate_cache("get_user")
        await self._invalidate_cache("get_all_users")

    async def update_user(self, user_id: int, **kwargs):
        if not kwargs:
            return
        set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values())
        values.append(user_id)
        await self._execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", tuple(values), commit=True)
        await self._invalidate_cache("get_user")
        await self._invalidate_cache("get_all_users")
        await self._invalidate_cache("get_all_reps")
        await self._invalidate_cache("get_all_debtors")
        await self._invalidate_cache("get_all_financial_admins")
        await self._invalidate_cache("get_all_banned_users")

    async def update_last_request_time(self, user_id: int):
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET last_request_time = ? WHERE user_id = ?", (current_time, user_id))
            await db.commit()
        await self._invalidate_cache("get_user")

    async def can_make_request(self, user_id: int, cooldown_seconds: int = 10) -> bool:
        user = await self.get_user(user_id)
        if not user or not user.get('last_request_time'):
            return True
        try:
            last_time = datetime.datetime.strptime(user['last_request_time'], "%Y-%m-%d %H:%M:%S")
            now = datetime.datetime.now()
            if (now - last_time).total_seconds() < cooldown_seconds:
                return False
        except (TypeError, ValueError):
            pass
        return True

    async def update_user_balance(self, user_id: int, amount: int, operation: str = "set"):
        async with aiosqlite.connect(self.db_path) as db:
            if operation == "add":
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            elif operation == "subtract":
                await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            else:
                await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
            await db.commit()
        await self._invalidate_cache("get_user")
        await self._invalidate_cache("get_all_users")

    async def update_user_debt(self, user_id: int, amount: int, operation: str = "set"):
        async with aiosqlite.connect(self.db_path) as db:
            if operation == "add":
                await db.execute("UPDATE users SET debt = debt + ? WHERE user_id = ?", (amount, user_id))
            elif operation == "subtract":
                await db.execute("UPDATE users SET debt = debt - ? WHERE user_id = ?", (amount, user_id))
            else:
                await db.execute("UPDATE users SET debt = ? WHERE user_id = ?", (amount, user_id))
            await db.commit()
        await self._invalidate_cache("get_user")
        await self._invalidate_cache("get_all_users")
        await self._invalidate_cache("get_all_reps")
        await self._invalidate_cache("get_all_debtors")

    async def update_user_credit_limit(self, user_id: int, new_limit: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET credit_limit = ? WHERE user_id = ?", (new_limit, user_id))
            await db.commit()
        await self._invalidate_cache("get_user")
        await self._invalidate_cache("get_all_reps")

    async def update_user_rep_status(self, user_id: int, is_rep: bool, discount: int = 0):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET is_rep = ?, discount_percentage = ? WHERE user_id = ?",
                           (int(is_rep), discount, user_id))
            await db.commit()
        await self._invalidate_cache("get_user")
        await self._invalidate_cache("get_all_users")
        await self._invalidate_cache("get_all_reps")
        await self._invalidate_cache("get_all_debtors")

    async def update_user_financial_admin_status(self, user_id: int, is_financial: bool):
        # Deprecated: این پروژه دیگر مفهوم «ادمین مالی» ندارد.
        await self._invalidate_cache("get_user")
        await self._invalidate_cache("get_all_users")

        return

    async def update_user_banned_status(self, user_id: int, banned: bool):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET banned = ? WHERE user_id = ?", (int(banned), user_id))
            await db.commit()
        await self._invalidate_cache("get_user")
        await self._invalidate_cache("get_all_users")
        await self._invalidate_cache("get_all_banned_users")

    async def get_all_users(self):
        cache_key = self._cache_key("get_all_users")
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM users")
            rows = await cursor.fetchall()
            users = []
            for row in rows:
                users.append({
                    'user_id': row[0], 'full_name': row[1], 'store_name': row[2], 'email': row[3],
                    'card_number': row[4], 'phone_number': row[5], 'phone_verified': bool(row[6]) if len(row) > 6 else False, 'balance': row[7], 'is_rep': bool(row[8]),
                    'discount_percentage': row[9], 'debt': row[10], 'credit_limit': row[11],
                    'registration_date': row[12], 'banned': bool(row[13]), 'last_request_time': row[14],
                    'is_financial_admin': bool(row[15]) if len(row) > 15 else False,
                    'is_approved': bool(row[16]) if len(row) > 16 else False,
                    'approved_by': row[17] if len(row) > 17 and row[17] is not None else 0,
                    'approved_date': row[18] if len(row) > 18 else None,
                    'referral_code': row[19] if len(row) > 19 else None,
                    'referred_by': row[20] if len(row) > 20 and row[20] is not None else 0,
                    'registration_status': row[21] if len(row) > 21 else 'new',
                    'rejection_reason': row[22] if len(row) > 22 else ''
                })
            await self._set_cached(cache_key, users)
            return users

    async def get_all_reps(self):
        cache_key = self._cache_key("get_all_reps")
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM users WHERE is_rep = 1")
            rows = await cursor.fetchall()
            users = []
            for row in rows:
                users.append({
                    'user_id': row[0], 'full_name': row[1], 'store_name': row[2], 'email': row[3],
                    'card_number': row[4], 'phone_number': row[5], 'phone_verified': bool(row[6]) if len(row) > 6 else False, 'balance': row[7], 'is_rep': bool(row[8]),
                    'discount_percentage': row[9], 'debt': row[10], 'credit_limit': row[11],
                    'registration_date': row[12], 'banned': bool(row[13]), 'is_financial_admin': bool(row[15]) if len(row) > 15 else False,
                    'is_approved': bool(row[16]) if len(row) > 16 else False,
                    'approved_by': row[17] if len(row) > 17 and row[17] is not None else 0,
                    'approved_date': row[18] if len(row) > 18 else None,
                    'referral_code': row[19] if len(row) > 19 else None,
                    'referred_by': row[20] if len(row) > 20 and row[20] is not None else 0,
                    'registration_status': row[21] if len(row) > 21 else 'new',
                    'rejection_reason': row[22] if len(row) > 22 else ''
                })
            await self._set_cached(cache_key, users)
            return users

    async def get_all_financial_admins(self):
        # Deprecated: این پروژه دیگر مفهوم «ادمین مالی» ندارد.
        return []

        cache_key = self._cache_key("get_all_financial_admins")
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT user_id, full_name FROM users WHERE is_financial_admin = 1")
            rows = await cursor.fetchall()
            result = [{'user_id': row[0], 'full_name': row[1]} for row in rows]
            await self._set_cached(cache_key, result)
            return result

    async def get_all_banned_users(self):
        cache_key = self._cache_key("get_all_banned_users")
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM users WHERE banned = 1")
            rows = await cursor.fetchall()
            users = []
            for row in rows:
                users.append({
                    'user_id': row[0], 'full_name': row[1], 'store_name': row[2], 'email': row[3],
                    'card_number': row[4], 'phone_number': row[5], 'phone_verified': bool(row[6]) if len(row) > 6 else False, 'balance': row[7], 'is_rep': bool(row[8]),
                    'discount_percentage': row[9], 'debt': row[10], 'credit_limit': row[11],
                    'registration_date': row[12], 'banned': bool(row[13]), 'is_financial_admin': bool(row[15]) if len(row) > 15 else False,
                    'is_approved': bool(row[16]) if len(row) > 16 else False,
                    'approved_by': row[17] if len(row) > 17 and row[17] is not None else 0,
                    'approved_date': row[18] if len(row) > 18 else None,
                    'referral_code': row[19] if len(row) > 19 else None,
                    'referred_by': row[20] if len(row) > 20 and row[20] is not None else 0,
                    'registration_status': row[21] if len(row) > 21 else 'new',
                    'rejection_reason': row[22] if len(row) > 22 else ''
                })
            await self._set_cached(cache_key, users)
            return users

    async def get_all_debtors(self):
        cache_key = self._cache_key("get_all_debtors")
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM users WHERE debt > 0 AND is_rep = 1")
            rows = await cursor.fetchall()
            users = []
            for row in rows:
                users.append({
                    'user_id': row[0], 'full_name': row[1], 'store_name': row[2], 'email': row[3],
                    'card_number': row[4], 'phone_number': row[5], 'phone_verified': bool(row[6]) if len(row) > 6 else False, 'balance': row[7], 'is_rep': bool(row[8]),
                    'discount_percentage': row[9], 'debt': row[10], 'credit_limit': row[11],
                    'registration_date': row[12], 'banned': bool(row[13]), 'is_financial_admin': bool(row[15]) if len(row) > 15 else False,
                    'is_approved': bool(row[16]) if len(row) > 16 else False,
                    'approved_by': row[17] if len(row) > 17 and row[17] is not None else 0,
                    'approved_date': row[18] if len(row) > 18 else None,
                    'referral_code': row[19] if len(row) > 19 else None,
                    'referred_by': row[20] if len(row) > 20 and row[20] is not None else 0,
                    'registration_status': row[21] if len(row) > 21 else 'new',
                    'rejection_reason': row[22] if len(row) > 22 else ''
                })
            await self._set_cached(cache_key, users)
            return users

    async def search_users(self, query: str):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM users WHERE
                full_name LIKE ? OR phone_number LIKE ?
            ''', (f'%{query}%', f'%{query}%'))
            rows = await cursor.fetchall()
            users = []
            for row in rows:
                users.append({
                    'user_id': row[0], 'full_name': row[1], 'store_name': row[2], 'email': row[3],
                    'card_number': row[4], 'phone_number': row[5], 'phone_verified': bool(row[6]) if len(row) > 6 else False, 'balance': row[7], 'is_rep': bool(row[8]),
                    'discount_percentage': row[9], 'debt': row[10], 'credit_limit': row[11],
                    'registration_date': row[12], 'banned': bool(row[13]), 'is_financial_admin': bool(row[15]) if len(row) > 15 else False,
                    'is_approved': bool(row[16]) if len(row) > 16 else False,
                    'approved_by': row[17] if len(row) > 17 and row[17] is not None else 0,
                    'approved_date': row[18] if len(row) > 18 else None,
                    'referral_code': row[19] if len(row) > 19 else None,
                    'referred_by': row[20] if len(row) > 20 and row[20] is not None else 0,
                    'registration_status': row[21] if len(row) > 21 else 'new',
                    'rejection_reason': row[22] if len(row) > 22 else ''
                })
            return users

    # -------------------------------------------------------------
    # توابع مدیریت دسته‌بندی‌ها و محصولات (با رمزنگاری)
    # -------------------------------------------------------------
    async def get_categories(self):
        cache_key = self._cache_key("get_categories")
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT id, name FROM categories ORDER BY id")
            rows = await cursor.fetchall()
            categories = []
            for row in rows:
                category = {'id': row[0], 'name': row[1], 'products': []}
                prod_cursor = await db.execute('''
                    SELECT id, name, price, description, openvpn_server, openvpn_secret, openvpn_download_link, openvpn_config FROM products WHERE category_id = ?
                ''', (category['id'],))
                prod_rows = await prod_cursor.fetchall()
                for prod_row in prod_rows:
                    product = {
                        'id': prod_row[0],
                        'name': prod_row[1],
                        'price': prod_row[2],
                        'description': prod_row[3],
                        'openvpn_server': prod_row[4] or '',
                        'openvpn_secret': prod_row[5] or '',
                        'openvpn_download_link': prod_row[6] or '',
                        'openvpn_config': prod_row[7] or '',
                        'accounts': []
                    }
                    acc_cursor = await db.execute('''
                        SELECT account_type, username, password, secret, server, port, config, extra_note
                        FROM product_accounts WHERE product_id = ?
                    ''', (product['id'],))
                    acc_rows = await acc_cursor.fetchall()
                    for acc_row in acc_rows:
                        acc_dict = {
                            'account_type': acc_row[0],
                            'username': self._decrypt(acc_row[1]) if acc_row[1] else '',
                            'password': self._decrypt(acc_row[2]) if acc_row[2] else '',
                            'secret': self._decrypt(acc_row[3]) if acc_row[3] else '',
                            'server': acc_row[4],
                            'port': acc_row[5],
                            'config': self._decrypt(acc_row[6]) if acc_row[6] else '',
                            'extra_note': acc_row[7]
                        }
                        product['accounts'].append(acc_dict)
                    category['products'].append(product)
                categories.append(category)
            await self._set_cached(cache_key, categories)
            return categories

    async def get_category_by_id(self, cat_id: int):
        cache_key = self._cache_key("get_category_by_id", cat_id)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT id, name FROM categories WHERE id = ?", (cat_id,))
            row = await cursor.fetchone()
            if row:
                category = {'id': row[0], 'name': row[1], 'products': []}
                prod_cursor = await db.execute('''
                    SELECT id, name, price, description, openvpn_server, openvpn_secret, openvpn_download_link, openvpn_config FROM products WHERE category_id = ?
                ''', (category['id'],))
                prod_rows = await prod_cursor.fetchall()
                for prod_row in prod_rows:
                    product = {
                        'id': prod_row[0],
                        'name': prod_row[1],
                        'price': prod_row[2],
                        'description': prod_row[3],
                        'openvpn_server': prod_row[4] or '',
                        'openvpn_secret': prod_row[5] or '',
                        'openvpn_download_link': prod_row[6] or '',
                        'openvpn_config': prod_row[7] or '',
                        'accounts': []
                    }
                    acc_cursor = await db.execute('''
                        SELECT account_type, username, password, secret, server, port, config, extra_note
                        FROM product_accounts WHERE product_id = ?
                    ''', (product['id'],))
                    acc_rows = await acc_cursor.fetchall()
                    for acc_row in acc_rows:
                        acc_dict = {
                            'account_type': acc_row[0],
                            'username': self._decrypt(acc_row[1]) if acc_row[1] else '',
                            'password': self._decrypt(acc_row[2]) if acc_row[2] else '',
                            'secret': self._decrypt(acc_row[3]) if acc_row[3] else '',
                            'server': acc_row[4],
                            'port': acc_row[5],
                            'config': self._decrypt(acc_row[6]) if acc_row[6] else '',
                            'extra_note': acc_row[7]
                        }
                        product['accounts'].append(acc_dict)
                    category['products'].append(product)
                await self._set_cached(cache_key, category)
                return category
            return None

    async def add_category(self, name: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                await db.commit()
                await self._invalidate_cache("get_categories")
                return True
            except aiosqlite.IntegrityError:
                return False

    async def rename_category(self, cat_id: int, new_name: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE categories SET name = ? WHERE id = ?", (new_name, cat_id))
            await db.commit()
        await self._invalidate_cache("get_categories")

    async def delete_category(self, cat_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
            await db.commit()
        await self._invalidate_cache("get_categories")

    async def add_product_to_category(self, category_id: int, name: str, price: int, description: str, openvpn_server: str = '', openvpn_secret: str = '', openvpn_download_link: str = '', openvpn_config: str = '') -> int:
        price = max(int(price), 1)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO products (category_id, name, price, price_min, price_max, description, openvpn_server, openvpn_secret, openvpn_download_link, openvpn_config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (category_id, name, price, price, price, description, openvpn_server or '', openvpn_secret or '', openvpn_download_link or '', openvpn_config or ''))
            await db.commit()
            cursor = await db.execute("SELECT last_insert_rowid()")
            product_id = (await cursor.fetchone())[0]
        await self._invalidate_cache("get_categories")
        return product_id

    async def update_product_price(self, product_id: int, new_price: int):
        price = max(int(new_price), 1)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE products SET price = ?, price_min = ?, price_max = ? WHERE id = ?", (price, price, price, product_id))
            await db.commit()
        await self._invalidate_cache("get_categories")

    async def update_product_description(self, product_id: int, new_description: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE products SET description = ? WHERE id = ?", (new_description, product_id))
            await db.commit()
        await self._invalidate_cache("get_categories")
    async def update_product_openvpn_settings(self, product_id: int, server: str = '', secret: str = '', download_link: str = '', config_value: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            if config_value is None:
                await db.execute(
                    "UPDATE products SET openvpn_server = ?, openvpn_secret = ?, openvpn_download_link = ? WHERE id = ?",
                    (server or '', secret or '', download_link or '', product_id)
                )
            else:
                await db.execute(
                    "UPDATE products SET openvpn_server = ?, openvpn_secret = ?, openvpn_download_link = ?, openvpn_config = ? WHERE id = ?",
                    (server or '', secret or '', download_link or '', config_value or '', product_id)
                )
            await db.commit()
        await self._invalidate_cache("get_categories")


    async def delete_product(self, product_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
            await db.commit()
        await self._invalidate_cache("get_categories")

    async def add_accounts_to_product(self, product_id: int, accounts: list):
        columns = [
            'product_id', 'account_type', 'username', 'password', 'secret',
            'server', 'port', 'config', 'extra_note'
        ]
        placeholders = ', '.join(['?'] * len(columns))
        insert_sql = (
            f"INSERT INTO product_accounts ({', '.join(columns)}) "
            f"VALUES ({placeholders})"
        )
        async with aiosqlite.connect(self.db_path) as db:
            for acc in accounts:
                port_value = acc.get('port', 0)
                try:
                    port_value = int(port_value or 0)
                except (TypeError, ValueError):
                    port_value = 0
                values = (
                    int(product_id),
                    str(acc.get('account_type', 'other') or 'other'),
                    self._encrypt(str(acc.get('username', '') or '')),
                    self._encrypt(str(acc.get('password', '') or '')),
                    self._encrypt(str(acc.get('secret', '') or '')),
                    str(acc.get('server', '') or ''),
                    port_value,
                    self._encrypt(str(acc.get('config', '') or '')),
                    str(acc.get('extra_note', '') or ''),
                )
                try:
                    await db.execute(insert_sql, values)
                except Exception:
                    logger.exception(
                        'Failed to insert product account. values_len=%s account_type=%s product_id=%s',
                        len(values), acc.get('account_type'), product_id
                    )
                    raise
            await db.commit()
        await self._invalidate_cache("get_categories")

    def format_account_display(self, acc: dict) -> str:
        acc_type = acc.get('account_type', 'other')
        if acc_type == 'openvpn':
            lines = []
            if acc.get('username'):
                lines.append(f"نام کاربری: {acc['username']}")
            if acc.get('password'):
                lines.append(f"رمز عبور: {acc['password']}")
            if acc.get('secret'):
                lines.append(f"کلید (Secret): {acc['secret']}")
            if acc.get('server'):
                lines.append(f"آدرس سرور: {acc['server']}")
            if acc.get('config'):
                cfg = acc['config']
                if isinstance(cfg, str) and cfg.startswith("FILE::"):
                    cfg_name = os.path.basename(cfg.split("::", 1)[1].split("|", 1)[0])
                    lines.append(f"فایل کانفیگ: {cfg_name}")
                else:
                    lines.append(f"فایل کانفیگ:\n{cfg}")
            if acc.get('extra_note'):
                lines.append(f"توضیحات: {acc['extra_note']}")
            return "\n".join(lines)
        elif acc_type == 'v2ray':
            if acc.get('config') and acc['config'].startswith(('vmess://', 'vless://', 'trojan://')):
                return acc['config']
            else:
                lines = []
                if acc.get('username'):
                    lines.append(f"نام کاربری: {acc['username']}")
                if acc.get('password'):
                    lines.append(f"رمز عبور: {acc['password']}")
                if acc.get('server'):
                    lines.append(f"سرور: {acc['server']}")
                if acc.get('port'):
                    lines.append(f"پورت: {acc['port']}")
                if acc.get('extra_note'):
                    lines.append(f"توضیحات: {acc['extra_note']}")
                return "\n".join(lines)
        else:
            lines = []
            if acc.get('username'):
                lines.append(f"نام کاربری: {acc['username']}")
            if acc.get('password'):
                lines.append(f"رمز عبور: {acc['password']}")
            if acc.get('server'):
                lines.append(f"سرور: {acc['server']}")
            if acc.get('config'):
                lines.append(f"اطلاعات اضافی: {acc['config']}")
            if acc.get('extra_note'):
                lines.append(f"توضیحات: {acc['extra_note']}")
            return "\n".join(lines)

    async def pop_account_from_product(self, product_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                cursor = await db.execute('''
                    SELECT id, account_type, username, password, secret, server, port, config, extra_note
                    FROM product_accounts WHERE product_id = ? ORDER BY id ASC LIMIT 1
                ''', (product_id,))
                row = await cursor.fetchone()
                if row:
                    account_id = row[0]
                    acc_dict = {
                        'account_type': row[1],
                        'username': self._decrypt(row[2]) if row[2] else '',
                        'password': self._decrypt(row[3]) if row[3] else '',
                        'secret': self._decrypt(row[4]) if row[4] else '',
                        'server': row[5],
                        'port': row[6],
                        'config': self._decrypt(row[7]) if row[7] else '',
                        'extra_note': row[8]
                    }
                    account_string = self.format_account_display(acc_dict)
                    await db.execute("DELETE FROM product_accounts WHERE id = ?", (account_id,))
                    await db.commit()
                    await self._invalidate_cache("get_categories")
                    return account_string
                await db.commit()
                return None
            except Exception as e:
                await db.rollback()
                raise e

    async def get_product_accounts_count(self, product_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM product_accounts WHERE product_id = ?", (product_id,))
            return (await cursor.fetchone())[0]

    async def get_all_products(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT id, name, price, description, openvpn_server, openvpn_secret, openvpn_download_link, openvpn_config FROM products")
            rows = await cursor.fetchall()
            products = []
            for row in rows:
                product = {
                    'id': row[0],
                    'name': row[1],
                    'price': row[2],
                    'description': row[3],
                    'openvpn_server': row[4] or '',
                    'openvpn_secret': row[5] or '',
                    'openvpn_download_link': row[6] or '',
                    'openvpn_config': row[7] or '',
                    'accounts': []
                }
                acc_cursor = await db.execute('''
                    SELECT account_type, username, password, secret, server, port, config, extra_note
                    FROM product_accounts WHERE product_id = ?
                ''', (product['id'],))
                acc_rows = await acc_cursor.fetchall()
                for acc_row in acc_rows:
                    acc_dict = {
                        'account_type': acc_row[0],
                        'username': self._decrypt(acc_row[1]) if acc_row[1] else '',
                        'password': self._decrypt(acc_row[2]) if acc_row[2] else '',
                        'secret': self._decrypt(acc_row[3]) if acc_row[3] else '',
                        'server': acc_row[4],
                        'port': acc_row[5],
                        'config': self._decrypt(acc_row[6]) if acc_row[6] else '',
                        'extra_note': acc_row[7]
                    }
                    product['accounts'].append(acc_dict)
                products.append(product)
            return products

    async def get_product_by_id(self, product_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT id, name, price, description, category_id, openvpn_server, openvpn_secret, openvpn_download_link, openvpn_config FROM products WHERE id = ?", (product_id,))
            row = await cursor.fetchone()
            if row:
                product = {
                    'id': row[0],
                    'name': row[1],
                    'price': row[2],
                    'description': row[3],
                    'category_id': row[4],
                    'openvpn_server': row[5] or '',
                    'openvpn_secret': row[6] or '',
                    'openvpn_download_link': row[7] or '',
                    'openvpn_config': row[8] or '',
                    'accounts': []
                }
                acc_cursor = await db.execute('''
                    SELECT account_type, username, password, secret, server, port, config, extra_note
                    FROM product_accounts WHERE product_id = ?
                ''', (product_id,))
                acc_rows = await acc_cursor.fetchall()
                for acc_row in acc_rows:
                    acc_dict = {
                        'account_type': acc_row[0],
                        'username': self._decrypt(acc_row[1]) if acc_row[1] else '',
                        'password': self._decrypt(acc_row[2]) if acc_row[2] else '',
                        'secret': self._decrypt(acc_row[3]) if acc_row[3] else '',
                        'server': acc_row[4],
                        'port': acc_row[5],
                        'config': self._decrypt(acc_row[6]) if acc_row[6] else '',
                        'extra_note': acc_row[7]
                    }
                    product['accounts'].append(acc_dict)
                return product
            return None

    # -------------------------------------------------------------
    # توابع مدیریت تاریخچه خرید
    # -------------------------------------------------------------
    async def get_unique_tracking_code(self) -> int:
        while True:
            code = random.randint(100000, 999999)
            purchase = await self.get_purchase_by_tracking_code(code)
            if not purchase:
                return code

    async def add_purchase(self, user_id: int, product_name: str, price: int, account: str, tracking_code: int = None,
                           bank_account_number: str = "نامشخص", payment_method: str = "wallet", approved_by: int = 0,
                           group_name: str = "") -> int:
        if tracking_code is None:
            tracking_code = await self.get_unique_tracking_code()
        date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        purchase_id = 0
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO purchase_history (user_id, product_name, price, account, date, tracking_code, bank_account_number, payment_method, approved_by, group_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, product_name, price, account, date, tracking_code, bank_account_number, payment_method, approved_by, group_name or ''))
            purchase_id = cursor.lastrowid or 0
            await db.commit()
        if purchase_id:
            await self.apply_referral_reward_for_purchase(user_id=user_id, purchase_id=int(purchase_id), tracking_code=int(tracking_code), purchase_amount=int(price))
        return tracking_code

    async def get_user_purchases(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT * FROM purchase_history WHERE user_id = ? ORDER BY date DESC
            ''', (user_id,))
            rows = await cursor.fetchall()
            purchases = []
            for row in rows:
                purchases.append({
                    'id': row[0], 'user_id': row[1], 'product_name': row[2], 'price': row[3],
                    'account': row[4], 'date': row[5], 'tracking_code': row[6], 'bank_account_number': row[7] if len(row) > 7 else 'نامشخص',
                    'payment_method': row[8] if len(row) > 8 else 'wallet', 'status': row[9] if len(row) > 9 else 'success',
                    'approved_by': row[10] if len(row) > 10 else 0,
                    'group_name': row[11] if len(row) > 11 and row[11] else ''
                })
            return purchases

    async def get_all_purchases(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM purchase_history ORDER BY date DESC")
            rows = await cursor.fetchall()
            purchases = []
            for row in rows:
                purchases.append({
                    'id': row[0], 'user_id': row[1], 'product_name': row[2], 'price': row[3],
                    'account': row[4], 'date': row[5], 'tracking_code': row[6], 'bank_account_number': row[7] if len(row) > 7 else 'نامشخص',
                    'payment_method': row[8] if len(row) > 8 else 'wallet', 'status': row[9] if len(row) > 9 else 'success',
                    'approved_by': row[10] if len(row) > 10 else 0,
                    'group_name': row[11] if len(row) > 11 and row[11] else ''
                })
            return purchases

    async def get_purchase_by_tracking_code(self, tracking_code: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM purchase_history WHERE tracking_code = ?", (tracking_code,))
            row = await cursor.fetchone()
            if row:
                return {
                    'id': row[0], 'user_id': row[1], 'product_name': row[2], 'price': row[3],
                    'account': row[4], 'date': row[5], 'tracking_code': row[6], 'bank_account_number': row[7] if len(row) > 7 else 'نامشخص',
                    'payment_method': row[8] if len(row) > 8 else 'wallet', 'status': row[9] if len(row) > 9 else 'success',
                    'approved_by': row[10] if len(row) > 10 else 0,
                    'group_name': row[11] if len(row) > 11 and row[11] else ''
                }
            return None

    # -------------------------------------------------------------
    # توابع مدیریت پشتیبانی
    # -------------------------------------------------------------
    async def add_support_ticket(self, user_id: int, full_name: str, message_text: str, tracking_code: int = None,
                                 category: str = 'general', priority: str = 'normal', related_payment_id: str = ''):
        date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO support_tickets (user_id, full_name, message_text, date, tracking_code, category, priority, status, related_payment_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)
            ''', (user_id, full_name, message_text, date, tracking_code, category or 'general', priority or 'normal', related_payment_id or ''))
            await db.commit()
            return cursor.lastrowid


    async def get_all_support_tickets(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM support_tickets ORDER BY date DESC")
            rows = await cursor.fetchall()
            tickets = []
            for row in rows:
                tickets.append({
                    'id': row[0], 'user_id': row[1], 'full_name': row[2], 'message_text': row[3],
                    'date': row[4], 'is_answered': bool(row[5]), 'tracking_code': row[6],
                    'category': row[7] if len(row) > 7 and row[7] else 'general',
                    'priority': row[8] if len(row) > 8 and row[8] else 'normal',
                    'status': row[9] if len(row) > 9 and row[9] else ('answered' if row[5] else 'open'),
                    'related_payment_id': row[10] if len(row) > 10 and row[10] else '',
                    'answered_at': row[11] if len(row) > 11 and row[11] else '',
                    'closed_at': row[12] if len(row) > 12 and row[12] else '',
                })
            return tickets

    async def get_unanswered_support_tickets(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM support_tickets WHERE status IN ('open','in_progress') ORDER BY date DESC")
            rows = await cursor.fetchall()
            tickets = []
            for row in rows:
                tickets.append({
                    'id': row[0], 'user_id': row[1], 'full_name': row[2], 'message_text': row[3],
                    'date': row[4], 'is_answered': bool(row[5]), 'tracking_code': row[6],
                    'category': row[7] if len(row) > 7 and row[7] else 'general',
                    'priority': row[8] if len(row) > 8 and row[8] else 'normal',
                    'status': row[9] if len(row) > 9 and row[9] else ('answered' if row[5] else 'open'),
                    'related_payment_id': row[10] if len(row) > 10 and row[10] else '',
                    'answered_at': row[11] if len(row) > 11 and row[11] else '',
                    'closed_at': row[12] if len(row) > 12 and row[12] else '',
                })
            return tickets

    async def update_support_ticket_status(self, ticket_id: int, status: str):
        status = (status or 'open').strip().lower()
        answered_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status in ('answered', 'closed') else ''
        closed_at = answered_at if status == 'closed' else ''
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE support_tickets SET status = ?, is_answered = ?, answered_at = CASE WHEN ? != '' THEN ? ELSE answered_at END, closed_at = CASE WHEN ? != '' THEN ? ELSE closed_at END WHERE id = ?",
                (status, int(status in ('answered', 'closed')), answered_at, answered_at, closed_at, closed_at, ticket_id)
            )
            await db.commit()

    async def mark_support_ticket_as_answered(self, ticket_id: int):
        await self.update_support_ticket_status(ticket_id, 'answered')

    # -------------------------------------------------------------
    # توابع مدیریت پرداخت بدهی / شارژ
    # -------------------------------------------------------------
    async def create_debt_payment(self, user_id: int, amount: int, file_name: str, payment_id: str, target_bank_id: int = 0, payment_method: str = "card", payment_network: str = "", payment_destination: str = ""):
        date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO debt_payments (payment_id, user_id, amount, file_name, date, status, target_bank_id, payment_method, payment_network, payment_destination)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (payment_id, user_id, amount, file_name, date, int(target_bank_id or 0), payment_method or "card", payment_network or "", payment_destination or ""),
            )
            await db.commit()

    async def get_debt_payment_by_id(self, payment_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM debt_payments WHERE payment_id = ?", (payment_id,))
            row = await cursor.fetchone()
            if row:
                return {
                    'id': row[0], 'payment_id': row[1], 'user_id': row[2], 'amount': row[3],
                    'file_name': row[4], 'date': row[5], 'status': row[6], 'approved_by': row[7] if len(row) > 7 else 0,
                    'target_bank_id': row[8] if len(row) > 8 and row[8] is not None else 0,
                    'payment_method': row[9] if len(row) > 9 and row[9] else 'card',
                    'payment_network': row[10] if len(row) > 10 and row[10] else '',
                    'payment_destination': row[11] if len(row) > 11 and row[11] else '',
                    'txid': row[12] if len(row) > 12 and row[12] else ''
                }
            return None

    async def update_debt_payment_txid(self, payment_id: str, txid: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE debt_payments SET txid = ? WHERE payment_id = ?", ((txid or '').strip(), payment_id))
            await db.commit()

    async def update_debt_payment_status(self, payment_id: str, status: str, approved_by: int = 0) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE debt_payments SET status = ?, approved_by = ? WHERE payment_id = ? AND status = 'pending'",
                (status, approved_by, payment_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_all_debt_payments(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM debt_payments ORDER BY date DESC")
            rows = await cursor.fetchall()
            payments = []
            for row in rows:
                payments.append({
                    'id': row[0], 'payment_id': row[1], 'user_id': row[2], 'amount': row[3],
                    'file_name': row[4], 'date': row[5], 'status': row[6], 'approved_by': row[7] if len(row) > 7 else 0,
                    'target_bank_id': row[8] if len(row) > 8 and row[8] is not None else 0,
                    'payment_method': row[9] if len(row) > 9 and row[9] else 'card',
                    'payment_network': row[10] if len(row) > 10 and row[10] else '',
                    'payment_destination': row[11] if len(row) > 11 and row[11] else '',
                    'txid': row[12] if len(row) > 12 and row[12] else ''
                })
            return payments

    async def get_user_debt_payments(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM debt_payments WHERE user_id = ? ORDER BY date DESC", (user_id,))
            rows = await cursor.fetchall()
            payments = []
            for row in rows:
                payments.append({
                    'id': row[0], 'payment_id': row[1], 'user_id': row[2], 'amount': row[3],
                    'file_name': row[4], 'date': row[5], 'status': row[6], 'approved_by': row[7] if len(row) > 7 else 0,
                    'target_bank_id': row[8] if len(row) > 8 and row[8] is not None else 0,
                    'payment_method': row[9] if len(row) > 9 and row[9] else 'card',
                    'payment_network': row[10] if len(row) > 10 and row[10] else '',
                    'payment_destination': row[11] if len(row) > 11 and row[11] else '',
                    'txid': row[12] if len(row) > 12 and row[12] else ''
                })
            return payments

    async def add_payment_notification(self, payment_id: str, chat_id: int, message_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO payment_notifications (payment_id, chat_id, message_id) VALUES (?, ?, ?)",
                (payment_id, int(chat_id), int(message_id))
            )
            await db.commit()

    async def get_payment_notifications(self, payment_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT chat_id, message_id FROM payment_notifications WHERE payment_id = ? ORDER BY id ASC",
                (payment_id,)
            )
            rows = await cursor.fetchall()
            return [{'chat_id': row[0], 'message_id': row[1]} for row in rows]

    async def clear_payment_notifications(self, payment_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM payment_notifications WHERE payment_id = ?", (payment_id,))
            await db.commit()

    async def get_bank_account_by_id(self, account_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, account_number, account_owner, is_active, is_default, user_id FROM bank_accounts WHERE id = ?",
                (account_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                'id': row[0],
                'account_number': row[1],
                'account_owner': row[2],
                'is_active': bool(row[3]),
                'is_default': bool(row[4]),
                'user_id': row[5] or 0,
            }

    async def get_low_stock_products(self, threshold: int = 5):
        threshold = max(0, int(threshold or 0))
        categories = await self.get_categories()
        low = []
        for category in categories:
            for product in category.get('products', []):
                stock = len(product.get('accounts', []))
                if stock <= threshold:
                    low.append({
                        'category_name': category.get('name', ''),
                        'product_id': product.get('id'),
                        'product_name': product.get('name', ''),
                        'stock': stock,
                    })
        low.sort(key=lambda x: (x['stock'], x['product_name']))
        return low

    async def get_sales_summary(self, days: int = 1):
        start = (datetime.datetime.now() - datetime.timedelta(days=max(0, int(days or 1)))).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*), COALESCE(SUM(price),0) FROM purchase_history WHERE status='success' AND date >= ?", (start,))
            purchase_count, total_sales = await cursor.fetchone()
            cursor = await db.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM debt_payments WHERE date >= ?", (start,))
            payment_count, total_payment_amount = await cursor.fetchone()
            cursor = await db.execute("SELECT COUNT(*) FROM debt_payments WHERE status='pending'")
            pending_payments = (await cursor.fetchone())[0]
            cursor = await db.execute("SELECT COUNT(*) FROM support_tickets WHERE status IN ('open','in_progress')")
            open_tickets = (await cursor.fetchone())[0]
            cursor = await db.execute("SELECT COUNT(*) FROM users WHERE registration_date >= ?", (start,))
            new_users = (await cursor.fetchone())[0]
        return {
            'purchase_count': purchase_count or 0,
            'total_sales': total_sales or 0,
            'payment_count': payment_count or 0,
            'total_payment_amount': total_payment_amount or 0,
            'pending_payments': pending_payments or 0,
            'open_tickets': open_tickets or 0,
            'new_users': new_users or 0,
        }

    async def get_total_stats(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            total_users = (await cursor.fetchone())[0]
            cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_rep = 1")
            rep_count = (await cursor.fetchone())[0]
            cursor = await db.execute("SELECT SUM(debt) FROM users WHERE is_rep = 1")
            total_debt = (await cursor.fetchone())[0] or 0
            cursor = await db.execute("SELECT SUM(price) FROM purchase_history WHERE status='success'")
            total_sales = (await cursor.fetchone())[0] or 0
            cursor = await db.execute('''
                SELECT product_name, COUNT(*), SUM(price) FROM purchase_history WHERE status='success' GROUP BY product_name
            ''')
            sales_stats = {}
            for row in await cursor.fetchall():
                sales_stats[row[0]] = {'count': row[1], 'total_price': row[2]}
            return {
                'total_users': total_users,
                'rep_count': rep_count,
                'total_debt': total_debt,
                'total_sales': total_sales,
                'sales_stats': sales_stats
            }

    # -------------------------------------------------------------
    # توابع مدیریت ادمین‌ها
    # -------------------------------------------------------------
    async def is_admin(self, user_id: int) -> bool:
        cache_key = self._cache_key("is_admin", user_id)
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached
        row = await self._fetchone("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        result = row is not None
        await self._set_cached(cache_key, result, ttl=300)
        return result

    async def add_admin(self, user_id: int, full_name: str, added_by: int):
        added_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR IGNORE INTO admins (user_id, full_name, added_by, added_date)
                VALUES (?, ?, ?, ?)
            ''', (user_id, full_name, added_by, added_date))
            await db.commit()

    async def remove_admin(self, user_id: int) -> bool:
        if user_id == self.admin_id:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            await db.commit()
            return True

    async def get_all_admins(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT user_id, full_name, is_main FROM admins")
            rows = await cursor.fetchall()
            return [{'user_id': row[0], 'full_name': row[1], 'is_main': bool(row[2])} for row in rows]

    # -------------------------------------------------------------
    # توابع مدیریت حساب‌های بانکی
    # -------------------------------------------------------------
    async def add_bank_account(self, account_number: str, account_owner: str, is_default: bool = False, user_id: int = 0):
        async with aiosqlite.connect(self.db_path) as db:
            if is_default:
                await db.execute("UPDATE bank_accounts SET is_default = 0")
            await db.execute('''
                INSERT INTO bank_accounts (account_number, account_owner, is_active, is_default, user_id)
                VALUES (?, ?, 1, ?, ?)
            ''', (account_number, account_owner, int(is_default), user_id))
            await db.commit()

    async def get_bank_accounts(self, active_only: bool = True):
        async with aiosqlite.connect(self.db_path) as db:
            if active_only:
                cursor = await db.execute("SELECT id, account_number, account_owner, is_default, user_id FROM bank_accounts WHERE is_active = 1")
            else:
                cursor = await db.execute("SELECT id, account_number, account_owner, is_default, user_id FROM bank_accounts")
            rows = await cursor.fetchall()
            return [{'id': row[0], 'account_number': row[1], 'account_owner': row[2], 'is_default': bool(row[3]), 'user_id': row[4]} for row in rows]

    async def set_default_bank_account(self, account_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE bank_accounts SET is_default = 0")
            await db.execute("UPDATE bank_accounts SET is_default = 1 WHERE id = ?", (account_id,))
            await db.commit()

    async def update_bank_account_status(self, account_id: int, is_active: bool):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE bank_accounts SET is_active = ? WHERE id = ?", (int(is_active), account_id))
            await db.commit()

    async def delete_bank_account(self, account_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM bank_accounts WHERE id = ?", (account_id,))
            await db.commit()

    async def get_default_bank_account(self):
        mode = await self.get_setting('bank_selection_mode')
        accounts = await self.get_bank_accounts(active_only=True)
        if not accounts:
            return None
        if mode == 'fixed':
            default = next((a for a in accounts if a['is_default']), None)
            return default if default else accounts[0]
        else:
            return random.choice(accounts)

    # -------------------------------------------------------------
    # توابع کمکی
    # -------------------------------------------------------------
    async def find_record_by_tracking_code(self, tracking_code: int, user_id: int = None):
        purchase = await self.get_purchase_by_tracking_code(tracking_code)
        if purchase:
            if user_id is None or purchase['user_id'] == user_id:
                return {'type': 'purchase', 'data': purchase}
        return None

    async def add_file_cleanup(self, file_name: str, days: int, user_id: int, purpose: str):
        expiry_date = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO file_cleanup (file_name, expiry_date, user_id, purpose)
                VALUES (?, ?, ?, ?)
            ''', (file_name, expiry_date, user_id, purpose))
            await db.commit()

    async def cleanup_expired_files(self):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT file_name, user_id, purpose FROM file_cleanup WHERE expiry_date < ?", (now,))
            rows = await cursor.fetchall()
            for row in rows:
                file_name = row[0]
                user_id = row[1]
                purpose = row[2]
                file_path = os.path.join("uploads", file_name)  # مسیر آپلودها باید یکسان با bot.py باشد
                if os.path.exists(file_path):
                    os.remove(file_path)
                await db.execute("DELETE FROM file_cleanup WHERE file_name = ?", (file_name,))
            await db.commit()

    # -------------------------------------------------------------
    # توابع مدیریت آموزش‌ها
    # -------------------------------------------------------------
    async def add_tutorial(self, title: str, content: str, created_by: int = 0):
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO tutorials (title, content, created_at, created_by, is_active) VALUES (?, ?, ?, ?, 1)",
                (title, content, created_at, created_by)
            )
            await db.commit()
            return cursor.lastrowid

    async def get_tutorials(self, active_only: bool = True):
        async with aiosqlite.connect(self.db_path) as db:
            if active_only:
                cursor = await db.execute("SELECT id, title, content, created_at, created_by, is_active FROM tutorials WHERE is_active = 1 ORDER BY id DESC")
            else:
                cursor = await db.execute("SELECT id, title, content, created_at, created_by, is_active FROM tutorials ORDER BY id DESC")
            rows = await cursor.fetchall()
            return [
                {
                    'id': row[0], 'title': row[1], 'content': row[2], 'created_at': row[3],
                    'created_by': row[4], 'is_active': bool(row[5])
                }
                for row in rows
            ]

    async def get_tutorial_by_id(self, tutorial_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, title, content, created_at, created_by, is_active FROM tutorials WHERE id = ?",
                (tutorial_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                'id': row[0], 'title': row[1], 'content': row[2], 'created_at': row[3],
                'created_by': row[4], 'is_active': bool(row[5])
            }

    async def delete_tutorial(self, tutorial_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM tutorials WHERE id = ?", (tutorial_id,))
            await db.commit()

    async def close(self):
        async with self._db_lock:
            if self._db is not None:
                await self._db.close()
                self._db = None

    async def apply_referral_reward_for_purchase(self, user_id: int, purchase_id: int, tracking_code: int, purchase_amount: int):
        try:
            enabled = (await self.get_setting('referral_system_enabled') or 'on').strip().lower()
            if enabled != 'on':
                return 0
        except Exception:
            return 0

        buyer = await self.get_user(user_id)
        if not buyer:
            return 0
        referrer_id = int(buyer.get('referred_by') or 0)
        if referrer_id <= 0 or referrer_id == user_id:
            return 0

        mode = (await self.get_setting('referral_reward_mode') or 'first_purchase').strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT 1 FROM referral_rewards WHERE purchase_id = ?", (purchase_id,))
            if await cursor.fetchone():
                return 0

            if mode == 'first_purchase':
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM purchase_history WHERE user_id = ? AND status = 'success'",
                    (user_id,)
                )
                count = (await cursor.fetchone())[0] or 0
                if int(count) > 1:
                    return 0

            try:
                reward_percent = float((await self.get_setting('referral_reward_percent') or '1').strip())
            except (TypeError, ValueError, AttributeError):
                reward_percent = 1.0
            reward_percent = max(0.0, reward_percent)
            reward_amount = int(int(purchase_amount) * (reward_percent / 100.0))
            if reward_amount <= 0:
                return 0

            created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await db.execute(
                """
                INSERT INTO referral_rewards (
                    referrer_user_id, referred_user_id, purchase_id, tracking_code,
                    purchase_amount, reward_percent, reward_amount, created_at, level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (referrer_id, user_id, purchase_id, tracking_code, int(purchase_amount), reward_percent, reward_amount, created_at)
            )
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                (reward_amount, referrer_id)
            )
            await db.commit()

        await self._invalidate_cache('get_user')
        await self._invalidate_cache('get_all_users')
        return reward_amount

    async def get_referral_chain(self, user_id: int, max_depth: int = 5):
        chain = []
        current_id = int(user_id or 0)
        visited = set()
        depth = 0
        while current_id and current_id not in visited and depth < max_depth:
            visited.add(current_id)
            user = await self.get_user(current_id)
            if not user:
                break
            chain.append({
                'user_id': current_id,
                'full_name': user.get('full_name', 'ناشناس'),
                'referral_code': user.get('referral_code') or '',
            })
            parent = int(user.get('referred_by') or 0)
            if parent <= 0:
                break
            current_id = parent
            depth += 1
        return list(reversed(chain))

    async def get_downline_tree(self, user_id: int, max_depth: int = 3):
        async def _children(parent_id: int, level: int):
            if level > max_depth:
                return []
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT user_id, full_name, is_approved FROM users WHERE referred_by = ? ORDER BY registration_date DESC",
                    (parent_id,)
                )
                rows = await cursor.fetchall()
            result = []
            for row in rows:
                node = {
                    'user_id': row[0],
                    'full_name': row[1],
                    'is_approved': bool(row[2]),
                    'level': level,
                    'children': await _children(row[0], level + 1),
                }
                result.append(node)
            return result

        return await _children(user_id, 1)

    async def get_referral_admin_report(self, user_id: int = None, limit: int = 20):
        async with aiosqlite.connect(self.db_path) as db:
            if user_id is None:
                cursor = await db.execute(
                    """
                    SELECT u.user_id, u.full_name, u.referral_code,
                           COUNT(DISTINCT c.user_id) AS referrals_count,
                           COALESCE(SUM(rr.reward_amount), 0) AS total_reward,
                           COALESCE(SUM(rr.purchase_amount), 0) AS downline_sales
                    FROM users u
                    LEFT JOIN users c ON c.referred_by = u.user_id AND c.is_approved = 1
                    LEFT JOIN referral_rewards rr ON rr.referrer_user_id = u.user_id
                    WHERE COALESCE(u.referral_code, '') <> ''
                    GROUP BY u.user_id, u.full_name, u.referral_code
                    HAVING referrals_count > 0 OR total_reward > 0
                    ORDER BY total_reward DESC, referrals_count DESC, u.user_id ASC
                    LIMIT ?
                    """,
                    (limit,)
                )
                rows = await cursor.fetchall()
                return [
                    {
                        'user_id': r[0], 'full_name': r[1], 'referral_code': r[2],
                        'referrals_count': r[3], 'total_reward': r[4], 'downline_sales': r[5],
                    } for r in rows
                ]

            cursor = await db.execute(
                """
                SELECT rr.id, rr.referred_user_id, u.full_name, rr.purchase_amount, rr.reward_percent, rr.reward_amount, rr.created_at, rr.tracking_code
                FROM referral_rewards rr
                LEFT JOIN users u ON u.user_id = rr.referred_user_id
                WHERE rr.referrer_user_id = ?
                ORDER BY rr.created_at DESC
                LIMIT ?
                """,
                (user_id, limit)
            )
            rows = await cursor.fetchall()
            return [
                {
                    'reward_id': r[0], 'referred_user_id': r[1], 'referred_full_name': r[2] or 'ناشناس',
                    'purchase_amount': r[3], 'reward_percent': r[4], 'reward_amount': r[5],
                    'created_at': r[6], 'tracking_code': r[7],
                } for r in rows
            ]

    async def get_referral_summary(self, user_id: int):
        user = await self.get_user(user_id)
        if not user:
            return {
                'referred_count': 0,
                'approved_referred_count': 0,
                'referred_users': [],
                'all_referred_users': [],
                'total_reward': 0,
                'downline_sales': 0,
                'chain': [],
                'tree': [],
            }

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT user_id, full_name, approved_date, registration_date, is_approved
                FROM users
                WHERE referred_by = ?
                ORDER BY COALESCE(approved_date, registration_date) DESC
                """,
                (user_id,)
            )
            rows = await cursor.fetchall()
            all_referred_users = [
                {
                    'user_id': row[0],
                    'full_name': row[1],
                    'approved_date': row[2],
                    'registration_date': row[3],
                    'is_approved': bool(row[4]),
                }
                for row in rows
            ]
            referred_users = [r for r in all_referred_users if r['is_approved']]

            cursor = await db.execute(
                "SELECT COALESCE(SUM(reward_amount), 0), COALESCE(SUM(purchase_amount), 0) FROM referral_rewards WHERE referrer_user_id = ?",
                (user_id,)
            )
            rewards_row = await cursor.fetchone()
            total_reward = int((rewards_row[0] or 0))
            downline_sales = int((rewards_row[1] or 0))

        chain = await self.get_referral_chain(user_id, max_depth=6)
        tree = await self.get_downline_tree(user_id, max_depth=3)

        return {
            'referred_count': len(all_referred_users),
            'approved_referred_count': len(referred_users),
            'referred_users': referred_users,
            'all_referred_users': all_referred_users,
            'total_reward': total_reward,
            'downline_sales': downline_sales,
            'chain': chain,
            'tree': tree,
        }

    async def get_user_by_referral_code(self, referral_code: str):
        if not referral_code:
            return None
        code = referral_code.strip().upper()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT user_id, full_name, is_approved, referral_code FROM users WHERE referral_code = ?",
                (code,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {'user_id': row[0], 'full_name': row[1], 'is_approved': bool(row[2]), 'referral_code': row[3]}

    async def generate_referral_code(self, user_id: int = None) -> str:
        while True:
            base = str(user_id)[-4:] if user_id else ''.join(random.choices('0123456789', k=4))
            code = f"R{base}{''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=4))}"
            exists = await self.get_user_by_referral_code(code)
            if not exists:
                return code

    async def approve_user_registration(self, user_id: int, approved_by: int = 0, referrer_user_id: int = 0) -> str:
        user = await self.get_user(user_id)
        if not user:
            raise ValueError("User not found")
        referral_code = user.get('referral_code') or await self.generate_referral_code(user_id)
        approved_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET is_approved = 1, approved_by = ?, approved_date = ?, referral_code = ?, referred_by = CASE WHEN ? > 0 THEN ? ELSE referred_by END, registration_status = 'approved', rejection_reason = '' WHERE user_id = ?",
                (approved_by, approved_date, referral_code, referrer_user_id, referrer_user_id, user_id)
            )
            await db.commit()
        await self._invalidate_cache("get_user")
        await self._invalidate_cache("get_all_users")
        return referral_code

    async def reject_user_registration(self, user_id: int, approved_by: int = 0, reason: str = ''):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET is_approved = 0, approved_by = ?, approved_date = ?, registration_status = 'rejected', rejection_reason = ? WHERE user_id = ?",
                (approved_by, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (reason or '').strip(), user_id)
            )
            await db.commit()
        await self._invalidate_cache("get_user")
        await self._invalidate_cache("get_all_users")

    async def get_pending_users(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT user_id, full_name, phone_number, registration_date, referred_by FROM users WHERE is_approved = 0 AND registration_status = 'pending_admin' ORDER BY registration_date DESC"
            )
            rows = await cursor.fetchall()
            return [{'user_id': r[0], 'full_name': r[1], 'phone_number': r[2], 'registration_date': r[3], 'referred_by': r[4]} for r in rows]

    async def resolve_random_price(self, product_id: int) -> int:
        product = await self.get_product_by_id(product_id)
        if not product:
            return 0
        return int(product.get('price') or 0)


    async def set_latest_openvpn_config(self, value: str):
        await self.set_setting('latest_openvpn_config', value or '')

    async def get_latest_openvpn_config(self) -> str:
        return await self.get_setting('latest_openvpn_config') or ''


    async def get_export_users_rows(self):
        return await self.get_all_users()

    async def get_export_products_rows(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT c.id, c.name, p.id, p.name, p.price, p.description,
                       (SELECT COUNT(*) FROM product_accounts pa WHERE pa.product_id = p.id) AS stock
                FROM products p
                JOIN categories c ON c.id = p.category_id
                ORDER BY c.id, p.id
            ''')
            rows = await cursor.fetchall()
            return [
                {
                    'category_id': row[0],
                    'category_name': row[1],
                    'product_id': row[2],
                    'product_name': row[3],
                    'price': row[4],
                    'description': row[5],
                    'stock': row[6] or 0,
                }
                for row in rows
            ]


    async def subscribe_product_stock(self, user_id: int, product_id: int):
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR IGNORE INTO stock_subscriptions (user_id, product_id, created_at) VALUES (?, ?, ?)", (int(user_id), int(product_id), created_at))
            await db.commit()

    async def unsubscribe_product_stock(self, user_id: int, product_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM stock_subscriptions WHERE user_id = ? AND product_id = ?", (int(user_id), int(product_id)))
            await db.commit()

    async def get_product_stock_subscribers(self, product_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT user_id FROM stock_subscriptions WHERE product_id = ? ORDER BY id ASC", (int(product_id),))
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def clear_product_stock_subscribers(self, product_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM stock_subscriptions WHERE product_id = ?", (int(product_id),))
            await db.commit()
