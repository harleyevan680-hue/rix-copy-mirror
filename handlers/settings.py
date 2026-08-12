from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import ensure_user, get_user, get_autotrade_settings, save_autotrade_settings


def settings_text(user, auto, copy=None):
    username = f"@{user['username']}" if user.get('username') else "Not set"
    return (
        "⚙️ SETTINGS\n\n"
        "👤 ACCOUNT INFORMATION\n\n"
        f"Name: {user.get('full_name') or 'Not set'}\n"
        f"Username: {username}\n"
        f"Telegram ID: {user['telegram_id']}\n"
        f"Date Joined: {user.get('created_at') or 'Unknown'}\n"
        "Account Status: 🟢 ACTIVE\n\n"
        "📈 COPY SETTINGS\n\n"
        f"Copy Trading: {'🟢 ACTIVE' if copy and copy.get('active') else '🔴 OFF'}\n"
        f"Trader Chain: {copy.get('chain','—') if copy and copy.get('active') else '—'}\n"
        f"Followed Wallets: {1 if copy and copy.get('active') else 0}\n"
        "Supported Chains: ◎ SOL  Ξ ETH  🟡 BNB\n\n"
        "🤖 AUTOTRADE SETTINGS\n\n"
        f"SOL: {'🟢 ON' if auto['SOL']['enabled'] else '🔴 OFF'} | SL {auto['SOL']['sl']:.1f}% | TP {auto['SOL']['tp']:.1f}%\n"
        f"ETH: {'🟢 ON' if auto['ETH']['enabled'] else '🔴 OFF'} | SL {auto['ETH']['sl']:.1f}% | TP {auto['ETH']['tp']:.1f}%\n"
        f"BNB: {'🟢 ON' if auto['BNB']['enabled'] else '🔴 OFF'} | SL {auto['BNB']['sl']:.1f}% | TP {auto['BNB']['tp']:.1f}%\n"
        "\n🔔 NOTIFICATIONS\n\n"
        "Trade Alerts: 🟢 ON\nDeposit Alerts: 🟢 ON\nWithdrawal Alerts: 🟢 ON\nSystem Alerts: 🟢 ON\n\n"
        "🔐 SECURITY\n\n"
        "Wallet Monitoring: 🟢 ACTIVE\nPrivate Credentials: 🔒 NOT STORED\nWallet Connection: Public Address\n\n"
        "🌐 NETWORK SETTINGS\n\n"
        "◎ Solana: 🟢 Configured\nΞ Ethereum: 🟢 Configured\n🟡 BNB Smart Chain: 🟢 Configured"
    )


async def settings(update, context):
    q = update.callback_query
    await q.answer()
    user = get_user(q.from_user.id) or ensure_user(q.from_user)
    auto = get_autotrade_settings(q.from_user.id)
    from database import get_copy_trader
    copy = get_copy_trader(q.from_user.id)
    await q.edit_message_text(settings_text(user, auto, copy), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="back")]]))


async def auto_menu(update, context):
    q = update.callback_query
    await q.answer()
    a = get_autotrade_settings(q.from_user.id)
    text = (
        "🤖 Automated Trading\n\n"
        f"◎ SOL: {'🟢 ON' if a['SOL']['enabled'] else '🔴 OFF'} | SL {a['SOL']['sl']:.1f}% | TP {a['SOL']['tp']:.1f}%\n"
        f"Ξ ETH: {'🟢 ON' if a['ETH']['enabled'] else '🔴 OFF'} | SL {a['ETH']['sl']:.1f}% | TP {a['ETH']['tp']:.1f}%\n"
        f"🟡 BNB: {'🟢 ON' if a['BNB']['enabled'] else '🔴 OFF'} | SL {a['BNB']['sl']:.1f}% | TP {a['BNB']['tp']:.1f}%\n\n"
        "Auto-trading executes rule-based orders based on your stop-loss and take-profit settings."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Configure Autotrade", callback_data="auto_config")],
        [InlineKeyboardButton("🟢 Enable All", callback_data="auto_enable"), InlineKeyboardButton("🔴 Disable All", callback_data="auto_disable")],
        [InlineKeyboardButton("◀️ Back", callback_data="back")],
    ])
    await q.edit_message_text(text, reply_markup=kb)


async def auto_enable(update, context):
    q=update.callback_query; await q.answer(); save_autotrade_settings(q.from_user.id, enabled=True)
    await q.edit_message_text("✅ AUTO TRADING ENABLED\n\nAuto trading is now enabled on SOL, ETH and BNB.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="back")]]))


async def auto_disable(update, context):
    q=update.callback_query; await q.answer(); save_autotrade_settings(q.from_user.id, enabled=False)
    await q.edit_message_text("🛑 AUTO TRADING DISABLED\n\nAuto trading has been disabled on SOL, ETH and BNB.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="back")]]))


async def auto_config(update, context):
    q=update.callback_query; await q.answer()
    await q.edit_message_text("🤖 Configure Autotrade\n\nSelect the chain:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("◎ SOL", callback_data="auto_chain_SOL"), InlineKeyboardButton("Ξ ETH", callback_data="auto_chain_ETH"), InlineKeyboardButton("🟡 BNB", callback_data="auto_chain_BNB")],
        [InlineKeyboardButton("◀️ Back", callback_data="back")]
    ]))


async def auto_chain(update, context):
    q=update.callback_query; await q.answer(); chain=q.data.rsplit('_',1)[1]
    context.user_data.update(auto_stage="sl", auto_chain=chain)
    await q.edit_message_text(f"🤖 Autotrade — {chain}\n\nEnter stop-loss % (e.g. 10 for 10%):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back")]]))


async def auto_text(update, context):
    if context.user_data.get('auto_stage') is None:
        return False
    stage=context.user_data['auto_stage']; chain=context.user_data['auto_chain']; raw=update.message.text.strip()
    try: value=float(raw)
    except ValueError:
        await update.message.reply_text("❌ Enter a valid number."); return True
    if value < 0 or value > 1000:
        await update.message.reply_text("❌ Enter a percentage between 0 and 1000."); return True
    if stage=='sl':
        context.user_data['auto_sl']=value; context.user_data['auto_stage']='tp'
        await update.message.reply_text(f"✅ Stop-loss: {value:.1f}%\n\nEnter take-profit % (e.g. 50):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back")]])); return True
    if stage=='tp':
        context.user_data['auto_tp']=value; context.user_data['auto_stage']='max'
        await update.message.reply_text(f"✅ Take-profit: {value:.1f}%\n\nEnter max daily trades (e.g. 5):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back")]])); return True
    if stage=='max':
        max_trades=int(value)
        sl = context.user_data['auto_sl']; tp = context.user_data['auto_tp']
        save_autotrade_settings(update.effective_user.id, chain=chain, sl=sl, tp=tp, max_daily=max_trades, enabled=True)
        context.user_data.clear()
        await update.message.reply_text(f"✅ AUTOTRADE SETTINGS SAVED\n\nChain: {chain}\nStop-loss: {sl:.1f}%\nTake-profit: {tp:.1f}%\nMax daily trades: {max_trades}\n\n🟢 Autotrade enabled.")
        return True
    return False
