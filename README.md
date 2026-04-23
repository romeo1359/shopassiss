# SonyTel Modular Bot

1. Copy `.env.example` to `.env`
2. Fill values
3. Install deps: `pip install -r requirements.txt`
4. Run: `python main.py`

Notes:
- Secrets are loaded only from `.env`.
- The deprecated financial admin role has been removed from active flows.
- Registration rejection supports an admin-provided reason.


## انتشار روی GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git
git push -u origin main
```

## نصب روی Ubuntu
روی سرور:
```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git
cd <YOUR_REPO>
chmod +x scripts/install_ubuntu.sh
sudo ./scripts/install_ubuntu.sh
```

پس از نصب:
```bash
sudo systemctl status telegram-shop-bot
sudo journalctl -u telegram-shop-bot -f
```

## به‌روزرسانی روی Ubuntu
بعد از pull کردن نسخه جدید:
```bash
chmod +x scripts/update_ubuntu.sh
sudo ./scripts/update_ubuntu.sh
```
