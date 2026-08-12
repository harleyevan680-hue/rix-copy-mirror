import logging

logger = logging.getLogger(__name__)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import ensure_user, get_user_balance, get_copy_trader, stop_copy_trading, reserve_copy_allocation, get_positions
from handlers.ui import main_menu, back
from config import MIN_TRADE_USD, MAX_TRADE_USD
from services.jupiter import SOL_MINT

async def _asset_balance_lines(uid):
    from database import get_asset_balances
    from services.pricing import get_usd_price

    balances = get_asset_balances(uid)
    prices = {}
    for asset in ('SOL', 'ETH', 'BNB'):
        try:
            prices[asset] = await get_usd_price(asset)
        except Exception:
            prices[asset] = 0.0

    labels = {'SOL': '◎ SOL', 'ETH': 'Ξ ETH', 'BNB': '🟡 BNB'}
    lines = []
    for asset in ('SOL', 'ETH', 'BNB'):
        amount = float(balances.get(asset, 0.0))
        usd = amount * prices.get(asset, 0.0)
        lines.append(
            f"{labels[asset]}\n"
            f"   {amount:,.6f} {asset}\n"
            f"   ${usd:,.2f} USD"
        )
    return "\n\n".join(lines), balances, prices


async def _dashboard_text(uid):
    from database import get_asset_balances, get_copy_trader, get_positions
    b=get_asset_balances(uid); t=get_copy_trader(uid); positions=get_positions(uid)
    balance_lines, b, prices = await _asset_balance_lines(uid)
    portfolio=sum(b[a]*prices.get(a,0.0) for a in ('SOL','ETH','BNB'))
    from services.deposit_addresses import get_user_deposit_address
    sol_addr=get_user_deposit_address(uid,'SOL') or 'Not configured'
    eth_addr=get_user_deposit_address(uid,'ETH') or 'Not configured'
    bnb_addr=get_user_deposit_address(uid,'BNB') or 'Not configured'
    def short(a):
        return a if a == 'Not configured' or len(a) <= 18 else a[:9]+'...'+a[-7:]
    return (
        "💼 Wallet Overview — ✅ Connected\n\n"
        f"◎ SOL Address: {short(sol_addr)}\n"
        f"Ξ ETH Address: {short(eth_addr)}\n"
        f"🟡 BNB Address: {short(bnb_addr)}\n\n"
        "💰 ASSET BALANCES\n\n"
        f"{balance_lines}\n\n"
        f"💵 TOTAL PORTFOLIO VALUE\n${portfolio:,.2f} USD\n\n"
        f"📈 Active Copy Trades: {1 if t and t.get('active') else 0}\n"
        f"📂 Open Positions: {len(positions)}\n"
        f"👛 Followed Wallets: {1 if t and t.get('active') else 0}\n\n"
        "🤖 Mode: ACTIVE\n🟢 Bot Status: Running\n🔄 Copy Execution: Active\n🔐 Wallet Security: Protected"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from database import ensure_user
    u=ensure_user(update.effective_user)
    for aid in __import__('config').ADMIN_IDS:
        try:
            await context.bot.send_message(aid, f"🔔 NEW USER STARTED\n\n👤 Name: {update.effective_user.full_name}\n🔹 Username: @{update.effective_user.username if update.effective_user.username else 'none'}\n🆔 Telegram ID: {update.effective_user.id}\n📅 Date Joined: {u.get('created_at','')}\n\n🟢 Account: ACTIVE")
        except Exception: logger.exception('admin notification failed')
    await update.effective_message.reply_text(
        "👋 Welcome to Riz Copy Mirror!\n\nThe ultimate copy trading experience.\n\n📈 Mirror top-performing wallets instantly, discover profitable opportunities, and trade smarter with powerful automation.\n\n🤖 Riz Copy Mirror executes trades in real time, helping you stay ahead without constantly watching charts.\n\nℹ️ Type /help anytime to view the complete bot guide.\n\n🔗 Initializing your account...\n\n✅ Wallet successfully created and linked!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 CONTINUE",callback_data="home")]]))

