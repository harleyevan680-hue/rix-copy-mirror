import asyncio,logging
from telegram import Update,InlineKeyboardButton,InlineKeyboardMarkup,BotCommand
from telegram.ext import Application,CommandHandler,CallbackQueryHandler,MessageHandler,ContextTypes,TypeHandler,ApplicationHandlerStop,filters
from config import BOT_TOKEN,LOG_LEVEL,validate_config,COPY_SCAN_INTERVAL,DEPOSIT_SCAN_INTERVAL,AUTO_SCAN_INTERVAL,ADMIN_IDS
from database import init_database,is_user_banned
from handlers.user import start,home,balance,profile,support,trading,copy,copy_start,copy_chain,copy_stop,sell_back,text_router,menu_router,buy_sol,buy_token,sell_position,sell_pick,sell_pct
from handlers.wallet import wallet,deposit,withdraw,wallet_text,_set_with_asset
from handlers.import_wallet import import_wallet,import_network,import_method_public,import_list,import_delete,import_text,import_any
from handlers.commands import wallet_cmd,deposit_cmd,copytrade_cmd,withdraw_cmd,import_cmd,guide_cmd,help_cmd
from handlers.settings import settings,auto_menu,auto_enable,auto_disable,auto_config,auto_chain,auto_text
from handlers.admin import panel,admin_command,deposits,withdrawals,action,stats,is_admin,users,user_profile,user_action,broadcast,admin_text
from services.copy_engine import scan_once
from services.wallet_monitor import wallet_monitor

logging.basicConfig(level=getattr(logging,LOG_LEVEL,logging.INFO),format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger=logging.getLogger("crypto_copy_bot")


async def access_guard(update, context):
    user = update.effective_user
    if not user or is_admin(user.id):
        return
    if is_user_banned(user.id):
        if update.callback_query:
            await update.callback_query.answer("🚫 Your account is banned.", show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text("🚫 Your account has been banned. Please contact the administrator.")
        raise ApplicationHandlerStop


# Callback actions that perform an operation rather than opening a new screen.
# They must not become Back-navigation destinations.
NAV_ACTION_PATTERNS = (
    r"^quick_(SOL|ETH|BNB)$",
    r"^balance$",  # Refreshing balance should not create another history entry.
    r"^auto_enable$", r"^auto_disable$", r"^copy_stop$",
    r"^sellpct:(25|50|100)$",
    r"^(approve_dep|reject_dep|approve_w|reject_w):\d+$",
    r"^import_delete:\d+$",
    r"^admin_(ban|unban)$",
)

def _is_nav_action(data):
    import re
    return any(re.match(pattern, data) for pattern in NAV_ACTION_PATTERNS)

async def navigation_tracker(update, context):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if data == "back" or _is_nav_action(data):
        return

    stack = context.chat_data.setdefault("nav_stack", [])

    # Home is a navigation root. When explicitly selected, discard stale
    # history so Back never jumps into an older conversation branch.
    if data == "home":
        context.chat_data["nav_stack"] = ["home"]
        return

    if not stack:
        stack.append("home")

    if stack[-1] != data:
        stack.append(data)

    # Keep navigation history bounded.
    if len(stack) > 30:
        del stack[:-30]


async def back_handler(update, context):
    q = update.callback_query
    if not q:
        return
    # Do not answer the callback here. The destination handler answers it;
    # answering twice can make Telegram reject the callback query.
    stack = context.chat_data.setdefault("nav_stack", [])
    # Remove the current screen.
    if stack:
        stack.pop()
    target = stack[-1] if stack else "home"
    if target == "back":
        target = "home"
    # Find the registered callback handler for the previous screen.
    for pattern, handler in CALLBACK_ROUTES.items():
        if __import__("re").match(pattern, target):
            original = q.data
            q.data = target
            try:
                await handler(update, context)
            finally:
                q.data = original
            return
    # Unknown/expired navigation target: safely return home.
    stack.clear()
    original = q.data
    q.data = "home"
    try:
        await home(update, context)
    finally:
        q.data = original


CALLBACK_ROUTES = {}

async def notify_admin_deposit(bot,did,user,asset,amount,txid,usd_value=0.0,network="SOLANA"):
    for aid in ADMIN_IDS:
        await bot.send_message(aid,f"🔔 NEW DEPOSIT REQUEST\n\n━━━━━━━━━━━━━━━━━━\n\n👤 USER\n{user.full_name}\nID: <code>{user.id}</code>\n\n💰 DEPOSIT\nAsset: {asset}\nAmount: {amount:,.8f} {asset}\nUSD Value: ${usd_value:,.2f}\nNetwork: {network}\n\n🆔 DEPOSIT ID\n#{did}\n\n🔗 TRANSACTION\n<code>{txid}</code>",parse_mode="HTML",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛡️ REVIEW",callback_data="admin_deposits")]]))

async def notify_admin_withdrawal(bot,wid,user,asset,amount,address):
    for aid in ADMIN_IDS:
        await bot.send_message(aid,f"🔔 NEW WITHDRAWAL REQUEST\n\n━━━━━━━━━━━━━━━━━━\n\n👤 USER\n{user.full_name}\nID: <code>{user.id}</code>\n\n💵 Amount: {amount:,.2f} {asset}\n\n📍 ADDRESS\n<code>{address}</code>\n\n🆔 REQUEST #{wid}",parse_mode="HTML",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛡️ REVIEW",callback_data="admin_withdrawals")]]))

async def deposit_menu(update, context):
    q = update.callback_query
    if not q:
        return
    await q.answer()
    from handlers.wallet import wallet_keyboard
    await q.edit_message_text(
        "💰 DEPOSIT\n\n━━━━━━━━━━━━━━━━━━\n\nSelect the asset you want to deposit.",
        reply_markup=wallet_keyboard(),
    )

async def transfer_menu(update, context):
    q=update.callback_query
    if not q:
        return
    await q.answer()
    await q.edit_message_text(
        "🔄 TRANSFER\n\n━━━━━━━━━━━━━━━━━━\n\nSelect the source asset.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◎ SOL",callback_data="transfer_from_SOL"),InlineKeyboardButton("Ξ ETH",callback_data="transfer_from_ETH"),InlineKeyboardButton("🟡 BNB",callback_data="transfer_from_BNB")],
            [InlineKeyboardButton("◀️ Back",callback_data="back")]
        ])
    )

