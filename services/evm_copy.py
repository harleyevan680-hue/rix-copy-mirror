"""EVM copy-trade monitor for ETH/BNB public trader wallets.

It focuses on the two most reliable swap shapes: native asset -> ERC-20 and
ERC-20 -> native asset. Token->token swaps can contain router/internal
movements that cannot be safely inferred from a generic public RPC response,
so they are ignored rather than guessed.
"""
import logging
from database import get_active_copy_traders, get_copy_remaining, change_copy_remaining, create_copy_trade, upsert_position, get_position, update_copy_signature
from services.evm import evm, NATIVE, CHAINS
from services.pricing import get_usd_price
from config import COPY_PER_TRADE_PERCENT, ENABLE_REAL_TRADING

log=logging.getLogger(__name__)

async def _native_price(chain):
    return await get_usd_price('ETH' if chain=='ETH' else 'BNB')

async def _process_chain(user, chain):
    address=user['wallet_address']; asset='ETH' if chain=='ETH' else 'BNB'
    transfers=await evm.transfers(chain,address)
    grouped={}
    for t in transfers:
        tx=t.get('hash')
        if tx: grouped.setdefault(tx,[]).append(t)
    out=[]
    for tx,ts in grouped.items():
        outgoing=[t for t in ts if (t.get('from') or '').lower()==address.lower()]
        incoming=[t for t in ts if (t.get('to') or '').lower()==address.lower()]
        native_out=next((t for t in outgoing if (t.get('asset') or asset).upper()==asset),None)
        native_in=next((t for t in incoming if (t.get('asset') or asset).upper()==asset),None)
        token_in=next((t for t in incoming if (t.get('asset') or '').upper() not in (asset,'') and t.get('rawContract',{}).get('address')),None)
        token_out=next((t for t in outgoing if (t.get('asset') or '').upper() not in (asset,'') and t.get('rawContract',{}).get('address')),None)
        if native_out and token_in:
            try: native_amount=float(native_out.get('value') or 0) if chain=='ETH' else int(native_out.get('value') or 0)/1e18
            except Exception: continue
            token=token_in['rawContract']['address']; raw=token_in.get('rawContract',{}).get('value') or '0x0'
            try: token_base=int(raw,16) if isinstance(raw,str) else int(raw)
            except Exception: token_base=0
            if native_amount<=0 or token_base<=0: continue
            price=await _native_price(chain); usd=native_amount*price; copy_usd=min(get_copy_remaining(user['telegram_id']),usd*COPY_PER_TRADE_PERCENT/100)
            if copy_usd<0.01: continue
            status='CONFIRMED' if ENABLE_REAL_TRADING else 'ACTIVE'; exec_hash='ACTIVE'
            if ENABLE_REAL_TRADING:
                quote=await evm.zero_x_quote(chain,NATIVE,token,int(copy_usd*10**18),evm.execution_address()); exec_hash=await evm.execute_quote(quote)
            change_copy_remaining(user['telegram_id'],-copy_usd)
            key=f'{chain}:{token}'
            upsert_position(user['telegram_id'],key,token_base,copy_usd,source_wallet=address,source_quantity_delta=token_base,source_entry_signature=tx)
            create_copy_trade(user['telegram_id'],token,'BUY',copy_usd,status,exec_hash); update_copy_signature(user['telegram_id'],tx)
            out.append({'telegram_id':user['telegram_id'],'signature':tx,'tx_hash':exec_hash,'side':'BUY','mint':token,'amount_usd':copy_usd,'status':'COPIED','mode':status})
        elif token_out and native_in:
            token=token_out['rawContract']['address']; key=f'{chain}:{token}'; pos=get_position(user['telegram_id'],key)
            if not pos: continue
            try: native_amount=float(native_in.get('value') or 0) if chain=='ETH' else int(native_in.get('value') or 0)/1e18
            except Exception: continue
            proceeds=native_amount*await _native_price(chain); status='CONFIRMED' if ENABLE_REAL_TRADING else 'ACTIVE'; exec_hash='ACTIVE'
            if ENABLE_REAL_TRADING:
                quote=await evm.zero_x_quote(chain,token,NATIVE,int(pos['quantity_base']),evm.execution_address()); exec_hash=await evm.execute_quote(quote)
            upsert_position(user['telegram_id'],key,-int(pos['quantity_base']),-float(pos['cost_usd']),source_quantity_delta=-int(pos['source_quantity_base']))
            change_copy_remaining(user['telegram_id'],proceeds); create_copy_trade(user['telegram_id'],token,'SELL',proceeds,status,exec_hash); update_copy_signature(user['telegram_id'],tx)
            out.append({'telegram_id':user['telegram_id'],'signature':tx,'tx_hash':exec_hash,'side':'SELL','mint':token,'amount_usd':proceeds,'status':'COPIED','mode':status,'realized_pnl':proceeds-float(pos['cost_usd'])})
    return out

async def scan_evm():
    events=[]
    for user in get_active_copy_traders():
        if user.get('chain') not in ('ETH','BNB'):
            continue
        try: events.extend(await _process_chain(user,user.get('chain','ETH')))
        except Exception: log.exception('EVM copy scan failed for %s',user['telegram_id'])
    return events