async def home(update, context):
    q=update.callback_query
    if not q:return
    await q.answer(); context.user_data.clear()
    from services.deposit_addresses import get_user_deposit_address
    await q.edit_message_text(await _dashboard_text(q.from_user.id),reply_markup=main_menu(get_user_deposit_address(q.from_user.id,'SOL'),get_user_deposit_address(q.from_user.id,'ETH'),get_user_deposit_address(q.from_user.id,'BNB')))

async def balance(update, context):
    context.user_data.clear(); q=update.callback_query; await q.answer()
    from database import get_user_balance
    balance_lines, b, prices = await _asset_balance_lines(q.from_user.id)
    portfolio = sum(b[a] * prices.get(a, 0.0) for a in ('SOL', 'ETH', 'BNB'))
    await q.edit_message_text(
        "💳 YOUR BALANCE\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{balance_lines}\n\n"
        f"💵 TOTAL PORTFOLIO VALUE\n${portfolio:,.2f} USD\n\n"
        f"💳 TRADING BALANCE\n${get_user_balance(q.from_user.id):,.2f} USD",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="balance")],
            [InlineKeyboardButton("◀️ Back", callback_data="back")],
        ])
    )

async def profile(update, context):
    context.user_data.clear()
    q=update.callback_query; await q.answer(); u=q.from_user
    await q.edit_message_text(f"👤 PROFILE\n\n━━━━━━━━━━━━━━━━━━\n\nName: {u.full_name}\nTelegram ID: <code>{u.id}</code>\n\nYour account is ready.",parse_mode="HTML",reply_markup=back())

async def support(update, context):
    context.user_data.clear()
    q=update.callback_query; await q.answer()
    await q.edit_message_text("🆘 SUPPORT\n\n━━━━━━━━━━━━━━━━━━\n\n@verifiedcopytradingbot ;If you need assistance, contact the administrator.",reply_markup=back())

async def trading(update, context):
    context.user_data.clear()
    q=update.callback_query; await q.answer(); b=get_user_balance(q.from_user.id)
    text=f"📊 TRADING\n\n━━━━━━━━━━━━━━━━━━\n\n💳 AVAILABLE BALANCE\n${b:,.2f}\n\n"
    if b<=0:
        text += "⚠️ NO AVAILABLE BALANCE\n\nDeposit funds before opening a trade."
    else:
        text += "🧪 TRADING MODE\nYour current balance is used for trading. Blockchain transaction is submitted."
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 BUY SOL",callback_data="buy_sol")],
        [InlineKeyboardButton("🟢 BUY TOKEN",callback_data="buy_token")],
        [InlineKeyboardButton("🔴 SELL POSITION",callback_data="sell_position")],
        [InlineKeyboardButton("🔙 BACK",callback_data="back")]
    ]))

async def buy_sol(update, context):
    q=update.callback_query; await q.answer()
    context.user_data.update(trade_stage="buy_amount",trade_mint=SOL_MINT,trade_symbol="SOL")
    await q.edit_message_text("🟢 BUY SOL\n\n━━━━━━━━━━━━━━━━━━\n\nEnter the amount in USD you want to use.\n\nExample: 50\n\nMinimum: $%.2f\nMaximum: $%.2f"%(MIN_TRADE_USD,MAX_TRADE_USD),reply_markup=back())

async def buy_token(update, context):
    q=update.callback_query; await q.answer(); context.user_data["trade_stage"]="token_mint"
    await q.edit_message_text("🟢 BUY TOKEN\n\n━━━━━━━━━━━━━━━━━━\n\nSend the Solana token mint address.\n\n⚠️ Use the official mint address.",reply_markup=back())

async def sell_back(update, context):
    """Return from any sell-position screen to the Trading screen."""
    q = update.callback_query
    if not q:
        return
    await q.answer()
    context.user_data.pop("trade_mint", None)
    context.user_data.pop("trade_stage", None)
    b = get_user_balance(q.from_user.id)
    text = (
        "📊 TRADING\n\n━━━━━━━━━━━━━━━━━━\n\n"
        f"💳 AVAILABLE BALANCE\n${b:,.2f}\n\n"
    )
    if b <= 0:
        text += "⚠️ NO AVAILABLE BALANCE\n\nDeposit funds before opening a trade."
    else:
        text += (
            "🧪 TRADING MODE\n"
            "Your current balance is used for trading. "
            "Current Jupiter quotes are used for market pricing; "
            "Blockchain transaction is submitted."
        )
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 BUY SOL", callback_data="buy_sol")],
            [InlineKeyboardButton("🟢 BUY TOKEN", callback_data="buy_token")],
            [InlineKeyboardButton("🔴 SELL POSITION", callback_data="sell_position")],
            [InlineKeyboardButton("🔙 BACK", callback_data="back")],
        ]),
    )

