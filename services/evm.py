"""Ethereum/BNB helpers.

The EVM adapter uses JSON-RPC for reads and the 0x v1 quote endpoint for
transaction construction.  Real signing is opt-in and uses the execution
key only when ENABLE_REAL_TRADING=true.
"""
import asyncio
import httpx
from config import ALCHEMY_ETH_RPC_URL, BSC_RPC_URL, ZEROX_API_KEY, BSCSCAN_API_KEY, ENABLE_REAL_TRADING, EXECUTION_PRIVATE_KEY

NATIVE = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
CHAINS = {
    "ETH": {"chain_id": 1, "rpc": ALCHEMY_ETH_RPC_URL, "native": NATIVE},
    "BNB": {"chain_id": 56, "rpc": BSC_RPC_URL, "native": NATIVE},
}

class EVMService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30)

    def rpc_url(self, chain):
        return CHAINS[chain]["rpc"]

    async def rpc(self, chain, method, params=None):
        r = await self.client.post(self.rpc_url(chain), json={"jsonrpc":"2.0","id":1,"method":method,"params":params or []})
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        return data.get("result")

    async def balance(self, chain, address):
        value = await self.rpc(chain, "eth_getBalance", [address, "latest"])
        return int(value, 16) / 10**18

    async def transfers(self, chain, address, start_block=None, end_block=None):
        """Return native/token transfers for a wallet.

        ETH uses Alchemy's asset-transfer endpoint when available.  BNB falls
        back to normal RPC transaction scanning for native transfers; token
        transfer indexing is intentionally delegated to BscScan when a key is
        configured in the deposit monitor.
        """
        if chain == "ETH" and "alchemy.com" in self.rpc_url(chain):
            params = [{
                "fromBlock": start_block or "0x0",
                "toBlock": end_block or "latest",
                "fromAddress": address,
                "category": ["external", "erc20", "erc721", "erc1155"],
                "withMetadata": True,
                "excludeZeroValue": True,
                "maxCount": "0x64",
            }]
            try:
                out = await self.rpc(chain, "alchemy_getAssetTransfers", params)
                return out.get("transfers", []) if out else []
            except Exception:
                return []
        if chain == "BNB" and BSCSCAN_API_KEY:
            url = "https://api.bscscan.com/api"
            base={"address":address,"startblock":0,"endblock":99999999,"page":1,"offset":100,"sort":"desc","apikey":BSCSCAN_API_KEY}
            out=[]
            for action in ("txlist","txlistinternal","tokentx"):
                params=dict(base); params["module"]="account"; params["action"]=action
                r=await self.client.get(url,params=params); r.raise_for_status(); data=r.json()
                for x in (data.get("result") or []):
                    if not isinstance(x,dict): continue
                    if action=="tokentx":
                        out.append({"hash":x.get("hash"),"from":x.get("from"),"to":x.get("to"),"asset":x.get("tokenSymbol") or "TOKEN","rawContract":{"address":x.get("contractAddress"),"value":hex(int(x.get("value") or 0))}})
                    else:
                        out.append({"hash":x.get("hash"),"from":x.get("from"),"to":x.get("to"),"asset":"BNB","value":str(x.get("value") or "0")})
            return out
        return []

    def execution_address(self):
        if not EXECUTION_PRIVATE_KEY:
            raise RuntimeError("EXECUTION_PRIVATE_KEY is not configured.")
        try:
            from eth_account import Account
        except ImportError as exc:
            raise RuntimeError("Install web3 to enable EVM execution.") from exc
        return Account.from_key(EXECUTION_PRIVATE_KEY).address

    async def zero_x_quote(self, chain, sell_token, buy_token, sell_amount, taker):
        if not ZEROX_API_KEY:
            raise RuntimeError("ZEROX_API_KEY is not configured.")
        url = "https://api.0x.org/swap/v1/quote"
        r = await self.client.get(url, headers={"0x-api-key": ZEROX_API_KEY}, params={
            "chainId": CHAINS[chain]["chain_id"],
            "sellToken": sell_token,
            "buyToken": buy_token,
            "sellAmount": str(int(sell_amount)),
            "takerAddress": taker,
        })
        r.raise_for_status()
        return r.json()

    async def execute_quote(self, quote):
        if not ENABLE_REAL_TRADING:
            raise RuntimeError("REAL TRADING IS DISABLED.")
        if not EXECUTION_PRIVATE_KEY:
            raise RuntimeError("EXECUTION_PRIVATE_KEY is not configured.")
        try:
            from web3 import Web3
            from eth_account import Account
        except ImportError as exc:
            raise RuntimeError("Install web3 to enable EVM execution.") from exc
        chain_id = int(quote.get("chainId") or 1)
        rpc = CHAINS["ETH"]["rpc"] if chain_id == 1 else CHAINS["BNB"]["rpc"]
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
        acct = Account.from_key(EXECUTION_PRIVATE_KEY)
        tx = {
            "from": acct.address,
            "to": Web3.to_checksum_address(quote["to"]),
            "data": quote.get("data", "0x"),
            "value": int(quote.get("value", "0"), 16) if isinstance(quote.get("value"), str) else int(quote.get("value", 0)),
            "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
            "chainId": chain_id,
        }
        if chain_id == 1:
            tx["maxFeePerGas"] = w3.eth.gas_price * 2
            tx["maxPriorityFeePerGas"] = w3.to_wei(1, "gwei")
        else:
            tx["gasPrice"] = w3.eth.gas_price
        tx["gas"] = int(quote.get("gas", 500000))
        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status != 1:
            raise RuntimeError("EVM transaction failed on-chain.")
        return tx_hash.hex()

    async def close(self):
        await self.client.aclose()

evm = EVMService()
