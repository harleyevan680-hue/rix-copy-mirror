"""Rule-based stop-loss / take-profit monitor for recorded positions.

This service never invents a price. It uses the configured market-price service
and only closes positions that have a real recorded entry cost. Real execution
is delegated to the chain-specific trading adapter when ENABLE_REAL_TRADING is
true; otherwise it records an ACTIVE paper execution.
"""
import logging
from database import get_users_with_positions, get_positions, get_autotrade_settings, get_position
from services.pricing import get_usd_price
from services.trading import sell

log=logging.getLogger(__name__)

async def scan_autotrade(bot=None):
    for uid in get_users_with_positions():
        try:
            settings=get_autotrade_settings(uid)
            positions=get_positions(uid)
            for pos in positions:
                mint=pos.get('mint') or ''
                asset='SOL' if mint=='So11111111111111111111111111111111111111112' else None
                # Native ETH/BNB positions are not represented by the same
                # Solana mint ledger, so only chain-specific position records
                # that can be priced safely are considered here.
                if not asset:
                    continue
                cfg=settings.get(asset)
                if not cfg or not cfg.get('enabled'):
                    continue
                price=await get_usd_price(asset)
                qty=float(pos.get('quantity_base') or 0)/1e9
                market=qty*price
                cost=float(pos.get('cost_usd') or 0)
                if cost <= 0:
                    continue
                pnl_pct=(market-cost)/cost*100
                trigger=None
                if cfg['tp']>0 and pnl_pct >= cfg['tp']:
                    trigger=f"TAKE PROFIT {cfg['tp']:.1f}%"
                elif cfg['sl']>0 and pnl_pct <= -cfg['sl']:
                    trigger=f"STOP LOSS {cfg['sl']:.1f}%"
                if not trigger:
                    continue
                # sell() accepts a percentage of the recorded position.
                sig, proceeds, status=await sell(uid,mint,100,'SOL')
                if bot:
                    await bot.send_message(uid, f"🤖 AUTOTRADE CLOSED\n\n◎ SOL\n\nTrigger: {trigger}\nP/L: {pnl_pct:+.2f}%\nProceeds: ${proceeds:,.2f}\nStatus: {status}\n\nTransaction: <code>{sig}</code>", parse_mode='HTML')
        except Exception:
            log.exception('autotrade scan failed for user %s',uid)