async def sell_position(update, context):
    q=update.callback_query; await q.answer(); pos=get_positions(q.from_user.id)
    if not pos:
        await q.edit_message_text("🔴 SELL POSITION\n\n━━━━━━━━━━━━━━━━━━\n\nYou do not have any open positions yet.",reply_markup=back()); return
    rows=[[InlineKeyboardButton(f"SELL {p['mint'][:8]}…",callback_data=f"sellpick:{p['mint']}")] for p in pos[:10]]
    rows.append([InlineKeyboardButton("🔙 BACK",callback_data="back")])
    await q.edit_message_text("🔴 SELL POSITION\n\n━━━━━━━━━━━━━━━━━━\n\nChoose the position you want to close or reduce.",reply_markup=InlineKeyboardMarkup(rows))

async def sell_pick(update, context):
    q=update.callback_query; await q.answer(); mint=q.data.split(":",1)[1]
    context.user_data.update(trade_mint=mint,trade_stage="sell_percent")
    await q.edit_message_text("🔴 SELL POSITION\n\n━━━━━━━━━━━━━━━━━━\n\nHow much of this position do you want to sell?",reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("25%",callback_data="sellpct:25"),InlineKeyboardButton("50%",callback_data="sellpct:50")],
        [InlineKeyboardButton("100% — CLOSE",callback_data="sellpct:100")],
        [InlineKeyboardButton("🔙 BACK",callback_data="back")]
    ]))

async def sell_pct(update, context):
    q=update.callback_query; await q.answer(); pct=float(q.data.split(":")[1]); uid=q.from_user.id; mint=context.user_data.get("trade_mint")
    from services.trading import sell
    try:
        sig,proceeds,status=await sell(uid,mint,pct,mint[:8])
        label="🧪 ACTIVE" if status=="ACTIVE" else "🟢 CONFIRMED"
        await q.edit_message_text(f"✅ TRADE CLOSED\n\n━━━━━━━━━━━━━━━━━━\n\n🔴 SELL\n{pct:.0f}% of position\n\n💵 Proceeds\n${proceeds:,.2f}\n\n🧾 TRADE ID\n<code>{sig}</code>\n\nStatus: {label}",parse_mode="HTML",reply_markup=back())
    except Exception as e:
        await q.edit_message_text(f"❌ TRADE FAILED\n\n━━━━━━━━━━━━━━━━━━\n\n{e}",reply_markup=back())
    context.user_data.clear()

async def copy(update, context):
    context.user_data.clear()
    q=update.callback_query; await q.answer(); t=get_copy_trader(q.from_user.id)
    if t and t["active"]:
        txt=f"🔁 COPY TRADING STATUS\n\n━━━━━━━━━━━━━━━━━━\n\n🌐 CHAIN: {t.get('chain','SOL')}\n👤 TRADER\n<code>{t['wallet_address']}</code>\n\n💰 ALLOCATION\n${t['allocation']:,.2f}\n\nSTATUS: 🟢 ACTIVE\n\n🧪 COPYING USING YOUR CURRENT BALANCE"
        buttons=[[InlineKeyboardButton("🛑 STOP COPYING",callback_data="copy_stop")],[InlineKeyboardButton("🔙 BACK",callback_data="back")]]
    else:
        txt="🔁 COPY TRADING\n\n━━━━━━━━━━━━━━━━━━\n\nSelect a blockchain and enter the trader's PUBLIC wallet address.\n\n\n"
        buttons=[[InlineKeyboardButton("🚀 START COPY TRADING",callback_data="copy_start")],[InlineKeyboardButton("🔙 BACK",callback_data="back")]]
    await q.edit_message_text(txt,parse_mode="HTML",reply_markup=InlineKeyboardMarkup(buttons))