async def transfer_from(update, context):
    q=update.callback_query
    await q.answer()
    asset=q.data.rsplit('_',1)[1]
    context.user_data["transfer_from"]=asset
    await q.edit_message_text(
        f"🔄 TRANSFER — FROM {asset}\n\nSelect the destination asset.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◎ SOL",callback_data="transfer_to_SOL"),InlineKeyboardButton("Ξ ETH",callback_data="transfer_to_ETH"),InlineKeyboardButton("🟡 BNB",callback_data="transfer_to_BNB")],
            [InlineKeyboardButton("◀️ Back",callback_data="back")]
        ])
    )

async def transfer_to(update, context):
    q=update.callback_query
    await q.answer()
    to=q.data.rsplit('_',1)[1]
    src=context.user_data.get("transfer_from")
    if not src or src==to:
        await q.edit_message_text("❌ Choose a different destination asset.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back",callback_data="back")]]))
        return
    context.user_data["transfer_to"]=to
    context.user_data["transfer_stage"]="amount"
    await q.edit_message_text(f"🔄 TRANSFER {src} → {to}\n\nEnter the USD value you want to transfer.\n\n⚠️ This is an internal portfolio conversion; blockchain withdrawals are handled separately.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel",callback_data="back")]]))

async def transfer_text(update, context):
    if context.user_data.get("transfer_stage")!="amount":
        return False
    try:
        amount=float(update.message.text.replace(',','').strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a valid amount.")
        return True
    if amount<=0:
        await update.message.reply_text("❌ Amount must be greater than zero.")
        return True
    src=context.user_data["transfer_from"]; dst=context.user_data["transfer_to"]
    from database import get_asset_balance, change_asset_balance
    from services.pricing import get_usd_price
    available=get_asset_balance(update.effective_user.id,src)
    if amount>available:
        await update.message.reply_text(f"❌ Insufficient {src} balance.\n\nAvailable: {available:.8f} {src}")
        return True
    try:
        src_price=await get_usd_price(src); dst_price=await get_usd_price(dst)
    except Exception:
        await update.message.reply_text("⚠️ Live pricing is temporarily unavailable. Please try again.")
        return True
    usd_value=amount*src_price
    dst_amount=usd_value/dst_price if dst_price>0 else 0
    if dst_amount<=0:
        await update.message.reply_text("❌ Conversion quote unavailable.")
        return True
    if not change_asset_balance(update.effective_user.id,src,-amount):
        await update.message.reply_text("❌ Your balance changed. Please try again.")
        return True
    change_asset_balance(update.effective_user.id,dst,dst_amount)
    context.user_data.clear()
    await update.message.reply_text(f"✅ TRANSFER COMPLETED\n\n{src} → {dst}\n\nSent: {amount:.8f} {src}\nReceived: {dst_amount:.8f} {dst}\nValue: ${usd_value:,.2f}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")]]))
    return True

