"""Automatic deposit detection for assigned public receiving addresses."""
import asyncio
import logging
from config import DEPOSIT_SCAN_INTERVAL, BSCSCAN_API_KEY, SOL_DEPOSIT_CONFIRMATIONS, ETH_DEPOSIT_CONFIRMATIONS, BNB_DEPOSIT_CONFIRMATIONS
from database import get_users_with_deposit_addresses, create_deposit, get_deposit_by_txid
from services.wallet_monitor import wallet_monitor
from services.deposit_addresses import get_user_deposit_address
from services.pricing import get_usd_price
from services.evm import evm

log = logging.getLogger(__name__)

async def _notify(bot, row, txid, asset, amount, network, usd):
    from config import ADMIN_IDS
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, f"🔔 AUTOMATIC DEPOSIT DETECTED\n\n👤 User ID: {row['telegram_id']}\n💰 {amount:.8f} {asset}\n💵 USD Value: ${usd:,.2f}\n🌐 {network}\n🔗 <code>{txid}</code>\n\n🟡 Awaiting admin approval.", parse_mode='HTML')
        except Exception:
            log.exception('admin deposit notification failed')

async def _sol_for_user(row):
    uid=row['telegram_id']; address=get_user_deposit_address(uid,'SOL')
    if not address: return []
    sigs=await wallet_monitor.get_signatures(address,50)
    out=[]
    for item in sigs:
        sig=item.get('signature')
        if not sig or item.get('err'): continue
        if get_deposit_by_txid(sig): continue
        try:
            status_resp = await wallet_monitor.rpc("getSignatureStatuses", [[sig], {"searchTransactionHistory": True}])
            status_val = (status_resp or [None])[0] if isinstance(status_resp, list) else None
            if not status_val or status_val.get("err") is not None:
                continue
            confirmation = status_val.get("confirmationStatus")
            if confirmation not in ("confirmed", "finalized"):
                continue
        except Exception:
            continue
        tx=await wallet_monitor.get_transaction(sig)
        if not tx: continue
        meta=tx.get('meta') or {}; msg=((tx.get('transaction') or {}).get('message') or {})
        keys=msg.get('accountKeys') or []
        idx=None
        for i,k in enumerate(keys):
            pub=k.get('pubkey') if isinstance(k,dict) else str(k)
            if pub==address: idx=i; break
        if idx is None: continue
        pre=(meta.get('preBalances') or []); post=(meta.get('postBalances') or [])
        if idx>=len(pre) or idx>=len(post): continue
        delta=post[idx]-pre[idx]
        if delta<=0: continue
        amount=delta/1e9
        if amount<=0: continue
        out.append((sig,'SOL',amount,'Solana'))
    return out

async def _evm_for_user(row, chain):
    uid=row['telegram_id']; asset=chain; address=get_user_deposit_address(uid,asset)
    if not address: return []
    transfers=await evm.transfers(chain,address)
    out=[]
    for t in transfers:
        if (t.get('to') or '').lower()!=address.lower(): continue
        tx=t.get('hash') or t.get('uniqueId')
        if not tx or get_deposit_by_txid(tx): continue
        value=t.get('value')
        if value is None: continue
        if chain=='BNB' and isinstance(value,str) and value.isdigit():
            amount=int(value)/1e18
        else:
            amount=float(value)
        symbol=(t.get('asset') or asset).upper()
        if chain=='BNB' and symbol in ('','BNB'):
            symbol='BNB'
        if symbol != asset: continue
        try:
            receipt = await evm.rpc(chain, 'eth_getTransactionReceipt', [tx])
            if not receipt or receipt.get('status') not in (None, '0x1'):
                continue
            block = receipt.get('blockNumber')
            latest = await evm.rpc(chain, 'eth_blockNumber', [])
            if block and latest:
                confirmations = int(latest, 16) - int(block, 16) + 1
                required = ETH_DEPOSIT_CONFIRMATIONS if chain == 'ETH' else BNB_DEPOSIT_CONFIRMATIONS
                if confirmations < required:
                    continue
        except Exception:
            continue
        out.append((tx,asset,amount,'Ethereum' if chain=='ETH' else 'BNB Smart Chain'))
    return out

async def scan_deposits(bot):
    for row in get_users_with_deposit_addresses():
        jobs=[(_sol_for_user,(row,)),(_evm_for_user,(row,'ETH')),(_evm_for_user,(row,'BNB'))]
        for fn,args in jobs:
            try:
                items=await fn(*args)
                for txid,asset,amount,network in items:
                    if get_deposit_by_txid(txid):
                        continue
                    try:
                        price=await get_usd_price(asset)
                    except Exception:
                        price=0.0
                    usd=amount*price
                    create_deposit(row['telegram_id'],asset,amount,txid,usd_value=usd,price_usd=price,network=network)
                    await _notify(bot,row,txid,asset,amount,network,usd)
            except Exception:
                log.exception('deposit scan failed for user %s',row['telegram_id'])