async def copy_start(update, context):
    q=update.callback_query; await q.answer(); context.user_data["copy_stage"]="chain"
    await q.edit_message_text("🔁 START COPY TRADING\n\n━━━━━━━━━━━━━━━━━━\n\nSelect the blockchain used by the trader wallet:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("◎ SOL",callback_data="copy_chain_SOL"), InlineKeyboardButton("Ξ ETH",callback_data="copy_chain_ETH"), InlineKeyboardButton("🟡 BNB",callback_data="copy_chain_BNB")],
        [InlineKeyboardButton("◀️ Back",callback_data="back")]
    ]))

async def copy_chain(update, context):
    q=update.callback_query; await q.answer(); chain=q.data.rsplit('_',1)[1]
    context.user_data.update(copy_stage="wallet", copy_chain=chain)
    await q.edit_message_text(f"🔁 COPY TRADING — {chain}\n\nSend the trader's PUBLIC wallet address.\n\n⚠️ This is the wallet you want to copy, not your imported wallet.", reply_markup=back())

async def copy_stop(update, context):
    q = update.callback_query
    if not q:
        return

    await q.answer()

    try:
        ok = stop_copy_trading(q.from_user.id)
    except Exception:
        logger.exception("Failed to stop copy trading for %s", q.from_user.id)
        ok = False

    # Clear any unfinished copy/trading input state.
    for key in (
        "copy_stage",
        "copy_wallet",
        "copy_allocation",
        "trade_stage",
        "trade_mint",
        "trade_symbol",
    ):
        context.user_data.pop(key, None)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 BACK", callback_data="back")],
        [InlineKeyboardButton("🏠 MAIN MENU", callback_data="home")],
    ])

    if ok:
        message = (
            "🛑 COPY TRADING STOPPED\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "No new copy trades will be opened.\n\n"
            "💳 Any unused reserved allocation has been returned "
            "to your available balance."
        )
    else:
        message = (
            "🛑 COPY TRADING STOPPED\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "No new copy trades will be opened.\n\n"
            "ℹ️ There was no active copy allocation to release."
        )

    await q.edit_message_text(
        message,
        reply_markup=keyboard,
    )

