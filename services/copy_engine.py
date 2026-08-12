import logging
import uuid

from config import COPY_PER_TRADE_PERCENT, ENABLE_REAL_TRADING
from database import (
    get_active_copy_traders,
    update_copy_signature,
    get_copy_remaining,
    change_copy_remaining,
    get_position,
    upsert_position,
    adjust_position_source_quantity,
    set_position_source_quantity,
    create_copy_trade,
)
from services.wallet_monitor import wallet_monitor
from services.jupiter import jupiter, USDC_MINT, SOL_MINT

logger = logging.getLogger(__name__)

# Common Solana stablecoin. Jupiter can quote it directly; all P/L is normalized to USDC.
BASE_MINTS = {USDC_MINT, SOL_MINT}


def _token_deltas(tx, wallet):
    """Return signed raw token deltas for accounts owned by wallet."""
    meta = (tx or {}).get("meta") or {}
    pre = {}
    post = {}

    for b in meta.get("preTokenBalances") or []:
        if b.get("owner") != wallet:
            continue
        mint = b.get("mint")
        amount = int((b.get("uiTokenAmount") or {}).get("amount") or 0)
        pre[mint] = pre.get(mint, 0) + amount

    for b in meta.get("postTokenBalances") or []:
        if b.get("owner") != wallet:
            continue
        mint = b.get("mint")
        amount = int((b.get("uiTokenAmount") or {}).get("amount") or 0)
        post[mint] = post.get(mint, 0) + amount

    deltas = {
        mint: post.get(mint, 0) - pre.get(mint, 0)
        for mint in set(pre) | set(post)
        if post.get(mint, 0) != pre.get(mint, 0)
    }
    return deltas, pre


def _native_sol_delta(tx, wallet):
    """Get the wallet's lamport delta, if accountKeys are available."""
    meta = (tx or {}).get("meta") or {}
    message = ((tx or {}).get("transaction") or {}).get("message") or {}
    keys = message.get("accountKeys") or []

    idx = None
    for i, key in enumerate(keys):
        pubkey = key.get("pubkey") if isinstance(key, dict) else str(key)
        if pubkey == wallet:
            idx = i
            break

    if idx is None:
        return 0

    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []
    if idx >= len(pre) or idx >= len(post):
        return 0
    return int(post[idx]) - int(pre[idx])


async def _usd_value(mint, amount_base):
    """Normalize a token amount to an estimated USDC value."""
    if amount_base <= 0:
        return 0.0
    if mint == USDC_MINT:
        return amount_base / 1_000_000
    quote = await jupiter.quote(mint, USDC_MINT, amount_base)
    out = int(quote.get("outAmount", 0))
    return out / 1_000_000 if out > 0 else 0.0


async def _active_quote(input_mint, output_mint, amount_base):
    return await jupiter.quote(input_mint, output_mint, amount_base)


def _sim_id():
    return "5UfD*****" + uuid.uuid4().hex[:16].upper()


async def _execute_or_simulate(quote):
    if ENABLE_REAL_TRADING:
        return await jupiter.execute_quote(quote), "CONFIRMED"
    return _sim_id(), "ACTIVE"


async def _open_base_position(user, source_sig, out_mint, source_out_base, source_spend_mint, source_spend_base):
    """Mirror a source base-asset buy using the configured copy percentage."""
    uid = user["telegram_id"]
    remaining = get_copy_remaining(uid)
    if remaining <= 0:
        return None

    source_usd = await _usd_value(source_spend_mint, source_spend_base)
    copy_usd = min(
        remaining,
        source_usd * COPY_PER_TRADE_PERCENT / 100.0,
    )
    # Do not create a position that would display as $0.00.
    # A real allocation must be meaningfully positive.
    if copy_usd < 0.01:
        return None

    quote = await _active_quote(USDC_MINT, out_mint, int(copy_usd * 1_000_000))
    user_out = int(quote.get("outAmount", 0))
    if user_out <= 0:
        return None

    # In real mode, the execution wallet would need the input USDC. In
    # trading mode, only the internal copy allocation is changed.
    tx_hash, status = await _execute_or_simulate(quote)

    if not change_copy_remaining(uid, -copy_usd):
        return None

    upsert_position(
        uid,
        out_mint,
        user_out,
        copy_usd,
        source_wallet=user["wallet_address"],
        source_quantity_delta=source_out_base,
        source_entry_signature=source_sig,
    )

    trade_id = create_copy_trade(
        uid, out_mint, "BUY", copy_usd, status, tx_hash
    )
    update_copy_signature(uid, source_sig)

    return {
        "signature": source_sig,
        "status": "COPIED",
        "mode": status,
        "tx_hash": tx_hash,
        "side": "BUY",
        "mint": out_mint,
        "amount_usd": copy_usd,
        "trade_id": trade_id,
    }


