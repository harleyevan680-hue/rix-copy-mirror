# Riz Copy Mirror

A Telegram copy-trading application with SOL, ETH and BNB workflows, automatic deposit detection, admin approval, balances, copy-wallet monitoring, autotrade rules, portfolio/history, and secure public-address wallet import.

## What is complete
- 19 compact inline main-menu buttons.
- SOL / ETH / BNB first-row copy-text buttons when the installed Telegram Bot API/PTB supports `CopyTextButton`; fallback shows the address without changing the account state.
- Unique per-user deposit-address assignment from administrator-managed address pools.
- Automatic on-chain deposit scanning; no manual TXID entry is required.
- Admin approval credits both the approved USD trading balance and the deposited asset balance.
- Import Wallet is watch-only and accepts public addresses only. It is never used as a copy-trader address.
- Copy Trading separately asks for the trader's public SOL/ETH/BNB address and a user-approved allocation.
- Auto Trading configuration for SOL/ETH/BNB with stop-loss, take-profit, and max daily trades.
- Buy/sell, transfer, withdrawal request, portfolio, history, settings, profile and support flows.
- `.env` and `.env.example` included.

## Important configuration
1. Copy `.env.example` to `.env` or edit the included `.env`.
2. Set `BOT_TOKEN` and `ADMIN_IDS`.
3. Populate enough unique addresses in `SOL_DEPOSIT_ADDRESSES`, `ETH_DEPOSIT_ADDRESSES`, and `BNB_DEPOSIT_ADDRESSES` for your expected users. **Never reuse a receiving address between users.**
4. Set the RPC/indexer/API keys.
5. Keep `ENABLE_REAL_TRADING=false` while testing.
6. For real execution, the execution wallet must be funded and its signing key must be stored securely outside Telegram. Never put a seed phrase/recovery phrase in chat.

## Run
```powershell
py -m pip install -r requirements.txt
py bot.py
```

## Verification performed in this build
- Python bytecode compilation (`compileall`)
- Local database smoke test
- Static callback/import review

A live Telegram/blockchain end-to-end test still requires the user's own credentials, funded execution wallet (for real mode), and live networks.