async def portfolio(update, context):
    q=update.callback_query; await q.answer()
    from database import get_asset_balances, get_positions
    from services.pricing import get_usd_price
    b=get_asset_balances(q.from_user.id); positions=get_positions(q.from_user.id)
    prices={}
    for asset in ('SOL','ETH','BNB'):
        try:
            prices[asset] = await get_usd_price(asset)
        except Exception:
            prices[asset] = 0.0
    labels={'SOL':'◎ SOL','ETH':'Ξ ETH','BNB':'🟡 BNB'}
    balance_lines=[]
    for asset in ('SOL','ETH','BNB'):
        amount=float(b.get(asset,0.0)); usd=amount*prices.get(asset,0.0)
        balance_lines.append(f"{labels[asset]}\n   {amount:,.6f} {asset}\n   ${usd:,.2f} USD")
    total=sum(float(b.get(asset,0.0))*prices.get(asset,0.0) for asset in ('SOL','ETH','BNB'))
    await q.edit_message_text(
        "📊 PORTFOLIO\n\n━━━━━━━━━━━━━━━━━━\n\n"
        "💰 ASSET BALANCES\n\n"
        + "\n\n".join(balance_lines)
        + f"\n\n💵 TOTAL PORTFOLIO VALUE\n${total:,.2f} USD\n\n📂 Open Positions: {len(positions)}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh",callback_data="portfolio")],[InlineKeyboardButton("◀️ Back",callback_data="back")]])
    )

async def history(update, context):
    q=update.callback_query; await q.answer()
    from database import get_trade_history
    rows=get_trade_history(q.from_user.id,10)
    if not rows:
        text="📜 TRADE HISTORY\n\nNo trades recorded yet."
    else:
        text="📜 TRADE HISTORY\n\n"+"\n\n".join([f"{r['side']} {r['symbol'] or 'ASSET'} — ${float(r['amount_usd']):,.2f}\nStatus: {r['status']}" for r in rows])
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back",callback_data="back")]]))

async def withdraw_asset(update, context):
    q = update.callback_query
    await q.answer()
    asset = q.data.split("_", 1)[1]
    context.user_data["stage"] = "with_amount"
    context.user_data["withdraw_asset"] = asset
    from database import get_user_balance
    await q.edit_message_text(
        f"📤 WITHDRAW {asset}\n\n━━━━━━━━━━━━━━━━━━\n\n"
        f"💳 AVAILABLE BALANCE: ${get_user_balance(q.from_user.id):,.2f}\n\n"
        "Enter the USD amount you want to withdraw.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 BACK", callback_data="back")]
        ]),
    )

