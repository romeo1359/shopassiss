# Project Structure

- `main.py`: entry point and scheduler bootstrap
- `app.py`: shared bot, dispatcher, and data manager instances
- `config.py`: environment-backed configuration and constants
- `database/data_manager.py`: database layer
- `handlers/user/`: user flows split by domain
- `handlers/admin/`: admin flows split by domain
- `keyboards/`: inline and reply keyboards
- `states/`: FSM states
- `middlewares/`: middleware registration and access control
- `utils/`: helpers and payment-specific utilities

## Run

```bash
pip install -r requirements.txt
python main.py
```
