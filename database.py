import sqlite3
from contextlib import closing
from config import DB_PATH

def _conn():
    c=sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory=sqlite3.Row
    return c

def init_database():
    with closing(_conn()) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(telegram_id INTEGER PRIMARY KEY,full_name TEXT,username TEXT,balance REAL NOT NULL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS deposits(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_id INTEGER NOT NULL,asset TEXT NOT NULL,amount REAL NOT NULL,txid TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',created_at TEXT DEFAULT CURRENT_TIMESTAMP,reviewed_at TEXT,usd_value REAL NOT NULL DEFAULT 0,price_usd REAL NOT NULL DEFAULT 0,network TEXT NOT NULL DEFAULT 'SOLANA');
        CREATE TABLE IF NOT EXISTS withdrawals(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_id INTEGER NOT NULL,asset TEXT NOT NULL,amount REAL NOT NULL,address TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',created_at TEXT DEFAULT CURRENT_TIMESTAMP,reviewed_at TEXT);
        CREATE TABLE IF NOT EXISTS copy_traders(telegram_id INTEGER PRIMARY KEY,wallet_address TEXT NOT NULL,chain TEXT NOT NULL DEFAULT 'SOL',allocation REAL NOT NULL,remaining REAL NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,last_signature TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS imported_wallets(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_id INTEGER NOT NULL,network TEXT NOT NULL,address TEXT NOT NULL,label TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(telegram_id,network,address));
        CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_id INTEGER NOT NULL,trade_type TEXT NOT NULL,symbol TEXT,side TEXT,amount_usd REAL NOT NULL DEFAULT 0,status TEXT NOT NULL,tx_hash TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS positions(telegram_id INTEGER NOT NULL,mint TEXT NOT NULL,quantity_base INTEGER NOT NULL DEFAULT 0,cost_usd REAL NOT NULL DEFAULT 0,source_wallet TEXT,source_quantity_base INTEGER NOT NULL DEFAULT 0,source_entry_signature TEXT,PRIMARY KEY(telegram_id,mint));
        """)
        dcols={r[1] for r in db.execute("PRAGMA table_info(deposits)").fetchall()}
        if 'usd_value' not in dcols:
            db.execute("ALTER TABLE deposits ADD COLUMN usd_value REAL NOT NULL DEFAULT 0")
        if 'price_usd' not in dcols:
            db.execute("ALTER TABLE deposits ADD COLUMN price_usd REAL NOT NULL DEFAULT 0")
        if 'network' not in dcols:
            db.execute("ALTER TABLE deposits ADD COLUMN network TEXT NOT NULL DEFAULT 'SOLANA'")

        cols={r[1] for r in db.execute("PRAGMA table_info(copy_traders)").fetchall()}
        if 'chain' not in cols:
            db.execute("ALTER TABLE copy_traders ADD COLUMN chain TEXT NOT NULL DEFAULT 'SOL'")
        if 'remaining' not in cols:
            db.execute("ALTER TABLE copy_traders ADD COLUMN remaining REAL NOT NULL DEFAULT 0")
        pcols={r[1] for r in db.execute("PRAGMA table_info(positions)").fetchall()}
        if 'source_wallet' not in pcols:
            db.execute("ALTER TABLE positions ADD COLUMN source_wallet TEXT")
        if 'source_quantity_base' not in pcols:
            db.execute("ALTER TABLE positions ADD COLUMN source_quantity_base INTEGER NOT NULL DEFAULT 0")
        if 'source_entry_signature' not in pcols:
            db.execute("ALTER TABLE positions ADD COLUMN source_entry_signature TEXT")
        db.execute("UPDATE copy_traders SET remaining=allocation WHERE remaining=0 AND active=1")
        db.commit()

def ensure_user(user):
    with closing(_conn()) as db:
        db.execute("INSERT INTO users(telegram_id,full_name,username) VALUES(?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name,username=excluded.username",(user.id,user.full_name or "",user.username or "")); db.commit()

def get_user_balance(uid):
    with closing(_conn()) as db:
        r=db.execute("SELECT balance FROM users WHERE telegram_id=?",(uid,)).fetchone(); return float(r['balance']) if r else 0.0

def change_balance(uid,amount):
    with closing(_conn()) as db:
        r=db.execute("SELECT balance FROM users WHERE telegram_id=?",(uid,)).fetchone()
        if not r or float(r['balance'])+amount < -1e-9: return False
        db.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?",(amount,uid)); db.commit(); return True

def create_deposit(uid,asset,amount,txid,usd_value=0.0,price_usd=0.0,network="SOLANA"):
    with closing(_conn()) as db:
        c=db.execute(
            "INSERT INTO deposits(telegram_id,asset,amount,txid,usd_value,price_usd,network) VALUES(?,?,?,?,?,?,?)",
            (uid,asset,float(amount),txid,float(usd_value),float(price_usd),network),
        )
        db.commit()
        return c.lastrowid

def get_pending_deposits():
    with closing(_conn()) as db: return db.execute("SELECT * FROM deposits WHERE status='PENDING' ORDER BY id DESC").fetchall()


def get_deposit_by_txid(txid):
    with closing(_conn()) as db:
        r=db.execute('SELECT * FROM deposits WHERE txid=? LIMIT 1',(txid,)).fetchone()
        return dict(r) if r else None


def get_users_with_deposit_addresses():
    _ensure_extended_schema()
    with closing(_conn()) as db:
        return [dict(r) for r in db.execute('SELECT DISTINCT u.telegram_id FROM users u JOIN deposit_addresses d ON d.telegram_id=u.telegram_id').fetchall()]

def approve_deposit(did):
    with closing(_conn()) as db:
        r=db.execute("SELECT * FROM deposits WHERE id=? AND status='PENDING'",(did,)).fetchone()
        if not r:return None
        credit = float(r['usd_value'] or 0) if 'usd_value' in r.keys() else float(r['amount'])
        if credit <= 0:
            credit = float(r['amount'])
        # Guarantee the user row exists before crediting the approved deposit.
        # SQLite UPDATE does not raise an error when zero rows are matched,
        # which previously allowed an approval to succeed without changing balance.
        db.execute(
            "INSERT INTO users(telegram_id,full_name,username) VALUES(?,?,?) "
            "ON CONFLICT(telegram_id) DO NOTHING",
            (r['telegram_id'], "", ""),
        )

        updated = db.execute(
            "UPDATE users SET balance=balance+? WHERE telegram_id=?",
            (credit, r['telegram_id']),
        )
        if updated.rowcount != 1:
            db.rollback()
            return None

        db.execute(
            "INSERT OR IGNORE INTO asset_balances(telegram_id,asset,balance) VALUES(?,?,0)",
            (r['telegram_id'], r['asset']),
        )
        db.execute(
            "UPDATE asset_balances SET balance=balance+? WHERE telegram_id=? AND asset=?",
            (float(r['amount']), r['telegram_id'], r['asset']),
        )
        db.execute(
            "UPDATE deposits SET status='APPROVED',reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
            (did,),
        )
        db.commit()
        result=dict(r)
        result['status']='APPROVED'
        return result

def reject_deposit(did):
    with closing(_conn()) as db:
        r=db.execute("SELECT * FROM deposits WHERE id=? AND status='PENDING'",(did,)).fetchone()
        if not r:return None
        db.execute("UPDATE deposits SET status='REJECTED',reviewed_at=CURRENT_TIMESTAMP WHERE id=?",(did,)); db.commit(); return dict(r)

def create_withdrawal(uid,asset,amount,address):
    with closing(_conn()) as db:
        c=db.execute("INSERT INTO withdrawals(telegram_id,asset,amount,address) VALUES(?,?,?,?)",(uid,asset,amount,address)); db.commit(); return c.lastrowid

def get_pending_withdrawals():
    with closing(_conn()) as db:return db.execute("SELECT * FROM withdrawals WHERE status='PENDING' ORDER BY id DESC").fetchall()

def approve_withdrawal(wid):
    with closing(_conn()) as db:
        r=db.execute("SELECT * FROM withdrawals WHERE id=? AND status='PENDING'",(wid,)).fetchone()
        if not r:return None
        u=db.execute("SELECT balance FROM users WHERE telegram_id=?",(r['telegram_id'],)).fetchone()
        if not u or float(u['balance'])<float(r['amount']):return 'INSUFFICIENT'
        db.execute("UPDATE users SET balance=balance-? WHERE telegram_id=?",(r['amount'],r['telegram_id'])); db.execute("UPDATE withdrawals SET status='APPROVED',reviewed_at=CURRENT_TIMESTAMP WHERE id=?",(wid,)); db.commit(); return dict(r)

def reject_withdrawal(wid):
    with closing(_conn()) as db:
        r=db.execute("SELECT * FROM withdrawals WHERE id=? AND status='PENDING'",(wid,)).fetchone()
        if not r:return None
        db.execute("UPDATE withdrawals SET status='REJECTED',reviewed_at=CURRENT_TIMESTAMP WHERE id=?",(wid,)); db.commit(); return dict(r)

def reserve_copy_allocation(uid,amount): return change_balance(uid,-float(amount))

def create_copy_trader(uid,wallet,allocation,chain='SOL'):
    with closing(_conn()) as db:
        db.execute("INSERT INTO copy_traders(telegram_id,wallet_address,chain,allocation,remaining,active) VALUES(?,?,?,?,?,1) ON CONFLICT(telegram_id) DO UPDATE SET wallet_address=excluded.wallet_address,chain=excluded.chain,allocation=excluded.allocation,remaining=excluded.remaining,active=1",(uid,wallet,chain,allocation,allocation)); db.commit()

def release_copy_allocation(uid):
    # Use a fresh connection. There is no global `db` object in this module.
    with closing(_conn()) as db:
        row = db.execute(
            "SELECT * FROM copy_traders WHERE telegram_id=? AND active=1",
            (uid,),
        ).fetchone()

        if not row:
            return False

        keys = set(row.keys()) if hasattr(row, "keys") else set()
        amount = 0.0

        if "remaining" in keys:
            try:
                amount = max(0.0, float(row["remaining"] or 0))
            except (TypeError, ValueError):
                amount = 0.0
        elif "allocation" in keys:
            try:
                amount = max(0.0, float(row["allocation"] or 0))
            except (TypeError, ValueError):
                amount = 0.0

        db.execute(
            "UPDATE users SET balance=balance+? WHERE telegram_id=?",
            (amount, uid),
        )
        db.execute(
            "UPDATE copy_traders SET active=0, remaining=0 WHERE telegram_id=?",
            (uid,),
        )
        db.commit()
        return True

def stop_copy_trading(uid): return release_copy_allocation(uid)

def get_copy_remaining(uid):
    with closing(_conn()) as db:
        r=db.execute("SELECT remaining FROM copy_traders WHERE telegram_id=? AND active=1",(uid,)).fetchone(); return float(r["remaining"]) if r else 0.0

def change_copy_remaining(uid,amount):
    with closing(_conn()) as db:
        r=db.execute("SELECT remaining FROM copy_traders WHERE telegram_id=? AND active=1",(uid,)).fetchone()
        if not r or float(r["remaining"])+amount < -1e-9: return False
        db.execute("UPDATE copy_traders SET remaining=remaining+? WHERE telegram_id=?",(amount,uid)); db.commit(); return True

def get_copy_trader(uid):
    with closing(_conn()) as db:
        r=db.execute("SELECT * FROM copy_traders WHERE telegram_id=?",(uid,)).fetchone(); return dict(r) if r else None

def get_active_copy_traders():
    with closing(_conn()) as db:return [dict(r) for r in db.execute("SELECT * FROM copy_traders WHERE active=1").fetchall()]

def update_copy_signature(uid,sig):
    with closing(_conn()) as db:db.execute("UPDATE copy_traders SET last_signature=? WHERE telegram_id=?",(sig,uid));db.commit()

def create_trade(uid,symbol,side,amount_usd,status,tx_hash=''):
    with closing(_conn()) as db:
        c=db.execute("INSERT INTO trades(telegram_id,trade_type,symbol,side,amount_usd,status,tx_hash) VALUES(?,?,?,?,?,?,?)",(uid,'TRADE',symbol,side,amount_usd,status,tx_hash));db.commit();return c.lastrowid

def create_copy_trade(uid,symbol,side,amount_usd,status,tx_hash=''):
    with closing(_conn()) as db:
        c=db.execute("INSERT INTO trades(telegram_id,trade_type,symbol,side,amount_usd,status,tx_hash) VALUES(?,?,?,?,?,?,?)",(uid,'COPY',symbol,side,amount_usd,status,tx_hash));db.commit();return c.lastrowid

def upsert_position(uid,mint,delta_base,cost_delta,source_wallet=None,source_quantity_delta=0,source_entry_signature=None):
    with closing(_conn()) as db:
        r=db.execute("SELECT quantity_base,cost_usd,source_wallet,source_quantity_base,source_entry_signature FROM positions WHERE telegram_id=? AND mint=?",(uid,mint)).fetchone()
        q=(int(r['quantity_base']) if r else 0)+int(delta_base)
        c=(float(r['cost_usd']) if r else 0.0)+float(cost_delta)
        sq=(int(r['source_quantity_base']) if r else 0)+int(source_quantity_delta)
        sw=(r['source_wallet'] if r else None) or source_wallet
        se=(r['source_entry_signature'] if r else None) or source_entry_signature
        if q<=0:
            db.execute("DELETE FROM positions WHERE telegram_id=? AND mint=?",(uid,mint))
        else:
            db.execute("""
                INSERT INTO positions(telegram_id,mint,quantity_base,cost_usd,source_wallet,source_quantity_base,source_entry_signature)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(telegram_id,mint) DO UPDATE SET
                    quantity_base=excluded.quantity_base,
                    cost_usd=excluded.cost_usd,
                    source_wallet=excluded.source_wallet,
                    source_quantity_base=excluded.source_quantity_base,
                    source_entry_signature=excluded.source_entry_signature
            """,(uid,mint,q,max(0.0,c),sw,max(0,sq),se))
        db.commit()

def adjust_position_source_quantity(uid,mint,delta):
    with closing(_conn()) as db:
        r=db.execute("SELECT quantity_base,source_quantity_base FROM positions WHERE telegram_id=? AND mint=?",(uid,mint)).fetchone()
        if not r:return False
        sq=max(0,int(r['source_quantity_base'])+int(delta))
        db.execute("UPDATE positions SET source_quantity_base=? WHERE telegram_id=? AND mint=?",(sq,uid,mint))
        db.commit()
        return True

def set_position_source_quantity(uid,mint,source_quantity,source_entry_signature=None):
    with closing(_conn()) as db:
        r=db.execute("SELECT 1 FROM positions WHERE telegram_id=? AND mint=?",(uid,mint)).fetchone()
        if not r:
            return False
        if source_entry_signature is None:
            db.execute("UPDATE positions SET source_quantity_base=? WHERE telegram_id=? AND mint=?",(max(0,int(source_quantity)),uid,mint))
        else:
            db.execute("UPDATE positions SET source_quantity_base=?,source_entry_signature=? WHERE telegram_id=? AND mint=?",(max(0,int(source_quantity)),source_entry_signature,uid,mint))
        db.commit()
        return True


def get_users_with_positions():
    with closing(_conn()) as db:
        rows=db.execute('SELECT DISTINCT telegram_id FROM positions WHERE quantity_base>0').fetchall()
        return [int(r['telegram_id']) for r in rows]

def get_position(uid,mint):
    with closing(_conn()) as db:
        r=db.execute("SELECT * FROM positions WHERE telegram_id=? AND mint=?",(uid,mint)).fetchone();return dict(r) if r else None

def get_positions(uid):
    with closing(_conn()) as db:return [dict(r) for r in db.execute("SELECT * FROM positions WHERE telegram_id=? AND quantity_base>0",(uid,)).fetchall()]

def get_stats():
    with closing(_conn()) as db:
        return tuple(db.execute("SELECT (SELECT COUNT(*) FROM users),(SELECT COALESCE(SUM(balance),0) FROM users),(SELECT COUNT(*) FROM deposits WHERE status='PENDING'),(SELECT COUNT(*) FROM withdrawals WHERE status='PENDING'),(SELECT COUNT(*) FROM copy_traders WHERE active=1)").fetchone())


def add_imported_wallet(uid, network, address, label=""):
    with closing(_conn()) as db:
        db.execute("INSERT OR IGNORE INTO imported_wallets(telegram_id,network,address,label) VALUES(?,?,?,?)",(uid,network,address,label or ""))
        db.commit()

def get_imported_wallets(uid):
    with closing(_conn()) as db:
        return [dict(r) for r in db.execute("SELECT * FROM imported_wallets WHERE telegram_id=? ORDER BY id DESC",(uid,)).fetchall()]

def delete_imported_wallet(uid, wid):
    with closing(_conn()) as db:
        db.execute("DELETE FROM imported_wallets WHERE id=? AND telegram_id=?",(wid,uid)); db.commit()

# ---------- Multi-asset / deposit-address / autotrade extensions ----------
def _ensure_extended_schema():
    with closing(_conn()) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS asset_balances(telegram_id INTEGER NOT NULL,asset TEXT NOT NULL,balance REAL NOT NULL DEFAULT 0,PRIMARY KEY(telegram_id,asset));
        CREATE TABLE IF NOT EXISTS deposit_addresses(telegram_id INTEGER NOT NULL,asset TEXT NOT NULL,address TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(telegram_id,asset),UNIQUE(asset,address));
        CREATE TABLE IF NOT EXISTS autotrade_settings(telegram_id INTEGER NOT NULL,asset TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 0,stop_loss REAL NOT NULL DEFAULT 10,take_profit REAL NOT NULL DEFAULT 50,max_daily INTEGER NOT NULL DEFAULT 5,PRIMARY KEY(telegram_id,asset));
        CREATE TABLE IF NOT EXISTS user_controls(telegram_id INTEGER PRIMARY KEY,banned INTEGER NOT NULL DEFAULT 0);
        """)
        for uid in [r[0] for r in db.execute('SELECT telegram_id FROM users').fetchall()]:
            for asset in ('SOL','ETH','BNB'):
                db.execute('INSERT OR IGNORE INTO asset_balances(telegram_id,asset,balance) VALUES(?,?,0)',(uid,asset))
                db.execute('INSERT OR IGNORE INTO autotrade_settings(telegram_id,asset) VALUES(?,?)',(uid,asset))
        db.commit()

_orig_init_database = init_database
def init_database():
    _orig_init_database()
    _ensure_extended_schema()


def ensure_user(user):
    with closing(_conn()) as db:
        db.execute("INSERT INTO users(telegram_id,full_name,username) VALUES(?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name,username=excluded.username",(user.id,user.full_name or "",user.username or ""))
        for asset in ('SOL','ETH','BNB'):
            db.execute('INSERT OR IGNORE INTO asset_balances(telegram_id,asset,balance) VALUES(?,?,0)',(user.id,asset))
            db.execute('INSERT OR IGNORE INTO autotrade_settings(telegram_id,asset) VALUES(?,?)',(user.id,asset))
        db.commit()
    return get_user(user.id)


def get_user(uid):
    with closing(_conn()) as db:
        r=db.execute('SELECT * FROM users WHERE telegram_id=?',(uid,)).fetchone()
        return dict(r) if r else None


def get_asset_balances(uid):
    _ensure_extended_schema()
    with closing(_conn()) as db:
        rows=db.execute('SELECT asset,balance FROM asset_balances WHERE telegram_id=?',(uid,)).fetchall()
        out={a:0.0 for a in ('SOL','ETH','BNB')}
        out.update({r['asset']:float(r['balance']) for r in rows})
        return out


def credit_asset(uid,asset,amount):
    ensure_user(type('U',(),{'id':uid,'full_name':'','username':''})())
    with closing(_conn()) as db:
        db.execute('INSERT OR IGNORE INTO asset_balances(telegram_id,asset,balance) VALUES(?,?,0)',(uid,asset))
        db.execute('UPDATE asset_balances SET balance=balance+? WHERE telegram_id=? AND asset=?',(float(amount),uid,asset)); db.commit()


def get_or_assign_deposit_address(uid,asset,pool):
    ensure_user(type('U',(),{'id':uid,'full_name':'','username':''})())
    with closing(_conn()) as db:
        r=db.execute('SELECT address FROM deposit_addresses WHERE telegram_id=? AND asset=?',(uid,asset)).fetchone()
        if r:return r['address']
        used={r['address'] for r in db.execute('SELECT address FROM deposit_addresses WHERE asset=?',(asset,)).fetchall()}
        address=next((a for a in pool if a not in used), None)
        if not address:
            return ''
        db.execute('INSERT INTO deposit_addresses(telegram_id,asset,address) VALUES(?,?,?)',(uid,asset,address)); db.commit(); return address


def get_autotrade_settings(uid):
    _ensure_extended_schema()
    with closing(_conn()) as db:
        rows=db.execute('SELECT asset,enabled,stop_loss,take_profit,max_daily FROM autotrade_settings WHERE telegram_id=?',(uid,)).fetchall()
        out={a:{'enabled':False,'sl':10.0,'tp':50.0,'max_daily':5} for a in ('SOL','ETH','BNB')}
        for r in rows: out[r['asset']]={'enabled':bool(r['enabled']),'sl':float(r['stop_loss']),'tp':float(r['take_profit']),'max_daily':int(r['max_daily'])}
        return out


def save_autotrade_settings(uid,chain=None,sl=10,tp=50,max_daily=5,enabled=None):
    _ensure_extended_schema()
    with closing(_conn()) as db:
        assets=[chain] if chain else ['SOL','ETH','BNB']
        for asset in assets:
            if enabled is None:
                db.execute('INSERT INTO autotrade_settings(telegram_id,asset,stop_loss,take_profit,max_daily) VALUES(?,?,?,?,?) ON CONFLICT(telegram_id,asset) DO UPDATE SET stop_loss=excluded.stop_loss,take_profit=excluded.take_profit,max_daily=excluded.max_daily',(uid,asset,float(sl),float(tp),int(max_daily)))
            else:
                db.execute('INSERT INTO autotrade_settings(telegram_id,asset,enabled) VALUES(?,?,?) ON CONFLICT(telegram_id,asset) DO UPDATE SET enabled=excluded.enabled',(uid,asset,int(enabled)))
        db.commit()


def get_trade_history(uid, limit=20):
    with closing(_conn()) as db:
        rows=db.execute("SELECT * FROM trades WHERE telegram_id=? ORDER BY id DESC LIMIT ?",(uid,int(limit))).fetchall()
        return [dict(r) for r in rows]


def get_asset_balance(uid, asset):
    return get_asset_balances(uid).get(asset.upper(), 0.0)


def change_asset_balance(uid, asset, amount):
    ensure_user(type('U',(),{'id':uid,'full_name':'','username':''})())
    with closing(_conn()) as db:
        r=db.execute('SELECT balance FROM asset_balances WHERE telegram_id=? AND asset=?',(uid,asset.upper())).fetchone()
        current=float(r['balance']) if r else 0.0
        if current+float(amount) < -1e-12:
            return False
        db.execute('INSERT OR IGNORE INTO asset_balances(telegram_id,asset,balance) VALUES(?,?,0)',(uid,asset.upper()))
        db.execute('UPDATE asset_balances SET balance=balance+? WHERE telegram_id=? AND asset=?',(float(amount),uid,asset.upper()))
        db.commit(); return True


def get_all_users():
    with closing(_conn()) as db:
        return [dict(r) for r in db.execute("SELECT u.*, COALESCE(c.banned,0) AS banned FROM users u LEFT JOIN user_controls c ON c.telegram_id=u.telegram_id ORDER BY u.created_at DESC").fetchall()]

def get_user_by_identifier(identifier):
    identifier=(identifier or '').strip()
    with closing(_conn()) as db:
        if identifier.lstrip('-').isdigit():
            r=db.execute("SELECT u.*, COALESCE(c.banned,0) AS banned FROM users u LEFT JOIN user_controls c ON c.telegram_id=u.telegram_id WHERE u.telegram_id=?",(int(identifier),)).fetchone()
        else:
            name=identifier.lstrip('@')
            r=db.execute("SELECT u.*, COALESCE(c.banned,0) AS banned FROM users u LEFT JOIN user_controls c ON c.telegram_id=u.telegram_id WHERE lower(COALESCE(u.username,''))=lower(?) LIMIT 1",(name,)).fetchone()
        return dict(r) if r else None

def set_user_banned(uid,banned):
    with closing(_conn()) as db:
        db.execute("INSERT INTO user_controls(telegram_id,banned) VALUES(?,?) ON CONFLICT(telegram_id) DO UPDATE SET banned=excluded.banned",(int(uid),1 if banned else 0)); db.commit()
        return True

def is_user_banned(uid):
    with closing(_conn()) as db:
        r=db.execute("SELECT banned FROM user_controls WHERE telegram_id=?",(int(uid),)).fetchone()
        return bool(r and r['banned'])
