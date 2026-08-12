from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_IDS
from database import (
    get_pending_deposits,get_pending_withdrawals,approve_deposit,reject_deposit,
    approve_withdrawal,reject_withdrawal,get_stats,get_all_users,get_user_by_identifier,
    set_user_banned,is_user_banned
)


def is_admin(uid): return uid in ADMIN_IDS


def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Pending Deposits",callback_data="admin_deposits")],
        [InlineKeyboardButton("📤 Pending Withdrawals",callback_data="admin_withdrawals")],
        [InlineKeyboardButton("👥 Manage Users",callback_data="admin_users")],
        [InlineKeyboardButton("📢 Broadcast Message",callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 Statistics",callback_data="admin_stats")],
        [InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")],
    ])


async def admin_command(update, context):
    """Open the admin panel from /admin for authorized administrators only."""
    if not update.effective_user or not is_admin(update.effective_user.id):
        if update.message:
            await update.message.reply_text("❌ ACCESS DENIED")
        return
    context.user_data.pop("admin_stage", None)
    await update.message.reply_text(
        "🛡️ ADMIN PANEL\n\n━━━━━━━━━━━━━━━━━━\n\nManage deposits, withdrawals, users and platform activity.",
        reply_markup=admin_keyboard(),
    )


async def panel(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): await q.edit_message_text("❌ ACCESS DENIED"); return
    context.user_data.pop("admin_stage",None)
    await q.edit_message_text("🛡️ ADMIN PANEL\n\n━━━━━━━━━━━━━━━━━━\n\nManage deposits, withdrawals, users and platform activity.",reply_markup=admin_keyboard())


async def users(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    context.user_data["admin_stage"]="find_user"
    await q.edit_message_text("👥 MANAGE USERS\n\n━━━━━━━━━━━━━━━━━━\n\nSend the Telegram ID or @username of the user you want to manage.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK",callback_data="back")]]))


async def user_profile(update,context,uid=None):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    if uid is None: uid=context.user_data.get("admin_user_id")
    u=get_user_by_identifier(str(uid)) if uid is not None else None
    if not u:
        await q.edit_message_text("❌ USER NOT FOUND.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK",callback_data="back")]])); return
    context.user_data["admin_user_id"]=u["telegram_id"]
    status="🚫 BANNED" if u.get("banned") else "🟢 ACTIVE"
    uname=f"@{u['username']}" if u.get('username') else "none"
    text=(f"👤 USER PROFILE\n\n━━━━━━━━━━━━━━━━━━\n\n"
          f"Name: {u.get('full_name') or 'Unknown'}\n"
          f"Username: {uname}\n"
          f"Telegram ID: <code>{u['telegram_id']}</code>\n"
          f"Joined: {u.get('created_at') or 'Unknown'}\n"
          f"Balance: ${float(u.get('balance') or 0):,.2f}\n"
          f"Status: {status}")
    toggle="✅ UNBAN USER" if u.get("banned") else "🚫 BAN USER"
    action="admin_unban" if u.get("banned") else "admin_ban"
    await q.edit_message_text(text,parse_mode="HTML",reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle,callback_data=action)],
        [InlineKeyboardButton("🔙 BACK",callback_data="back")],
        [InlineKeyboardButton("🛡️ ADMIN PANEL",callback_data="admin")],
    ]))


async def user_action(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    uid=context.user_data.get("admin_user_id")
    if not uid:
        await q.edit_message_text("❌ No user selected.",reply_markup=admin_keyboard()); return
    banned=q.data=="admin_ban"
    set_user_banned(uid,banned)
    try:
        await context.bot.send_message(uid, "🚫 Your account has been banned by an administrator." if banned else "✅ Your account has been unbanned and access has been restored.")
    except Exception: pass
    await q.edit_message_text("🚫 USER BANNED" if banned else "✅ USER UNBANNED",reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 VIEW PROFILE",callback_data="admin_user_view")],
        [InlineKeyboardButton("👥 MANAGE USERS",callback_data="admin_users")],
        [InlineKeyboardButton("🛡️ ADMIN PANEL",callback_data="admin")],
    ]))


async def broadcast(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    context.user_data["admin_stage"]="broadcast"
    await q.edit_message_text("📢 BROADCAST MESSAGE\n\n━━━━━━━━━━━━━━━━━━\n\nSend the message you want to broadcast to all users.\n\n⚠️ The message will be sent exactly as received.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK",callback_data="back")]]))