async def _close_position(user, source_sig, in_mint, source_sold_base, source_pre_base, out_mint=None):
    """Mirror a proportional source sell against the linked active position."""
    uid = user["telegram_id"]
    pos = get_position(uid, in_mint)
    if not pos:
        # We deliberately do not invent a position when the source sells an
        # asset that this user never copied.
        return None

    source_position_base = int(pos.get("source_quantity_base") or 0)
    if source_position_base <= 0:
        # Legacy positions without source quantity: fall back once to source
        # wallet pre-balance, then record the source quantity going forward.
        source_position_base = int(source_pre_base or 0)

    if source_position_base <= 0:
        return None

    fraction = max(0.0, min(1.0, source_sold_base / source_position_base))
    if fraction <= 0:
        return None

    user_sell_base = int(int(pos["quantity_base"]) * fraction)
    if user_sell_base <= 0:
        return None

    # Value the copied sale in USDC for P/L accounting. For a token->token
    # source swap, execute/simulate the actual same token-to-token direction;
    # for a token->base close, execute/simulate the direct token->USDC route.
    quote_to_usdc = await _active_quote(in_mint, USDC_MINT, user_sell_base)
    proceeds = int(quote_to_usdc.get("outAmount", 0)) / 1_000_000
    if proceeds <= 0:
        return None

    execution_quote = quote_to_usdc
    output_base = 0
    if out_mint and out_mint not in BASE_MINTS:
        execution_quote = await _active_quote(in_mint, out_mint, user_sell_base)
        output_base = int(execution_quote.get("outAmount", 0))
        if output_base <= 0:
            return None

    tx_hash, status = await _execute_or_simulate(execution_quote)
    cost_reduction = float(pos["cost_usd"]) * fraction

    # Remove the sold portion from the source-linked position.
    upsert_position(
        uid,
        in_mint,
        -user_sell_base,
        -cost_reduction,
        source_wallet=user["wallet_address"],
        source_quantity_delta=-source_sold_base,
    )

    # If this is token -> token, immediately carry the active proceeds into
    # the new output position. This mirrors the swap without touching cash.
    if out_mint and out_mint not in BASE_MINTS:
        if output_base <= 0:
            return None

        upsert_position(
            uid,
            out_mint,
            output_base,
            proceeds,
            source_wallet=user["wallet_address"],
            source_quantity_delta=0,
            source_entry_signature=source_sig,
        )
        action_amount = proceeds
    else:
        change_copy_remaining(uid, proceeds)
        action_amount = proceeds

    trade_id = create_copy_trade(
        uid,
        in_mint,
        "SELL",
        proceeds,
        status,
        tx_hash,
    )
    update_copy_signature(uid, source_sig)

    return {
        "signature": source_sig,
        "status": "COPIED",
        "mode": status,
        "tx_hash": tx_hash,
        "side": "SELL",
        "mint": in_mint,
        "amount_usd": action_amount,
        "trade_id": trade_id,
        "fraction": fraction,
        "proceeds": proceeds,
        "cost_reduction": cost_reduction,
        "realized_pnl": proceeds - cost_reduction,
        "token_to_token": bool(out_mint and out_mint not in BASE_MINTS),
        "output_base": output_base,
    }


async def process_copy_trade(user, tx):
    """Process one confirmed source transaction.

    The source position ledger is authoritative for matching closes. This
    prevents an unrelated wallet holding of the same mint from being mistaken
    for the copied position.
    """
    sig = tx.get("signature")
    if not sig or tx.get("err"):
        return None

    full = await wallet_monitor.get_transaction(sig)
    if not full or (full.get("meta") or {}).get("err"):
        return None

    deltas, pre = _token_deltas(full, user["wallet_address"])
    sol_delta = _native_sol_delta(full, user["wallet_address"])

    if sol_delta:
        deltas[SOL_MINT] = deltas.get(SOL_MINT, 0) + sol_delta

    negative = [(mint, -delta) for mint, delta in deltas.items() if delta < 0]
    positive = [(mint, delta) for mint, delta in deltas.items() if delta > 0]

    if not negative or not positive:
        return None

    # Ignore pure SOL fee-only transactions and choose the largest meaningful
    # asset movement on each side.
    negative.sort(key=lambda x: x[1], reverse=True)
    positive.sort(key=lambda x: x[1], reverse=True)
    in_mint, in_base = negative[0]
    out_mint, out_base = positive[0]

    # Base asset -> token = open a copied position.
    if in_mint in BASE_MINTS and out_mint not in BASE_MINTS:
        return await _open_base_position(
            user,
            sig,
            out_mint,
            out_base,
            in_mint,
            in_base,
        )

    # Token -> base asset = close a copied position proportionally.
    if in_mint not in BASE_MINTS and out_mint in BASE_MINTS:
        return await _close_position(
            user,
            sig,
            in_mint,
            in_base,
            pre.get(in_mint, 0),
            out_mint=None,
        )

    # Token -> token: close the source-linked input position and roll its
    # active proceeds into the output token.
    if in_mint not in BASE_MINTS and out_mint not in BASE_MINTS:
        result = await _close_position(
            user,
            sig,
            in_mint,
            in_base,
            pre.get(in_mint, 0),
            out_mint=out_mint,
        )
        if not result:
            return None

        # Set the source quantity of the newly opened output position to the
        # actual source output quantity. This is what makes later partial sells
        # match against the trader's own copied position rather than wallet-wide
        # balances.
        set_position_source_quantity(
            user["telegram_id"],
            out_mint,
            result.get("output_base", out_base),
            source_entry_signature=sig,
        )
        return result

    return None


async def scan_once():
    events = []

    for user in get_active_copy_traders():
        if user.get("chain", "SOL") != "SOL":
            continue
        try:
            signatures = await wallet_monitor.get_signatures(
                user["wallet_address"],
                100,
            )
            last = user.get("last_signature")
            new = []

            for item in signatures:
                if item.get("signature") == last:
                    break
                new.append(item)

            # Process oldest -> newest so an opening position exists before
            # its closing transaction is evaluated.
            for item in reversed(new):
                result = await process_copy_trade(user, item)
                if result:
                    events.append((user, result))

                # Advance the cursor even for unsupported/irrelevant confirmed
                # transactions so they are never repeatedly reconsidered.
                update_copy_signature(user["telegram_id"], item["signature"])

        except Exception:
            logger.exception(
                "Copy scan failed for user %s",
                user["telegram_id"],
            )

    return events
