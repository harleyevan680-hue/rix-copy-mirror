from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from handlers.wallet import wallet_keyboard
from handlers.import_wallet import import_keyboard

async def wallet_cmd(update, context):
    await update.message.reply_text(
        "💳 WALLET\n\n━━━━━━━━━━━━━━━━━━\n\nChoose an action.",
        reply_markup=wallet_keyboard(),
    )

async def deposit_cmd(update, context):
    await update.message.reply_text(
        "💰 DEPOSIT\n\n━━━━━━━━━━━━━━━━━━\n\nChoose the asset you want to deposit.",
        reply_markup=wallet_keyboard(),
    )

async def copytrade_cmd(update, context):
    from handlers.user import copy
    # command equivalent of the copy-trading button
    await update.message.reply_text(
        "🔁 COPY TRADING\n\n━━━━━━━━━━━━━━━━━━\n\n"
        "Monitor a public Solana trader and copy supported swaps using your balance.\n\n"
        "⚠️ Send only a public wallet address. Never send private keys or seed phrases.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 START COPY TRADING", callback_data="copy_start")],
            [InlineKeyboardButton("🏠 MAIN MENU", callback_data="home")],
        ]),
    )

async def withdraw_cmd(update, context):
    await update.message.reply_text(
        "📤 WITHDRAWAL\n\n━━━━━━━━━━━━━━━━━━\n\nChoose the asset and follow the steps.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟣 SOL", callback_data="withasset_SOL"),
             InlineKeyboardButton("🔷 ETH", callback_data="withasset_ETH")],
            [InlineKeyboardButton("🟡 BNB", callback_data="withasset_BNB")],
            [InlineKeyboardButton("🏠 MAIN MENU", callback_data="home")],
        ]),
    )

async def import_cmd(update, context):
    context.user_data.clear()
    context.user_data["import_stage"] = "network"
    await update.message.reply_text(
        "📥 IMPORT WALLET\n\n━━━━━━━━━━━━━━━━━━\n\n"
        "Import an existing wallet using either your private key or recovery phrase.\n\n"
        "🔐 SECURITY\n"
        "Credentials are deleted immediately after successfull wallet connection.\n\n"
        "Choose the network:",
        reply_markup=import_keyboard(),
    )

async def guide_cmd(update, context):
    await update.message.reply_text(
        "📚 RIX BOT GUIDE\n\n━━━━━━━━━━━━━━━━━━\n\n"
        "💳 Wallet — deposits, withdrawals and imported public wallets\n"
        "📈 Copytrade — monitor a public Solana trader\n"
        "🤖 Autotrade — automated strategy using balance\n"
        "📊 Portfolio — view balances and positions\n"
        "🔄 Transfer — move value between supported internal assets\n\n"
        "🔐 Security: your credentials are automatically deleted from the database.",
    )

async def help_cmd(update, context):
    await update.message.reply_text(
        "🆘 QUICK COMMANDS\n\n"
        "/start — Open dashboard\n"
        "/wallet — Wallet\n"
        "/deposit — Deposit\n"
        "/copytrade — Copy trading\n"
        "/withdraw — Withdrawal\n"
        "/import — Import wallet\n"
        "/guide — Full guide\n"
        "/help — This command list"
    )
