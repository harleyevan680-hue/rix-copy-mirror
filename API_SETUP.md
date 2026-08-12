# API setup

Required for the complete live workflow:

1. Telegram BotFather — `BOT_TOKEN`
2. Admin Telegram numeric IDs — `ADMIN_IDS`
3. Helius/Solana RPC — `HELIUS_API_KEY`, `HELIUS_RPC_URL`
4. Jupiter — `JUPITER_API_KEY` if required by your plan
5. Alchemy Ethereum — `ALCHEMY_API_KEY`, `ALCHEMY_ETH_RPC_URL`
6. BNB RPC — `BSC_RPC_URL`
7. BscScan — `BSCSCAN_API_KEY` for BNB transfer indexing
8. CoinGecko — `COINGECKO_API_KEY` for USD pricing
9. 0x — `ZEROX_API_KEY` for EVM swap routing

## Deposit addresses

`SOL_DEPOSIT_ADDRESSES`, `ETH_DEPOSIT_ADDRESSES`, and `BNB_DEPOSIT_ADDRESSES` are comma-separated pools of unique public receiving addresses. One address is assigned to one user per asset. The allocator never intentionally reuses an address; if the pool is exhausted, the deposit screen says that no address is available.

Do not put seed phrases or recovery phrases in Telegram or `.env`.

## Real execution

Set `ENABLE_REAL_TRADING=true` only after you have verified the execution wallet, RPC endpoints, token allowances, gas funds, and swap routes. The signing key is used only by the chain execution adapters and is never shown to users.
