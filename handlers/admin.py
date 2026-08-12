from telegram import InlineKeyboardButton,InlineKeyboardMarkup
from config import ADMIN_IDS
from database import get_pending_deposits,get_pending_withdrawals,approve_deposit,reject_deposit,approve_withdrawal,reject_withdrawal,get_stats

def is_admin(uid): return uid in ADMIN_IDS

async def panel(update,context):
    context.user_data.clear()
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): await q.edit_message_text("❌ ACCESS DENIED"); return
    await q.edit_message_text(
        "🛡️ ADMIN PANEL\n\n━━━━━━━━━━━━━━━━━━\n\nManage deposits, withdrawals and platform activity.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Pending Deposits",callback_data="admin_deposits")],
            [InlineKeyboardButton("📤 Pending Withdrawals",callback_data="admin_withdrawals")],
            [InlineKeyboardButton("📊 Statistics",callback_data="admin_stats")],
            [InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")],
        ]),
    )

async def deposits(update,context):
    context.user_data.clear()
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    rows=get_pending_deposits()
    if not rows: await q.edit_message_text("💰 PENDING DEPOSITS\n\n━━━━━━━━━━━━━━━━━━\n\nNo pending deposits.",reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK",callback_data="admin")],
                [InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")],
            ])); return
    r=rows[0]
    await q.edit_message_text(f"🔔 NEW DEPOSIT REQUEST\n\n━━━━━━━━━━━━━━━━━━\n\n👤 USER\n<code>{r['telegram_id']}</code>\n\n💰 DEPOSIT\nAsset: {r['asset']}\nAmount: {float(r['amount']):,.8f} {r['asset']}\nUSD Value: ${float(r['usd_value'] or 0):,.2f}\nNetwork: {r['network']}\n\n🆔 DEPOSIT ID\n#{r['id']}\n\n🔗 TRANSACTION\n<code>{r['txid']}</code>\n\n━━━━━━━━━━━━━━━━━━\n⚠️ Review the transaction before approving.",parse_mode="HTML",reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ APPROVE",callback_data=f"approve_dep:{r['id']}"),InlineKeyboardButton("❌ REJECT",callback_data=f"reject_dep:{r['id']}")],
        [InlineKeyboardButton("🔙 BACK",callback_data="admin")],
        [InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")]]))

async def withdrawals(update,context):
    context.user_data.clear()
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    rows=get_pending_withdrawals()
    if not rows: await q.edit_message_text("📤 PENDING WITHDRAWALS\n\n━━━━━━━━━━━━━━━━━━\n\nNo pending withdrawals.",reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK",callback_data="admin")],
                [InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")],
            ])); return
    r=rows[0]
    await q.edit_message_text(f"🔔 WITHDRAWAL REQUEST\n\n━━━━━━━━━━━━━━━━━━\n\n👤 USER\n<code>{r['telegram_id']}</code>\n\n💵 Amount: {r['amount']} {r['asset']}\n\n📍 ADDRESS\n<code>{r['address']}</code>\n\n🆔 REQUEST #{r['id']}",parse_mode="HTML",reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ APPROVE",callback_data=f"approve_w:{r['id']}"),InlineKeyboardButton("❌ REJECT",callback_data=f"reject_w:{r['id']}")],
        [InlineKeyboardButton("🔙 BACK",callback_data="admin")],
        [InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")]]))

async def action(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    typ,id_=q.data.split(":"); id_=int(id_)
    if typ=="approve_dep": row=approve_deposit(id_)
    elif typ=="reject_dep": row=reject_deposit(id_)
    elif typ=="approve_w": row=approve_withdrawal(id_)
    else: row=reject_withdrawal(id_)
    if row=="INSUFFICIENT": msg="❌ WITHDRAWAL NOT APPROVED\n\nUser no longer has enough available balance."
    elif row: msg="✅ REQUEST PROCESSED\n\nThe request has been updated successfully."
    else: msg="⚠️ REQUEST ALREADY PROCESSED\n\nNo pending request was found."
    await q.edit_message_text(msg,reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ ADMIN PANEL",callback_data="admin")],
        [InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")],
    ]))
    if isinstance(row,dict):
        try:
            if typ=="approve_dep":
                await context.bot.send_message(row["telegram_id"],f"✅ DEPOSIT APPROVED\n\n━━━━━━━━━━━━━━━━━━\n\nDeposit #{row['id']} has been approved.\n\n🪙 Amount: {float(row['amount']):,.8f} {row['asset']}\n💵 USD Credited: ${float(row.get('usd_value') or row['amount']):,.2f}\n🌐 Network: {row.get('network', '')}\n\n💳 Your balance has been credited successfully.")
            elif typ=="reject_dep":
                await context.bot.send_message(row["telegram_id"],f"❌ DEPOSIT REJECTED\n\n━━━━━━━━━━━━━━━━━━\n\nDeposit #{row['id']} was not approved.")
        except Exception: pass

async def stats(update,context):
    context.user_data.clear()
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    users,balance,pd,pw,active=get_stats()
    await q.edit_message_text(f"📊 ADMIN STATISTICS\n\n━━━━━━━━━━━━━━━━━━\n\n👥 Users: {users}\n💳 Total balances: ${balance:,.2f}\n💰 Pending deposits: {pd}\n📤 Pending withdrawals: {pw}\n🔁 Active copy traders: {active}",reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK",callback_data="admin")],
                [InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")],
            ]))
