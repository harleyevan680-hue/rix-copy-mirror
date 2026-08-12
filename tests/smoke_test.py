import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os
import tempfile

fd, path = tempfile.mkstemp(suffix='.db')
os.close(fd)
os.environ['DB_PATH'] = path
os.environ['BOT_TOKEN'] = 'test'
os.environ['ADMIN_IDS'] = '1'

from database import init_database, ensure_user, create_deposit, approve_deposit, get_user_balance, get_asset_balances

class U:
    id = 991
    full_name = 'Smoke Test'
    username = 'smoke'

init_database()
ensure_user(U())
did = create_deposit(991, 'SOL', 1.25, 'smoke-tx', usd_value=200.0, price_usd=160.0, network='Solana')
row = approve_deposit(did)
assert row and row['status'] == 'APPROVED'
assert abs(get_user_balance(991) - 200.0) < 1e-9
assert abs(get_asset_balances(991)['SOL'] - 1.25) < 1e-9
print('SMOKE TEST PASSED')
os.unlink(path)
