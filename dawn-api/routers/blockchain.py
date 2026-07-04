"""
v21.0 — Blockchain & Web3
Blockchain node access, smart contract analysis, on-chain data, DeFi monitoring
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from config import settings as app_settings
import db.client as db

logger = logging.getLogger(__name__)
router = APIRouter()

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ─── Schemas ──────────────────────────────────────────────────────────────

class BlockchainNetworkCreate(BaseModel):
    name: str
    chain_id: int
    rpc_url: str
    explorer_url: Optional[str] = None
    native_currency: str = "ETH"
    is_active: bool = True

class ContractAnalysisRequest(BaseModel):
    contract_address: str
    network_id: str
    contract_name: Optional[str] = None
    abi: Optional[str] = None

class WalletQuery(BaseModel):
    address: str
    network_id: str

class DeFiPositionQuery(BaseModel):
    wallet_address: str
    protocol: Optional[str] = None  # 'uniswap', 'aave', 'compound', etc.

# ─── Network Management ───────────────────────────────────────────────────

@router.get("/blockchain/networks", tags=["blockchain"])
async def list_networks(_: None = Depends(verify_key)):
    """List configured blockchain networks."""
    try:
        supabase = db.get_db()
        res = supabase.table("blockchain_networks").select("*").order("name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[blockchain] list networks failed: {e}")
        return []


@router.post("/blockchain/networks", tags=["blockchain"])
async def create_network(req: BlockchainNetworkCreate, _: None = Depends(verify_key)):
    """Add a blockchain network."""
    try:
        supabase = db.get_db()
        res = supabase.table("blockchain_networks").insert(req.model_dump()).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"[blockchain] create network failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create network: {str(e)}")


@router.delete("/blockchain/networks/{network_id}", tags=["blockchain"])
async def delete_network(network_id: str, _: None = Depends(verify_key)):
    """Remove a blockchain network."""
    try:
        supabase = db.get_db()
        supabase.table("blockchain_networks").delete().eq("id", network_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"[blockchain] delete network failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete network: {str(e)}")


# ─── Wallet Queries ───────────────────────────────────────────────────────

@router.post("/blockchain/wallet/balance", tags=["blockchain"])
async def get_wallet_balance(req: WalletQuery, _: None = Depends(verify_key)):
    """Get native token balance for a wallet address."""
    try:
        from web3 import Web3
        
        supabase = db.get_db()
        network = supabase.table("blockchain_networks").select("*").eq("id", req.network_id).execute()
        if not network.data:
            raise HTTPException(status_code=404, detail="Network not found")
        
        w3 = Web3(Web3.HTTPProvider(network.data[0]["rpc_url"]))
        
        if not w3.is_connected():
            raise HTTPException(status_code=502, detail="Cannot connect to blockchain node")
        
        checksum_address = w3.to_checksum_address(req.address)
        balance_wei = w3.eth.get_balance(checksum_address)
        balance_eth = w3.from_wei(balance_wei, 'ether')
        
        return {
            "address": req.address,
            "network": network.data[0]["name"],
            "balance": float(balance_eth),
            "balance_wei": str(balance_wei),
            "currency": network.data[0]["native_currency"],
        }
    except ImportError:
        raise HTTPException(status_code=501, detail="Web3.py not installed. Run: pip install web3")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[blockchain] wallet balance failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get balance: {str(e)}")


@router.post("/blockchain/wallet/transactions", tags=["blockchain"])
async def get_wallet_transactions(
    req: WalletQuery,
    limit: int = 20,
    _: None = Depends(verify_key),
):
    """Get recent transactions for a wallet."""
    try:
        from web3 import Web3
        
        supabase = db.get_db()
        network = supabase.table("blockchain_networks").select("*").eq("id", req.network_id).execute()
        if not network.data:
            raise HTTPException(status_code=404, detail="Network not found")
        
        w3 = Web3(Web3.HTTPProvider(network.data[0]["rpc_url"]))
        
        if not w3.is_connected():
            raise HTTPException(status_code=502, detail="Cannot connect to blockchain node")
        
        checksum_address = w3.to_checksum_address(req.address)
        
        # Get latest block
        latest_block = w3.eth.block_number
        
        transactions = []
        # Scan recent blocks for transactions involving this address
        for block_num in range(latest_block, max(latest_block - 100, 0), -1):
            if len(transactions) >= limit:
                break
            
            try:
                block = w3.eth.get_block(block_num, full_transactions=True)
                for tx in block.transactions:
                    if (tx["from"] and tx["from"].lower() == req.address.lower()) or \
                       (tx["to"] and tx["to"].lower() == req.address.lower()):
                        transactions.append({
                            "hash": tx["hash"].hex(),
                            "from": tx["from"],
                            "to": tx["to"],
                            "value": float(w3.from_wei(tx["value"], 'ether')),
                            "block_number": block_num,
                            "gas_price_gwei": float(w3.from_wei(tx["gasPrice"], 'gwei')) if tx.get("gasPrice") else 0,
                            "timestamp": block.timestamp if hasattr(block, 'timestamp') else None,
                        })
            except Exception:
                continue
        
        return {
            "address": req.address,
            "network": network.data[0]["name"],
            "transactions": transactions[:limit],
            "count": len(transactions[:limit]),
        }
    except ImportError:
        raise HTTPException(status_code=501, detail="Web3.py not installed. Run: pip install web3")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[blockchain] wallet transactions failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transactions: {str(e)}")


# ─── Smart Contract Analysis ──────────────────────────────────────────────

@router.post("/blockchain/contract/analyze", tags=["blockchain"])
async def analyze_contract(req: ContractAnalysisRequest, _: None = Depends(verify_key)):
    """Analyze a smart contract: read ABI, check verification, analyze functions."""
    try:
        from web3 import Web3
        
        supabase = db.get_db()
        network = supabase.table("blockchain_networks").select("*").eq("id", req.network_id).execute()
        if not network.data:
            raise HTTPException(status_code=404, detail="Network not found")
        
        net = network.data[0]
        w3 = Web3(Web3.HTTPProvider(net["rpc_url"]))
        
        if not w3.is_connected():
            raise HTTPException(status_code=502, detail="Cannot connect to blockchain node")
        
        checksum_address = w3.to_checksum_address(req.contract_address)
        
        result = {
            "address": req.contract_address,
            "network": net["name"],
            "explorer_url": f"{net.get('explorer_url', '')}/address/{req.contract_address}" if net.get('explorer_url') else None,
        }
        
        # Get contract bytecode (checks if it's a contract)
        bytecode = w3.eth.get_code(checksum_address)
        result["is_contract"] = len(bytecode) > 0 and bytecode != b'0x'
        
        if result["is_contract"]:
            result["bytecode_size"] = len(bytecode)
            
            # Try to get ABI from explorer
            if net.get("explorer_url"):
                try:
                    import httpx
                    explorer_api = net["explorer_url"].rstrip("/")
                    
                    # Etherscan-like API
                    api_key = ""  # Would need to be configured
                    api_url = f"{explorer_api}/api?module=contract&action=getabi&address={checksum_address}"
                    if api_key:
                        api_url += f"&apikey={api_key}"
                    
                    resp = httpx.get(api_url, timeout=10)
                    data = resp.json()
                    
                    if data.get("status") == "1" and data.get("result"):
                        result["abi"] = json.loads(data["result"])
                        result["verified"] = True
                        
                        # Analyze functions
                        functions = []
                        for item in result["abi"]:
                            if item.get("type") == "function":
                                functions.append({
                                    "name": item.get("name", "unknown"),
                                    "inputs": [{"name": i.get("name"), "type": i.get("type")} for i in item.get("inputs", [])],
                                    "outputs": [{"name": o.get("name"), "type": o.get("type")} for o in item.get("outputs", [])],
                                    "state_mutability": item.get("stateMutability", "nonpayable"),
                                })
                        result["functions"] = functions
                        result["function_count"] = len(functions)
                except Exception as e:
                    logger.warning(f"[blockchain] Explorer lookup failed: {e}")
                    result["verified"] = False
        
        return result
    
    except ImportError:
        raise HTTPException(status_code=501, detail="Web3.py not installed. Run: pip install web3")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[blockchain] contract analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze contract: {str(e)}")


# ─── DeFi Monitoring ──────────────────────────────────────────────────────

@router.post("/blockchain/defi/positions", tags=["blockchain"])
async def get_defi_positions(req: DeFiPositionQuery, _: None = Depends(verify_key)):
    """Get DeFi positions for a wallet (simplified — uses The Graph or direct RPC)."""
    try:
        from web3 import Web3
        
        supabase = db.get_db()
        
        # Get all active networks
        networks = supabase.table("blockchain_networks").select("*").eq("is_active", True).execute()
        
        positions = []
        
        for net in (networks.data or []):
            try:
                w3 = Web3(Web3.HTTPProvider(net["rpc_url"]))
                if not w3.is_connected():
                    continue
                
                checksum_address = w3.to_checksum_address(req.wallet_address)
                
                # Get native balance
                balance_wei = w3.eth.get_balance(checksum_address)
                balance = float(w3.from_wei(balance_wei, 'ether'))
                
                if balance > 0:
                    positions.append({
                        "network": net["name"],
                        "protocol": "native",
                        "asset": net["native_currency"],
                        "balance": balance,
                        "usd_value": None,  # Would need price oracle
                    })
            except Exception:
                continue
        
        return {
            "wallet": req.wallet_address,
            "positions": positions,
            "total_positions": len(positions),
        }
    
    except ImportError:
        raise HTTPException(status_code=501, detail="Web3.py not installed. Run: pip install web3")
    except Exception as e:
        logger.error(f"[blockchain] DeFi positions failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get DeFi positions: {str(e)}")


# ─── NFT Analysis ─────────────────────────────────────────────────────────

@router.post("/blockchain/nft/balance", tags=["blockchain"])
async def get_nft_balance(req: WalletQuery, _: None = Depends(verify_key)):
    """Get NFT balance for a wallet (ERC-721)."""
    try:
        from web3 import Web3
        
        supabase = db.get_db()
        network = supabase.table("blockchain_networks").select("*").eq("id", req.network_id).execute()
        if not network.data:
            raise HTTPException(status_code=404, detail="Network not found")
        
        w3 = Web3(Web3.HTTPProvider(network.data[0]["rpc_url"]))
        
        if not w3.is_connected():
            raise HTTPException(status_code=502, detail="Cannot connect to blockchain node")
        
        checksum_address = w3.to_checksum_address(req.address)
        
        # ERC-721 ABI for balanceOf
        erc721_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "tokensOfOwner",
                "outputs": [{"name": "tokens", "type": "uint256[]"}],
                "type": "function",
            },
        ]
        
        # This is a simplified check — would need to iterate over known NFT contracts
        return {
            "address": req.address,
            "network": network.data[0]["name"],
            "note": "Full NFT analysis requires iterating over known contracts. Use a dedicated NFT API for production.",
        }
    
    except ImportError:
        raise HTTPException(status_code=501, detail="Web3.py not installed. Run: pip install web3")
    except Exception as e:
        logger.error(f"[blockchain] NFT balance failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get NFT balance: {str(e)}")


# ─── Web3 Security ────────────────────────────────────────────────────────

@router.post("/blockchain/security/scan-contract", tags=["blockchain"])
async def scan_contract_security(
    req: ContractAnalysisRequest,
    _: None = Depends(verify_key),
):
    """Basic security scan of a smart contract."""
    try:
        from web3 import Web3
        
        supabase = db.get_db()
        network = supabase.table("blockchain_networks").select("*").eq("id", req.network_id).execute()
        if not network.data:
            raise HTTPException(status_code=404, detail="Network not found")
        
        w3 = Web3(Web3.HTTPProvider(network.data[0]["rpc_url"]))
        
        if not w3.is_connected():
            raise HTTPException(status_code=502, detail="Cannot connect to blockchain node")
        
        checksum_address = w3.to_checksum_address(req.contract_address)
        
        findings = []
        
        # Check 1: Is it a contract?
        bytecode = w3.eth.get_code(checksum_address)
        if len(bytecode) <= 2:
            findings.append({
                "severity": "critical",
                "title": "Not a contract",
                "description": "The address does not contain any contract code.",
            })
            return {"address": req.contract_address, "findings": findings, "risk_score": 10}
        
        # Check 2: Bytecode size (indicator of complexity)
        bytecode_size = len(bytecode)
        if bytecode_size > 24576:  # Near the max contract size
            findings.append({
                "severity": "medium",
                "title": "Large contract size",
                "description": f"Contract bytecode is {bytecode_size} bytes, approaching the 24KB limit. May indicate complex or bloated code.",
            })
        
        # Check 3: Try to get ABI and analyze functions
        if network.data[0].get("explorer_url"):
            try:
                import httpx
                explorer_api = network.data[0]["explorer_url"].rstrip("/")
                api_url = f"{explorer_api}/api?module=contract&action=getabi&address={checksum_address}"
                
                resp = httpx.get(api_url, timeout=10)
                data = resp.json()
                
                if data.get("status") == "1" and data.get("result"):
                    abi = json.loads(data["result"])
                    
                    # Check for dangerous functions
                    dangerous_patterns = ["selfdestruct", "suicide", "delegatecall", "callcode"]
                    for item in abi:
                        if item.get("type") == "function":
                            name = item.get("name", "").lower()
                            for pattern in dangerous_patterns:
                                if pattern in name:
                                    findings.append({
                                        "severity": "high",
                                        "title": f"Dangerous function: {item['name']}",
                                        "description": f"Contract contains '{item['name']}' which uses {pattern}. This can destroy the contract or execute arbitrary code.",
                                    })
                    
                    # Check for payable functions
                    payable_count = sum(1 for item in abi if item.get("type") == "function" and item.get("stateMutability") == "payable")
                    if payable_count > 5:
                        findings.append({
                            "severity": "low",
                            "title": "Many payable functions",
                            "description": f"Contract has {payable_count} payable functions. Ensure proper access controls are in place.",
                        })
            except Exception:
                pass
        
        # Calculate risk score
        severity_weights = {"critical": 10, "high": 7, "medium": 4, "low": 1}
        risk_score = min(sum(severity_weights.get(f["severity"], 0) for f in findings), 10)
        
        return {
            "address": req.contract_address,
            "network": network.data[0]["name"],
            "findings": findings,
            "risk_score": risk_score,
            "finding_count": len(findings),
        }
    
    except ImportError:
        raise HTTPException(status_code=501, detail="Web3.py not installed. Run: pip install web3")
    except Exception as e:
        logger.error(f"[blockchain] security scan failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to scan contract: {str(e)}")
