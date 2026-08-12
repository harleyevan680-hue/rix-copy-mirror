import re
import uuid

from database import get_user_balance, change_balance, create_trade, upsert_position, get_position
from services.jupiter import jupiter, USDC_MINT, SOL_MINT
from config import MIN_TRADE_USD, MAX_TRADE_USD, ENABLE_REAL_TRADING

TOKENS = {"SOL": SOL_MINT, "USDC": USDC_MINT}

def clean_amount(text):
    return float(re.sub(r"[$, ]", "", text))

def _sim_id():
    return "9KiLP****" + uuid.uuid4().hex[:16].upper()

async def buy(user_id, mint, amount_usd, symbol):
    amount_usd = float(amount_usd)
    if amount_usd < MIN_TRADE_USD or amount_usd > MAX_TRADE_USD:
        raise ValueError(f"Trade size must be between ${MIN_TRADE_USD:.2f} and ${MAX_TRADE_USD:.2f}.")
    if amount_usd > get_user_balance(user_id):
        raise ValueError("Insufficient available balance.")

    # Jupiter quotes are read-only. They let trading mode use current market
    # pricing without requiring a private key or an on-chain transaction.
    base_in = int(round(amount_usd * 1_000_000))
    quote = await jupiter.quote(USDC_MINT, mint, base_in)
    out = int(quote.get("outAmount", 0))
    if out <= 0:
        raise ValueError("No tradable quote was returned for this token.")

    if ENABLE_REAL_TRADING:
        if not change_balance(user_id, -amount_usd):
            raise ValueError("Your available balance changed. Please try again.")
        try:
            sig = await jupiter.execute_quote(quote)
        except Exception:
            change_balance(user_id, amount_usd)
            raise
        status = "CONFIRMED"
    else:
        # Paper/active mode: the user's internal Telegram balance is the
        # trading balance. No blockchain transaction or private key is used.
        if not change_balance(user_id, -amount_usd):
            raise ValueError("Your available balance changed. Please try again.")
        sig = _sim_id()
        status = "ACTIVE"

    create_trade(user_id, symbol, "BUY", amount_usd, status, sig)
    upsert_position(user_id, mint, out, amount_usd)
    return sig, out, status

async def sell(user_id, mint, percent, symbol):
    pos = get_position(user_id, mint)
    if not pos:
        raise ValueError("You do not have an open position for this token.")
    pct = max(1, min(float(percent), 100))
    amount_base = int(pos["quantity_base"] * pct / 100)
    if amount_base <= 0:
        raise ValueError("The position is too small to sell.")

    quote = await jupiter.quote(mint, USDC_MINT, amount_base)
    usdc_out = int(quote.get("outAmount", 0))
    if usdc_out <= 0:
        raise ValueError("No sell quote was returned for this position.")
    proceeds = usdc_out / 1_000_000
    cost_reduction = float(pos["cost_usd"]) * (amount_base / pos["quantity_base"])

    if ENABLE_REAL_TRADING:
        sig = await jupiter.execute_quote(quote)
        status = "CONFIRMED"
    else:
        sig = _sim_id()
        status = "ACTIVE"

    upsert_position(user_id, mint, -amount_base, -cost_reduction)
    change_balance(user_id, proceeds)
    create_trade(user_id, symbol, "SELL", proceeds, status, sig)
    return sig, proceeds, status
