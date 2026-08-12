from telegram import InlineKeyboardButton, InlineKeyboardMarkup
try:
    from telegram import CopyTextButton
except ImportError:
    CopyTextButton = None


def main_menu(sol_address="", eth_address="", bnb_address=""):
    # Telegram's CopyTextButton is used for the three quick-address buttons
    # when available. They intentionally do not navigate to another screen.
    def copy_btn(label, address, fallback):
        if CopyTextButton and address:
            return InlineKeyboardButton(label, copy_text=CopyTextButton(text=address))
        return InlineKeyboardButton(label, callback_data=fallback)

    return InlineKeyboardMarkup([
        [copy_btn("◎ SOL", sol_address, "quick_SOL"),
         copy_btn("Ξ ETH", eth_address, "quick_ETH"),
         copy_btn("🟡 BNB", bnb_address, "quick_BNB")],
        [InlineKeyboardButton("💰 Deposit", callback_data="deposit"), InlineKeyboardButton("💳 Balance", callback_data="balance")],
        [InlineKeyboardButton("📈 Copy Trading", callback_data="copy"), InlineKeyboardButton("🤖 Auto Trading", callback_data="auto")],
        [InlineKeyboardButton("🛒 Buy", callback_data="trading"), InlineKeyboardButton("💵 Sell", callback_data="sell_position")],
        [InlineKeyboardButton("🔄 Transfer", callback_data="transfer"), InlineKeyboardButton("📤 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("👛 Wallet", callback_data="wallet"), InlineKeyboardButton("📥 Import Wallet", callback_data="import_wallet")],
        [InlineKeyboardButton("📊 Portfolio", callback_data="portfolio"), InlineKeyboardButton("📜 Trade History", callback_data="history")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"), InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("🆘 Support", callback_data="support"), InlineKeyboardButton("🔄 Refresh", callback_data="home")],
    ])


def back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="home")]])