async def menu_router(update, context):
    if not update.message or not update.message.text:
        return

    label = update.message.text.strip()
    uid = update.effective_user.id

    # Bottom-menu buttons must always take priority over an unfinished
    # conversation (deposit amount, withdrawal amount, trade amount, copy
    # allocation, etc.). Otherwise a button label such as "💳 Wallet" can be
    # passed to the amount handler and produce "INVALID AMOUNT".
    bottom_labels = {
        "💰 Balance", "📊 Trading", "🔁 Copy Trading",
        "💳 Wallet", "👤 Profile", "🆘 Support",
    }
    if label in bottom_labels:
        context.user_data.clear()
    else:
        if context.user_data.get("copy_stage") or context.user_data.get("trade_stage") or context.user_data.get("stage"):
            return
    if label=="💰 Balance":
        b=get_user_balance(uid)
        await update.message.reply_text(f"💰 BALANCE\n\n━━━━━━━━━━━━━━━━━━\n\n💳 AVAILABLE BALANCE\n${b:,.2f}\n\n----\nThis current balance is used for trades.",reply_markup=back())
    elif label=="📊 Trading":
        b=get_user_balance(uid); text=f"📊 TRADING\n\n━━━━━━━━━━━━━━━━━━\n\n💳 AVAILABLE BALANCE\n${b:,.2f}\n\n"
        text += "⚠️ NO AVAILABLE BALANCE\n\nDeposit funds before opening a trade." if b<=0 else "🧪 TRADING MODE\nYour current balance is used for trading. Current Jupiter quotes provide market pricing; Blockchain transaction is submitted."
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🟢 BUY SOL", callback_data="buy_sol")],
                [InlineKeyboardButton("🟢 BUY TOKEN", callback_data="buy_token")],
                [InlineKeyboardButton("🔴 SELL POSITION", callback_data="sell_position")],
                [InlineKeyboardButton("🔙 BACK TO MAIN MENU", callback_data="back")],
            ]),
        )
    elif label=="🔁 Copy Trading":
        t=get_copy_trader(uid)
        if t and t["active"]:
            txt=f"🔁 COPY TRADING STATUS\n\n━━━━━━━━━━━━━━━━━━\n\n👤 TRADER\n<code>{t['wallet_address']}</code>\n\n💰 ALLOCATION\n${t['allocation']:,.2f}\n\nSTATUS: 🟢 ACTIVE\n\n🧪COPYING USING YOUR ALLOCATED BALANCE "; buttons=[[InlineKeyboardButton("🛑 STOP COPYING",callback_data="copy_stop")],
                 [InlineKeyboardButton("🔙 BACK TO MAIN MENU",callback_data="back")]]
        else:
            txt="🔁 COPY TRADING\n\n━━━━━━━━━━━━━━━━━━\n\nSelect a blockchain and enter the trader's PUBLIC wallet address.\n\n\n"
            buttons=[[InlineKeyboardButton("🚀 START COPY TRADING",callback_data="copy_start")],
                     [InlineKeyboardButton("🔙 BACK TO MAIN MENU",callback_data="back")]]
        await update.message.reply_text(txt,parse_mode="HTML",reply_markup=InlineKeyboardMarkup(buttons))
    elif label=="💳 Wallet":
        await update.message.reply_text(
            "💳 WALLET\n\n━━━━━━━━━━━━━━━━━━\n\nChoose an action.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Deposit SOL", callback_data="dep_SOL"), InlineKeyboardButton("🔷 Deposit ETH", callback_data="dep_ETH")],
                [InlineKeyboardButton("🟡 Deposit BNB", callback_data="dep_BNB"), InlineKeyboardButton("🟢 Deposit USDT", callback_data="dep_USDT")],
                [InlineKeyboardButton("📤 Withdraw", callback_data="withdraw")],
                [InlineKeyboardButton("🔙 BACK TO MAIN MENU", callback_data="back")],
            ]),
        )
    elif label=="👤 Profile":
        u=update.effective_user; await update.message.reply_text(f"👤 PROFILE\n\n━━━━━━━━━━━━━━━━━━\n\nName: {u.full_name}\nTelegram ID: <code>{u.id}</code>\n\nYour account is ready.",parse_mode="HTML",reply_markup=back())
    elif label=="🆘 Support":
        await update.message.reply_text("🆘 SUPPORT\n\n━━━━━━━━━━━━━━━━━━\n\n@verifiedcopytradingbot ;If you need assistance, contact the administrator.",reply_markup=back())

