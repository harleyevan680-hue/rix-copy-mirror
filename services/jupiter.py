import base64, asyncio, httpx
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from config import SOLANA_RPC_URL,JUPITER_API_KEY,ENABLE_REAL_TRADING,EXECUTION_PRIVATE_KEY,DEFAULT_SLIPPAGE_BPS
SOL_MINT="So11111111111111111111111111111111111111112"
USDC_MINT="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

class Jupiter:
    def __init__(self): self.client=httpx.AsyncClient(timeout=40,headers={"x-api-key":JUPITER_API_KEY} if JUPITER_API_KEY else {})
    def keypair(self):
        if not EXECUTION_PRIVATE_KEY: raise RuntimeError("EXECUTION_PRIVATE_KEY is not configured.")
        return Keypair.from_base58_string(EXECUTION_PRIVATE_KEY)
    def execution_public_key(self): return str(self.keypair().pubkey())
    async def quote(self,input_mint,output_mint,amount,slippage_bps=None):
        if input_mint==output_mint: raise ValueError("Input and output tokens must be different.")
        r=await self.client.get("https://api.jup.ag/swap/v1/quote",params={"inputMint":input_mint,"outputMint":output_mint,"amount":str(int(amount)),"slippageBps":str(DEFAULT_SLIPPAGE_BPS if slippage_bps is None else slippage_bps)})
        r.raise_for_status(); return r.json()
    async def execute_quote(self,quote):
        if not ENABLE_REAL_TRADING: raise RuntimeError("REAL TRADING IS DISABLED. Set ENABLE_REAL_TRADING=true after funding and checking the execution wallet.")
        kp=self.keypair(); owner=str(kp.pubkey())
        r=await self.client.post("https://api.jup.ag/swap/v1/swap",json={"quoteResponse":quote,"userPublicKey":owner,"wrapAndUnwrapSol":True,"dynamicComputeUnitLimit":True})
        r.raise_for_status(); data=r.json(); raw=base64.b64decode(data["swapTransaction"])
        tx=VersionedTransaction.from_bytes(raw); signed=VersionedTransaction(tx.message,[kp]); encoded=base64.b64encode(bytes(signed)).decode()
        rpc=await self.client.post(SOLANA_RPC_URL,json={"jsonrpc":"2.0","id":1,"method":"sendTransaction","params":[encoded,{"encoding":"base64","skipPreflight":False,"preflightCommitment":"confirmed","maxRetries":3}]})
        rpc.raise_for_status(); out=rpc.json()
        if out.get("error"): raise RuntimeError(str(out["error"]))
        sig=out.get("result")
        if not sig: raise RuntimeError("Solana did not return a transaction signature.")
        for _ in range(30):
            st=await self.client.post(SOLANA_RPC_URL,json={"jsonrpc":"2.0","id":1,"method":"getSignatureStatuses","params":[[sig],{"searchTransactionHistory":True}]})
            st.raise_for_status(); vals=(st.json().get("result") or {}).get("value") or []
            if vals and vals[0]:
                if vals[0].get("err") is not None: raise RuntimeError(f"Transaction failed: {vals[0]['err']}")
                if vals[0].get("confirmationStatus") in ("confirmed","finalized"): return sig
            await asyncio.sleep(1)
        raise RuntimeError("Transaction was submitted but confirmation timed out.")
    async def close(self): await self.client.aclose()
jupiter=Jupiter()