async def quick_address(update, context):
    q=update.callback_query; await q.answer()
    from services.deposit_addresses import get_user_deposit_address
    asset=q.data.split('_',1)[1]; address=get_user_deposit_address(q.from_user.id,asset)
    if address and not getattr(q, 'data', '').startswith('quick_'): return
    if address: await q.message.reply_text(f"{asset} address: <code>{address}</code>",parse_mode="HTML")

async def copy_job(context):
    try:
        events = await scan_once()
        try:
            from services.evm_copy import scan_evm
            evm_events = await scan_evm()
            for r in evm_events:
                events.append(({"telegram_id": r["telegram_id"]}, r))
        except Exception:
            logger.exception("EVM copy scan failed")
        for user, result in events:
            if result.get("status") != "COPIED":
                continue

            active = result.get("mode") == "ACTIVE"
            status_text = "🧪 ACTIVE" if active else "🟢 CONFIRMED"
            amount = float(result.get("amount_usd") or 0)

            # Never report a zero-value copy as opened.
            if result.get("side") == "BUY" and amount <= 0:
                logger.warning(
                    "Skipping zero-value copy notification for user %s",
                    user.get("telegram_id"),
                )
                continue

            if result.get("side") == "SELL":
                pnl = float(result.get("realized_pnl") or 0)
                pnl_icon = "🟢" if pnl >= 0 else "🔴"
                body = (
                    "🔴 COPY TRADE CLOSED\n\n"
                    "━━━━━━━━━━━━━━━━━━\n\n"
                    f"🪙 Token: <code>{result['mint']}</code>\n"
                    f"💵 Proceeds: ${amount:,.2f}\n"
                    f"{pnl_icon} Realized P/L: ${pnl:,.2f}\n\n"
                    "🔗 SOURCE TRANSACTION\n"
                    f"<code>{result['signature']}</code>\n\n"
                    "🔗 COPY TRANSACTION\n"
                    f"<code>{result['tx_hash']}</code>\n\n"
                    f"Status: {status_text}"
                )
            else:
                body = (
                    "🟢 COPY TRADE OPENED\n\n"
                    "━━━━━━━━━━━━━━━━━━\n\n"
                    f"🪙 Token: <code>{result['mint']}</code>\n"
                    f"💵 Copy Amount: ${amount:,.2f}\n\n"
                    "🔗 SOURCE TRANSACTION\n"
                    f"<code>{result['signature']}</code>\n\n"
                    "🔗 COPY TRANSACTION\n"
                    f"<code>{result['tx_hash']}</code>\n\n"
                    f"Status: {status_text}"
                )

            await context.bot.send_message(
                user["telegram_id"],
                body,
                parse_mode="HTML",
            )
    except Exception:
        logger.exception("copy scan failed")

async def post_init(app):
    init_database()
    await app.bot.set_my_commands([
        BotCommand("start", "Open dashboard"),
        BotCommand("wallet", "View balances and wallet addresses"),
        BotCommand("deposit", "Show deposit options"),
        BotCommand("copytrade", "Manage wallets you want to copy"),
        BotCommand("withdraw", "Submit a withdrawal request"),
        BotCommand("import", "Import wallet"),
        BotCommand("settings", "Configure trading preferences"),
        BotCommand("guide", "Full feature guide"),
        BotCommand("help", "Quick command reference"),
        BotCommand("admin", "Admin panel (administrators only)"),
    ])
    app.job_queue.run_repeating(copy_job,interval=COPY_SCAN_INTERVAL,first=5,name="copy_scan")
    from services.auto_trader import scan_autotrade
    app.job_queue.run_repeating(lambda c: scan_autotrade(c.bot),interval=AUTO_SCAN_INTERVAL,first=15,name="autotrade_scan")
    from services.deposit_monitor import scan_deposits
    app.job_queue.run_repeating(lambda c: scan_deposits(c.bot),interval=DEPOSIT_SCAN_INTERVAL,first=10,name="deposit_scan")
    logger.info("Bot initialized")