async def text_router(update, context):
    if not update.message: return
    stage=context.user_data.get("copy_stage")
    if stage:
        from services.wallet_monitor import wallet_monitor
        if stage=="chain":
            return
        if stage=="wallet":
            wallet=update.message.text.strip()
            chain=context.user_data.get('copy_chain','SOL')
            valid = wallet_monitor.validate_address(wallet) if chain=='SOL' else (wallet.startswith(('0x','0X')) and len(wallet)==42)
            if not valid:
                network = 'Solana' if chain == 'SOL' else ('Ethereum' if chain == 'ETH' else 'BNB Smart Chain')
                await update.message.reply_text(f"❌ INVALID WALLET\n\n━━━━━━━━━━━━━━━━━━\n\nPlease send a valid public {network} wallet address.")
                return
            context.user_data.update(copy_wallet=wallet,copy_stage="amount"); b=get_user_balance(update.effective_user.id)
            await update.message.reply_text(f"💰 COPY ALLOCATION\n\n━━━━━━━━━━━━━━━━━━\n\n💳 AVAILABLE BALANCE\n${b:,.2f}\n\nEnter the amount you want to reserve for copying this trader.\n\nExample: 500"); return
        if stage=="amount":
            try: amount=float(update.message.text.replace('$','').replace(',','').strip())
            except: await update.message.reply_text("❌ INVALID AMOUNT\n\nEnter a number such as 500."); return
            wallet=context.user_data.get("copy_wallet"); b=get_user_balance(update.effective_user.id)
            if amount<=0 or amount>b: await update.message.reply_text(f"❌ INVALID ALLOCATION\n\nAvailable balance: ${b:,.2f}\n Tap /deposit to deposit into your wallet and try again"); return
            # If the user already has an active copy allocation, return its
            # unused reservation before creating the replacement allocation.
            from database import get_copy_trader, release_copy_allocation, create_copy_trader
            existing = get_copy_trader(update.effective_user.id)
            if existing and existing.get("active"):
                if not release_copy_allocation(update.effective_user.id):
                    await update.message.reply_text(
                        "❌ ALLOCATION FAILED\n\n━━━━━━━━━━━━━━━━━━\n\n"
                        "Your existing copy allocation could not be released safely. "
                        "No changes were made."
                    )
                    return
                b = get_user_balance(update.effective_user.id)

            if amount <= 0 or amount > b:
                await update.message.reply_text(
                    f"❌ INVALID ALLOCATION\n\nAvailable balance: ${b:,.2f} \nTap /deposit to deposit and try again"
                )
                return

            if not reserve_copy_allocation(update.effective_user.id,amount):
                await update.message.reply_text(
                    "❌ ALLOCATION FAILED\n\n━━━━━━━━━━━━━━━━━━\n\n"
                    "Your available balance changed. Please try again."
                )
                return

            chain=context.user_data.get('copy_chain','SOL')
            create_copy_trader(update.effective_user.id,wallet,amount,chain)
            context.user_data.clear()
            await update.message.reply_text(f"✅ COPY TRADING STARTED\n\n━━━━━━━━━━━━━━━━━━\n\n🌐 Chain: {chain}\n👤 Trader\n<code>{wallet}</code>\n\n💰 Copy Allocation\n${amount:,.2f}\n\n🟢 Status: ACTIVE\n\nThe bot will monitor confirmed swaps and apply supported copies against your balance.",parse_mode="HTML",reply_markup=back()); return
    stage=context.user_data.get("trade_stage")
    if stage=="token_mint":
        from services.wallet_monitor import wallet_monitor
        mint=update.message.text.strip()
        if not wallet_monitor.validate_address(mint): await update.message.reply_text("❌ INVALID TOKEN MINT\n\n━━━━━━━━━━━━━━━━━━\n\nPlease send a valid Solana token mint address."); return
        context.user_data.update(trade_stage="buy_amount",trade_mint=mint,trade_symbol=mint[:8]); await update.message.reply_text("💵 BUY AMOUNT\n\n━━━━━━━━━━━━━━━━━━\n\nEnter how much USD you want to spend."); return
    if stage=="buy_amount":
        try: amount=float(update.message.text.replace('$','').replace(',','').strip())
        except: await update.message.reply_text("❌ INVALID AMOUNT\n\nEnter a number such as 50."); return
        from services.trading import buy
        if amount>get_user_balance(update.effective_user.id): await update.message.reply_text(f"❌ INSUFFICIENT BALANCE\n\nAvailable: ${get_user_balance(update.effective_user.id):,.2f}"); return
        mint=context.user_data.get("trade_mint"); symbol=context.user_data.get("trade_symbol","TOKEN")
        await update.message.reply_text("🟡 TRADE PROCESSING\n\n━━━━━━━━━━━━━━━━━━\n\nGetting a current Jupiter market quote…")
        try:
            sig,out,status=await buy(update.effective_user.id,mint,amount,symbol)
            label="ACTIVE" if status=="ACTIVE" else "🟢 CONFIRMED"
            await update.message.reply_text(f"✅ TRADE OPENED\n\n━━━━━━━━━━━━━━━━━━\n\n🟢 BUY\n{symbol}\n\n💵 Amount\n${amount:,.2f}\n\n🪙 Quantity (base units)\n{out:,}\n\n🧾 TRADE ID\n<code>{sig}</code>\n\nStatus: {label}",parse_mode="HTML",reply_markup=back())
        except Exception as e:
            await update.message.reply_text(f"❌ TRADE FAILED\n\n━━━━━━━━━━━━━━━━━━\n\n{e}",reply_markup=back())
        context.user_data.clear()
