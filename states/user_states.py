from aiogram.fsm.state import State, StatesGroup

class UserStates(StatesGroup):
    registration_full_name = State()
    registration_phone = State()
    waiting_for_referral_code = State()
    waiting_for_topup_amount = State()
    waiting_for_credit_topup_amount = State()
    waiting_for_photo_receipt = State()
    waiting_for_topup_amount_from_user = State()
    waiting_for_full_name = State()
    waiting_for_store_name = State()
    waiting_for_email = State()
    waiting_for_debt_payment_amount = State()
    waiting_for_debt_payment_photo = State()
    waiting_for_support_message = State()
    waiting_for_support_with_tracking = State()
    waiting_for_bank_selection = State()
    waiting_for_channel_join = State()
    waiting_for_support_category = State()
    waiting_for_support_priority = State()
    waiting_for_payment_txid = State()

