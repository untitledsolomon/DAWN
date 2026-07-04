"""
OSINT tool — reconnaissance and open-source intelligence gathering.
Integrates with Shodan, WHOIS, DNS, certificate transparency, and more.
"""
import asyncio
import json
import logging
from typing import Optional
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class OSINTTool(BaseTool):
    name = "osint"
    description = (
        "Open-source intelligence gathering. Perform reconnaissance on domains, "
        "IPs, emails, and usernames. Supports: whois, dns, shodan, certificate "
        "transparency (crt.sh), email verification, and social media discovery."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "whois", "dns_lookup", "shodan", "certificate_search",
                    "email_verify", "username_search", "ip_geolocation",
                    "dns_enum", "subdomain_enum", "full_recon"
                ],
                "description": "The OSINT operation to perform.",
            },
            "target": {
                "type": "string",
                "description": "The target domain, IP, email, or username.",
            },
            "store_results": {
                "type": "boolean",
                "description": "Store results in the database (default: true).",
            },
        },
        "required": ["operation", "target"],
    }

    async def run(
        self,
        operation: str,
        target: str,
        store_results: bool = True,
    ) -> ToolResult:
        if not target or len(target) > 500:
            return ToolResult(success=False, error="Invalid target")

        try:
            if operation == "whois":
                result = await self._whois_lookup(target)
            elif operation == "dns_lookup":
                result = await self._dns_lookup(target)
            elif operation == "shodan":
                result = await self._shodan_lookup(target)
            elif operation == "certificate_search":
                result = await self._certificate_search(target)
            elif operation == "email_verify":
                result = await self._email_verify(target)
            elif operation == "username_search":
                result = await self._username_search(target)
            elif operation == "ip_geolocation":
                result = await self._ip_geolocation(target)
            elif operation == "dns_enum":
                result = await self._dns_enumeration(target)
            elif operation == "subdomain_enum":
                result = await self._subdomain_enumeration(target)
            elif operation == "full_recon":
                result = await self._full_recon(target)
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")

            if store_results and result.get("success"):
                await self._store_results(operation, target, result)

            return ToolResult(
                success=result.get("success", False),
                output=result.get("data", {}),
                error=result.get("error"),
            )
        except Exception as e:
            logger.exception(f"OSINT {operation} failed: {e}")
            return ToolResult(success=False, error=f"OSINT {operation} failed: {e}")

    async def _whois_lookup(self, target: str) -> dict:
        """WHOIS lookup for domain registration info."""
        try:
            import subprocess
            proc = await asyncio.create_subprocess_exec(
                "whois", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            except asyncio.TimeoutError:
                proc.kill()
                return {"success": False, "error": "WHOIS lookup timed out"}

            text = stdout.decode(errors="replace")
            
            # Parse key fields
            import re
            data = {
                "raw": text[:5000],
                "registrar": self._extract_whois_field(text, "Registrar:"),
                "creation_date": self._extract_whois_field(text, "Creation Date:"),
                "expiry_date": self._extract_whois_field(text, "Registry Expiry Date:"),
                "name_servers": re.findall(r'Name Server:\s*(\S+)', text),
                "status": re.findall(r'Domain Status:\s*(.+)$', text, re.MULTILINE),
            }
            return {"success": True, "data": data}
        except FileNotFoundError:
            return {"success": False, "error": "whois command not found. Install: apt install whois"}

    async def _dns_lookup(self, target: str) -> dict:
        """DNS record lookup."""
        import subprocess
        record_types = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]
        results = {}
        
        for rtype in record_types:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "dig", "+short", target, rtype,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                records = stdout.decode(errors="replace").strip().split("\n")
                records = [r.strip() for r in records if r.strip()]
                if records:
                    results[rtype] = records
            except (asyncio.TimeoutError, FileNotFoundError):
                continue
        
        return {"success": True, "data": results}

    async def _shodan_lookup(self, target: str) -> dict:
        """Shodan API lookup."""
        from config import settings
        api_key = getattr(settings, "shodan_api_key", None)
        if not api_key:
            return {"success": False, "error": "Shodan API key not configured"}
        
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                # Determine if target is IP or domain
                import re
                if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', target):
                    # IP lookup
                    resp = await client.get(
                        f"https://api.shodan.io/shodan/host/{target}",
                        params={"key": api_key}
                    )
                else:
                    # Domain lookup
                    resp = await client.get(
                        f"https://api.shodan.io/dns/resolve",
                        params={"hostnames": target, "key": api_key}
                    )
                
                if resp.status_code == 200:
                    return {"success": True, "data": resp.json()}
                else:
                    return {"success": False, "error": f"Shodan API error: {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Shodan lookup failed: {e}"}

    async def _certificate_search(self, target: str) -> dict:
        """Certificate Transparency log search via crt.sh."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    f"https://crt.sh/?q={target}&output=json",
                    headers={"User-Agent": "DAWN-OSINT/1.0"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Deduplicate and summarize
                    seen = set()
                    certs = []
                    for entry in (data or [])[:50]:
                        name = entry.get("name_value", "")
                        if name not in seen:
                            seen.add(name)
                            certs.append({
                                "name": name,
                                "issuer": entry.get("issuer_name", ""),
                                "not_before": entry.get("not_before", ""),
                                "not_after": entry.get("not_after", ""),
                            })
                    return {"success": True, "data": {"certificates": certs, "count": len(certs)}}
                return {"success": False, "error": f"crt.sh error: {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Certificate search failed: {e}"}

    async def _email_verify(self, target: str) -> dict:
        """Basic email verification."""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        valid_format = bool(re.match(pattern, target))
        
        if not valid_format:
            return {"success": True, "data": {"email": target, "valid_format": False}}
        
        # Extract domain and check MX records
        domain = target.split("@")[1]
        dns_result = await self._dns_lookup(domain)
        has_mx = "MX" in dns_result.get("data", {})
        
        return {
            "success": True,
            "data": {
                "email": target,
                "valid_format": True,
                "domain": domain,
                "has_mx_records": has_mx,
            }
        }

    async def _username_search(self, target: str) -> dict:
        """Search for username across platforms (simulated — real Sherlock integration needs local install)."""
        platforms = [
            "github", "twitter", "reddit", "hackernews", "keybase",
            "medium", "dev.to", "stackoverflow", "linkedin",
        ]
        
        # Check if sherlock is installed
        import shutil
        has_sherlock = shutil.which("sherlock") is not None
        
        if has_sherlock:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "sherlock", target, "--output", "/dev/null",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
                output = stdout.decode(errors="replace")
                
                found = []
                for line in output.split("\n"):
                    if "[+]" in line:
                        parts = line.split("[+]")[1].strip()
                        if ":" in parts:
                            platform, url = parts.split(":", 1)
                            found.append({"platform": platform.strip(), "url": url.strip()})
                
                return {"success": True, "data": {"username": target, "platforms_found": found, "count": len(found)}}
            except (asyncio.TimeoutError, FileNotFoundError):
                pass
        
        # Fallback: return known platforms to check manually
        return {
            "success": True,
            "data": {
                "username": target,
                "note": "Sherlock not installed. Install with: pip install sherlock",
                "platforms_to_check": platforms,
            }
        }

    async def _ip_geolocation(self, target: str) -> dict:
        """IP geolocation via ip-api.com."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"http://ip-api.com/json/{target}")
                if resp.status_code == 200:
                    data = resp.json()
                    return {"success": True, "data": data}
                return {"success": False, "error": f"IP geolocation error: {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"IP geolocation failed: {e}"}

    async def _dns_enumeration(self, target: str) -> dict:
        """DNS enumeration — attempt zone transfer and common record discovery."""
        import subprocess
        results = {"records": {}, "zone_transfer": None}
        
        # Get NS records first
        try:
            proc = await asyncio.create_subprocess_exec(
                "dig", "+short", "NS", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            ns_servers = [l.strip() for l in stdout.decode(errors="replace").split("\n") if l.strip()]
            results["records"]["NS"] = ns_servers
            
            # Attempt zone transfer on each NS
            for ns in ns_servers[:3]:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "dig", "AXFR", target, f"@{ns}",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
                    output = stdout.decode(errors="replace")
                    if "Transfer failed" not in output and "AXFR" in output:
                        results["zone_transfer"] = {
                            "server": ns,
                            "success": True,
                            "records": output[:5000],
                        }
                        break
                except (asyncio.TimeoutError, FileNotFoundError):
                    continue
        except (asyncio.TimeoutError, FileNotFoundError):
            pass
        
        return {"success": True, "data": results}

    async def _subdomain_enumeration(self, target: str) -> dict:
        """Subdomain enumeration via common wordlist and certificate transparency."""
        import httpx
        
        subdomains = set()
        
        # Try crt.sh for certificate-based subdomain discovery
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    f"https://crt.sh/?q=%25.{target}&output=json",
                    headers={"User-Agent": "DAWN-OSINT/1.0"}
                )
                if resp.status_code == 200:
                    for entry in (resp.json() or []):
                        name = entry.get("name_value", "")
                        for n in name.split("\n"):
                            n = n.strip()
                            if n.endswith(f".{target}") or n == target:
                                subdomains.add(n)
        except Exception:
            pass
        
        return {
            "success": True,
            "data": {
                "domain": target,
                "subdomains": sorted(subdomains)[:100],
                "count": len(subdomains),
            }
        }

    async def _full_recon(self, target: str) -> dict:
        """Run multiple OSINT operations and aggregate results."""
        operations = [
            ("whois", self._whois_lookup),
            ("dns", self._dns_lookup),
            ("certificates", self._certificate_search),
            ("subdomains", self._subdomain_enumeration),
        ]
        
        results = {}
        for name, func in operations:
            try:
                result = await func(target)
                results[name] = result.get("data", {}) if result.get("success") else {"error": result.get("error")}
            except Exception as e:
                results[name] = {"error": str(e)}
        
        return {"success": True, "data": results}

    def _extract_whois_field(self, text: str, field: str) -> Optional[str]:
        """Extract a field from WHOIS text output."""
        import re
        match = re.search(rf'^{field}\s*(.+)$', text, re.MULTILINE)
        return match.group(1).strip() if match else None

    async def _store_results(self, operation: str, target: str, result: dict):
        """Store OSINT results in the database."""
        try:
            import db.client as db
            supabase = db.get_db()
            
            # Find or create target
            target_type = "domain"
            if any(c.isdigit() for c in target.replace(".", "")):
                if target.count(".") == 3 and all(p.isdigit() for p in target.split(".") if p):
                    target_type = "ip"
            if "@" in target:
                target_type = "email"
            
            t_res = supabase.table("osint_targets").select("id").eq("target_type", target_type).eq("value", target).execute()
            if t_res.data:
                target_id = t_res.data[0]["id"]
            else:
                t_res = supabase.table("osint_targets").insert({
                    "target_type": target_type,
                    "value": target,
                    "label": f"Auto-OSINT: {target}",
                }).execute()
                target_id = t_res.data[0]["id"] if t_res.data else None
            
            if target_id:
                supabase.table("osint_scan_results").insert({
                    "target_id": target_id,
                    "scan_type": operation,
                    "raw_data": json.dumps(result.get("data", {})),
                    "findings_count": len(json.dumps(result.get("data", {}))),
                }).execute()
        except Exception as e:
            logger.warning(f"Failed to store OSINT results: {e}")
