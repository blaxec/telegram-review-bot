# file: states/game_states.py

from aiogram.fsm.state import State, StatesGroup

class CoinflipStates(StatesGroup):
    waiting_for_bet = State()
    waiting_for_custom_bet = State()
    waiting_for_choice = State()

class DepositStates(StatesGroup):
    choosing_plan = State()
    waiting_for_amount = State()

class DonationStates(StatesGroup):
    waiting_for_donation_amount = State()