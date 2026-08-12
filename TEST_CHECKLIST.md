# Verification checklist

Local checks performed:

- `python -m compileall -q .` — PASS
- `python tests/smoke_test.py` — PASS

Manual/live checks required on the user's machine:

1. Install `requirements.txt`.
2. Fill `.env`.
3. Start the bot.
4. Press `/start` and verify admin notification.
5. Press Continue and verify all 19 buttons.
6. Verify SOL/ETH/BNB copy-text behavior on the Telegram client.
7. Configure unique deposit address pools.
8. Send a small test deposit on each network.
9. Verify automatic detection and admin approval.
10. Verify asset and approved USD balances after approval.
11. Add a public trader wallet and verify source transactions are detected.
12. Keep `ENABLE_REAL_TRADING=false` until every test passes.
13. Only then test real execution with a small amount and a funded execution wallet.
