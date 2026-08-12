from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_user_balance, create_deposit, create_withdrawal
from config import DEPOSIT_SOL_ADDRESS, DEPOSIT_BSC_ADDRESS, DEPOSIT_ETH_ADDRESS
from services.pricing import get_usd_price

DEPOSIT_CONFIG = {
    "SOL": {"network": "Solana", "address": DEPOSIT_SOL_ADDRESS},
    "ETH": {"network": "Ethereum", "address": DEPOSIT_ETH_ADDRESS},
    "BNB": {"network": "BNB Smart Chain (BSC)", "address": DEPOSIT_BSC_ADDRESS},
    "USDT": {"network": "BNB Smart Chain (BEP-20)", "address": DEPOSIT_BSC_ADDRESS},
}

def wallet_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Deposit SOL", callback_data="dep_SOL"),
         InlineKeyboardButton("🔷 Deposit ETH", callback_data="dep_ETH")],
        [InlineKeyboardButton("🟡 Deposit BNB", callback_data="dep_BNB"),
         InlineKeyboardButton("🟢 Deposit USDT", callback_data="dep_USDT")],
        [InlineKeyboardButton("📤 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("🔙 BACK", callback_data="back")],
    ])

async def wallet(update, context):
    context.user_data.clear()
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "💳 WALLET\n\n━━━━━━━━━━━━━━━━━━\n\n"
        "Your balance is your available trading balance.\n\n"
        "Choose a deposit or withdrawal option.",
        reply_markup=wallet_keyboard(),
    )

async def deposit(update, context):
    context.user_data.clear()
    q = update.callback_query
    await q.answer()
    asset = q.data.split("_", 1)[1]
    from services.deposit_addresses import get_user_deposit_address
    address = get_user_deposit_address(q.from_user.id, asset)
    cfg = DEPOSIT_CONFIG.get(asset)
    if not cfg:
        await q.edit_message_text("❌ Unsupported deposit asset.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data="back")]]))
        return
    if not address:
        await q.edit_message_text(
            f"⚠️ {asset} DEPOSIT NOT READY\n\n"
            "No unique receiving address has been assigned to your account yet.\n\n"
            "                   NOT READY                    ",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK",callback_data="back")]]))
        return
    warning = {
        "SOL":"⚠️ Send only SOL on the Solana network.",
        "ETH":"⚠️ Send only ETH on the Ethereum network.",
        "BNB":"⚠️ Send only native BNB on BNB Smart Chain (BSC).",
    }.get(asset, "")
    await q.edit_message_text(
        f"💰 DEPOSIT {asset}\n\n━━━━━━━━━━━━━━━━━━\n\n"
        f"🌐 Network: {cfg['network']}\n\n"
        f"Send {asset} to your personal deposit address:\n\n<code>{address}</code>\n\n"
        "👆 Tap the address above to copy it.\n\n"
        f"{warning}\n\n"
        "🔄 Automatic deposit detection: ACTIVE\n"
        "No TXID submission is required. The blockchain monitor will detect the transaction and verify confirmations.\n\n"
        "💳 Your internal trading balance is credited only after administrator approval.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK",callback_data="back")]]))

async def withdraw(update, context):
    context.user_data.clear()
    q=update.callback_query
    await q.answer()
    b=get_user_balance(q.from_user.id)
    context.user_data["stage"]="with_asset"
    await q.edit_message_text(
        f"📤 WITHDRAWAL\n\n━━━━━━━━━━━━━━━━━━\n\n"
        f"💳 AVAILABLE BALANCE\n${b:,.2f}\n\n"
        "Choose the asset you want to withdraw to:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟣 SOL",callback_data="withasset_SOL"),
             InlineKeyboardButton("🔷 ETH",callback_data="withasset_ETH")],
            [InlineKeyboardButton("🟡 BNB",callback_data="withasset_BNB")],
            [InlineKeyboardButton("🔙 BACK",callback_data="back")],
        ]))

async def wallet_text(update, context):
    stage=context.user_data.get("stage")
    # Deposits are detected automatically on-chain. The bot intentionally does
    # not ask the user to type an amount or transaction hash.
    if stage=="with_asset":
        # Button callbacks are handled by the generic callback router in bot.py.
        asset=update.message.text.strip().upper()
        if asset not in ("SOL","ETH","BNB"):
            await update.message.reply_text("❌ Choose SOL, ETH or BNB using the buttons.")
            return
        await _set_with_asset(update,context,asset)
        return

    if stage=="with_amount":
        try: amount=float(update.message.text.replace(",","").replace("$","").strip())
        except ValueError:
            await update.message.reply_text("❌ Enter a valid amount."); return
        b=get_user_balance(update.effective_user.id)
        if amount<=0 or amount>b:
            await update.message.reply_text(f"❌ Insufficient available balance.\n\nAvailable: ${b:,.2f}"); return
        context.user_data["withdraw_amount"]=amount
        context.user_data["stage"]="with_address"
        asset=context.user_data["withdraw_asset"]
        await update.message.reply_text(
            f"📍 {asset} WITHDRAWAL ADDRESS\n\n━━━━━━━━━━━━━━━━━━\n\n"
            "Enter the destination address. Make sure it matches the selected network.")
        return

    if stage=="with_address":
        address=update.message.text.strip()
        asset=context.user_data["withdraw_asset"]
        if asset=="SOL":
            from services.wallet_monitor import wallet_monitor
            if not wallet_monitor.validate_address(address):
                await update.message.reply_text("❌ Invalid Solana address."); return
        else:
            if not (address.startswith("0x") and len(address)==42):
                await update.message.reply_text("❌ Invalid EVM address. It must be a 42-character 0x address."); return
        amount=context.user_data["withdraw_amount"]
        wid=create_withdrawal(update.effective_user.id,asset,amount,address)
        context.user_data.clear()
        from bot import notify_admin_withdrawal
        await notify_admin_withdrawal(update.get_bot(),wid,update.effective_user,asset,amount,address)
        await update.message.reply_text(
            f"⏳ WITHDRAWAL PENDING\n\n━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 Request: #{wid}\n💵 Amount: ${amount:,.2f}\n🪙 Asset: {asset}\n"
            "\nStatus: 🟡 Awaiting administrator approval.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")]]))
        return

async def _set_with_asset(update,context,asset):
    context.user_data["withdraw_asset"]=asset
    context.user_data["stage"]="with_amount"
    await update.message.reply_text(
        f"📤 WITHDRAW {asset}\n\n━━━━━━━━━━━━━━━━━━\n\n"
        f"💳 AVAILABLE BALANCE: ${get_user_balance(update.effective_user.id):,.2f}\n\n"
        "Enter the USD amount you want to withdraw.")
