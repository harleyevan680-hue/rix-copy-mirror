import time
import logging
import httpx

logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
COIN_IDS = {
    "SOL": "solana",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "USDT": "tether",
}

_cache = {}
CACHE_SECONDS = 15.0

async def get_usd_price(asset: str) -> float:
    asset = asset.upper()
    coin_id = COIN_IDS.get(asset)
    if not coin_id:
        raise ValueError(f"Unsupported deposit asset: {asset}")

    now = time.monotonic()
    cached = _cache.get(asset)
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1]

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            COINGECKO_URL,
            params={"ids": coin_id, "vs_currencies": "usd"},
        )
        response.raise_for_status()
        data = response.json()

    price = float(data[coin_id]["usd"])
    if price <= 0:
        raise RuntimeError(f"Invalid USD price returned for {asset}")

    _cache[asset] = (now, price)
    return price