async def admin_text(update,context):
    if not update.message or not update.effective_user or not is_admin(update.effective_user.id): return False
    stage=context.user_data.get("admin_stage")
    if stage=="find_user":
        identifier=update.message.text.strip()
        u=get_user_by_identifier(identifier)
        if not u:
            await update.message.reply_text("❌ USER NOT FOUND.\n\nSend a valid Telegram ID or @username.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK",callback_data="back")]])); return True
        context.user_data["admin_stage"]=""
        context.user_data["admin_user_id"]=u["telegram_id"]
        status="🚫 BANNED" if u.get("banned") else "🟢 ACTIVE"
        uname=f"@{u['username']}" if u.get('username') else "none"
        text=(f"👤 USER PROFILE\n\n━━━━━━━━━━━━━━━━━━\n\nName: {u.get('full_name') or 'Unknown'}\nUsername: {uname}\nTelegram ID: <code>{u['telegram_id']}</code>\nJoined: {u.get('created_at') or 'Unknown'}\nBalance: ${float(u.get('balance') or 0):,.2f}\nStatus: {status}")
        toggle="✅ UNBAN USER" if u.get("banned") else "🚫 BAN USER"
        action="admin_unban" if u.get("banned") else "admin_ban"
        await update.message.reply_text(text,parse_mode="HTML",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(toggle,callback_data=action)],[InlineKeyboardButton("🔙 BACK",callback_data="back")],[InlineKeyboardButton("🛡️ ADMIN PANEL",callback_data="admin")]]))
        return True
    if stage=="broadcast":
        text=update.message.text
        users_list=get_all_users(); sent=failed=0
        for u in users_list:
            if u.get("banned"): continue
            try:
                await context.bot.send_message(u["telegram_id"],text)
                sent+=1
            except Exception:
                failed+=1
        context.user_data.pop("admin_stage",None)
        await update.message.reply_text(f"📢 BROADCAST COMPLETE\n\n━━━━━━━━━━━━━━━━━━\n\n✅ Sent: {sent}\n❌ Failed: {failed}",reply_markup=admin_keyboard())
        return True
    return False


async def deposits(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    rows=get_pending_deposits()
    if not rows: await q.edit_message_text("💰 PENDING DEPOSITS\n\n━━━━━━━━━━━━━━━━━━\n\nNo pending deposits.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK",callback_data="back")],[InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")]])); return
    r=rows[0]
    await q.edit_message_text(f"🔔 NEW DEPOSIT REQUEST\n\n━━━━━━━━━━━━━━━━━━\n\n👤 USER\n<code>{r['telegram_id']}</code>\n\n💰 DEPOSIT\nAsset: {r['asset']}\nAmount: {float(r['amount']):,.8f} {r['asset']}\nUSD Value: ${float(r['usd_value'] or 0):,.2f}\nNetwork: {r['network']}\n\n🆔 DEPOSIT ID\n#{r['id']}\n\n🔗 TRANSACTION\n<code>{r['txid']}</code>\n\n━━━━━━━━━━━━━━━━━━\n⚠️ Review the transaction before approving.",parse_mode="HTML",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ APPROVE",callback_data=f"approve_dep:{r['id']}"),InlineKeyboardButton("❌ REJECT",callback_data=f"reject_dep:{r['id']}")],[InlineKeyboardButton("🔙 BACK",callback_data="back")],[InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")]]))


async def withdrawals(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    rows=get_pending_withdrawals()
    if not rows: await q.edit_message_text("📤 PENDING WITHDRAWALS\n\n━━━━━━━━━━━━━━━━━━\n\nNo pending withdrawals.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK",callback_data="back")],[InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")]])); return
    r=rows[0]
    await q.edit_message_text(f"🔔 WITHDRAWAL REQUEST\n\n━━━━━━━━━━━━━━━━━━\n\n👤 USER\n<code>{r['telegram_id']}</code>\n\n💵 Amount: {r['amount']} {r['asset']}\n\n📍 ADDRESS\n<code>{r['address']}</code>\n\n🆔 REQUEST #{r['id']}",parse_mode="HTML",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ APPROVE",callback_data=f"approve_w:{r['id']}"),InlineKeyboardButton("❌ REJECT",callback_data=f"reject_w:{r['id']}")],[InlineKeyboardButton("🔙 BACK",callback_data="back")],[InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")]]))


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
    await q.edit_message_text(msg,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛡️ ADMIN PANEL",callback_data="admin")],[InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")]]))
    if isinstance(row,dict):
        try:
            if typ=="approve_dep":
                await context.bot.send_message(row["telegram_id"],f"✅ DEPOSIT APPROVED\n\n━━━━━━━━━━━━━━━━━━\n\nDeposit #{row['id']} has been approved.\n\n🪙 Amount: {float(row['amount']):,.8f} {row['asset']}\n💵 USD Credited: ${float(row.get('usd_value') or row['amount']):,.2f}\n🌐 Network: {row.get('network', '')}\n\n💳 Your balance has been credited successfully.")
            elif typ=="reject_dep": await context.bot.send_message(row["telegram_id"],f"❌ DEPOSIT REJECTED\n\n━━━━━━━━━━━━━━━━━━\n\nDeposit #{row['id']} was not approved.")
        except Exception: pass


async def stats(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    users,balance,pd,pw,active=get_stats()
    await q.edit_message_text(f"📊 ADMIN STATISTICS\n\n━━━━━━━━━━━━━━━━━━\n\n👥 Users: {users}\n💳 Total balances: ${balance:,.2f}\n💰 Pending deposits: {pd}\n📤 Pending withdrawals: {pw}\n🔁 Active copy traders: {active}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK",callback_data="back")],[InlineKeyboardButton("🏠 MAIN MENU",callback_data="home")]]))
