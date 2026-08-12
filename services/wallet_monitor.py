import httpx
from solders.pubkey import Pubkey
from config import SOLANA_RPC_URL

class WalletMonitor:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=20)
    @staticmethod
    def validate_address(address):
        try:
            Pubkey.from_string(address.strip())
            return True
        except Exception:
            return False
    async def rpc(self, method, params):
        r = await self.client.post(SOLANA_RPC_URL, json={"jsonrpc":"2.0","id":1,"method":method,"params":params})
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        return data.get("result")
    async def get_signatures(self, wallet, limit=10):
        return await self.rpc("getSignaturesForAddress", [wallet, {"limit": min(max(limit,1),100)}]) or []
    async def get_transaction(self, signature):
        return await self.rpc("getTransaction", [signature, {"encoding":"jsonParsed","maxSupportedTransactionVersion":0}])
    async def close(self):
        await self.client.aclose()

wallet_monitor = WalletMonitor()
