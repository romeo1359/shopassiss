# ربات دستیار فروشگاه نسخه 1

1. Copy `.env.example` to `.env`
2. Fill values
3. Install deps: `pip install -r requirements.txt`
4. Run: `python main.py`

Notes:
- Secrets are loaded only from `.env`.
- The deprecated financial admin role has been removed from active flows.
- Registration rejection supports an admin-provided reason.



## نصب روی Ubuntu
bash -c "$(curl -fsSL https://raw.githubusercontent.com/romeo1359/shopassiss/main/scripts/install_ubuntu.sh)"

اگر روی سرور curl نصب نبود، این نسخه را بزن
sudo apt update && sudo apt install -y curl && bash -c "$(curl -fsSL https://raw.githubusercontent.com/romeo1359/shopassiss/main/scripts/install_ubuntu.sh)"

  برای چک کردن وضعیت ربات:
  sudo systemctl status telegram-shop-bot

  و برای دیدن لاگ زنده:
  sudo journalctl -u telegram-shop-bot -f