async def post_shutdown(app):
    await wallet_monitor.close()
    from services.jupiter import jupiter
    await jupiter.close()
    from services.evm import evm
    await evm.close()

async def error_handler(update, context):
    logger.exception("Unhandled update error", exc_info=context.error)

def build():
    validate_config()
    a=Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    a.add_handler(CommandHandler("start",start))
    a.add_handler(CommandHandler("wallet",wallet_cmd))
    a.add_handler(CommandHandler("deposit",deposit_cmd))
    a.add_handler(CommandHandler("copytrade",copytrade_cmd))
    a.add_handler(CommandHandler("withdraw",withdraw_cmd))
    a.add_handler(CommandHandler("import",import_cmd))
    a.add_handler(CommandHandler("guide",guide_cmd))
    a.add_handler(CommandHandler("settings",settings))
    a.add_handler(CommandHandler("help",help_cmd))
    a.add_handler(CommandHandler("admin",admin_command))
    a.add_error_handler(error_handler)
    patterns={
        r"^home$":home,r"^deposit$":deposit_menu,r"^balance$":balance,r"^profile$":profile,r"^support$":support,r"^settings$":settings,r"^auto$":auto_menu,r"^auto_enable$":auto_enable,r"^auto_disable$":auto_disable,r"^auto_config$":auto_config,r"^auto_chain_(SOL|ETH|BNB)$":auto_chain,r"^quick_(SOL|ETH|BNB)$":quick_address,
        r"^trading$":trading,r"^buy_sol$":buy_sol,r"^buy_token$":buy_token,r"^sell_position$":sell_position,r"^sell_back$":sell_back,r"^sellpick:.+$":sell_pick,r"^sellpct:(25|50|100)$":sell_pct,r"^copy$":copy,r"^copy_start$":copy_start,r"^copy_chain_(SOL|ETH|BNB)$":copy_chain,r"^copy_stop$":copy_stop,
        r"^wallet$":wallet,r"^dep_(SOL|ETH|BNB|USDT)$":deposit,r"^withdraw$":withdraw,r"^withasset_(SOL|ETH|BNB)$":withdraw_asset,r"^transfer$":transfer_menu,r"^transfer_from_(SOL|ETH|BNB)$":transfer_from,r"^transfer_to_(SOL|ETH|BNB)$":transfer_to,r"^portfolio$":portfolio,r"^history$":history,
        r"^import_wallet$":import_wallet,r"^import_(SOL|ETH|BNB)$":import_network,r"^import_method_public$":import_method_public,r"^import_list$":import_list,r"^import_delete:\d+$":import_delete,
        r"^admin$":panel,r"^admin_deposits$":deposits,r"^admin_withdrawals$":withdrawals,r"^admin_stats$":stats,
        r"^admin_users$":users,r"^admin_broadcast$":broadcast,r"^admin_user_view$":lambda u,c: user_profile(u,c),
        r"^admin_(ban|unban)$":user_action,
        r"^(approve_dep|reject_dep|approve_w|reject_w):\d+$":action
    }
    CALLBACK_ROUTES.clear()
    CALLBACK_ROUTES.update(patterns)
    a.add_handler(TypeHandler(Update, access_guard), group=-100)
    a.add_handler(CallbackQueryHandler(navigation_tracker, pattern=r"^(?!back$).+"), group=-90)
    a.add_handler(CallbackQueryHandler(back_handler, pattern=r"^back$"), group=-80)
    for p,h in patterns.items(): a.add_handler(CallbackQueryHandler(h,pattern=p))
    a.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND,import_any),group=-2)
    a.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND,admin_text),group=-3)
    a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,menu_router),group=-1)
    a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,transfer_text),group=0)
    a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,auto_text),group=1)
    a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,import_text),group=2)
    a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,wallet_text),group=3)
    a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_router),group=4)
    return a

def main():
    init_database()
    logger.info("Starting crypto copy-trading bot.")
    app=build()
    app.run_polling(allowed_updates=Update.ALL_TYPES,drop_pending_updates=True)

if __name__=="__main__": main()
