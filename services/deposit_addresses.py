import os
from database import get_or_assign_deposit_address


def _pool(name):
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


def get_user_deposit_address(uid, asset):
    asset = asset.upper()
    pools = {
        "SOL": _pool("SOL_DEPOSIT_ADDRESSES"),
        "ETH": _pool("ETH_DEPOSIT_ADDRESSES"),
        "BNB": _pool("BNB_DEPOSIT_ADDRESSES"),
    }
    pool = pools.get(asset, [])
    if not pool:
        # Optional single-address fallback for initial testing.
        fallback = os.getenv(f"DEPOSIT_{asset}_ADDRESS", "").strip()
        if fallback:
            return get_or_assign_deposit_address(uid, asset, [fallback])
        return ""
    return get_or_assign_deposit_address(uid, asset, pool)
