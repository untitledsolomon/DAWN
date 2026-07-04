"""
Nmap integration tool — port scanning, service detection, OS fingerprinting.
Requires nmap installed on the host system.
"""
import asyncio
import json
import logging
import shlex
from typing import Optional
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

SCAN_PROFILES = {
    "quick": {
        "args": ["-T4", "-F", "--open"],
        "description": "Quick scan of top 100 ports",
    },
    "full": {
        "args": ["-T4", "-p-", "--open"],
        "description": "Full scan of all 65535 ports",
    },
    "service": {
        "args": ["-T4", "-sV", "--open"],
        "description": "Service version detection on common ports",
    },
    "vulnerability": {
        "args": ["-T4", "-sV", "--script", "vuln"],
        "description": "Vulnerability scan with NSE scripts",
    },
    "os_detection": {
        "args": ["-T4", "-O", "--osscan-guess"],
        "description": "OS fingerprinting",
    },
    "compliance": {
        "args": ["-T4", "-sV", "-sC", "--open"],
        "description": "Compliance-oriented scan with default scripts",
    },
}


class NmapTool(BaseTool):
    name = "nmap"
    description = (
        "Port scanning, service detection, OS fingerprinting, and NSE script execution. "
        "Use pre-built scan profiles or specify custom arguments. "
        "All scans are logged for audit. Requires authorization for production targets."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Target IP, hostname, CIDR range, or URL.",
            },
            "profile": {
                "type": "string",
                "enum": list(SCAN_PROFILES.keys()),
                "description": "Pre-built scan profile.",
            },
            "custom_args": {
                "type": "string",
                "description": "Custom Nmap arguments (overrides profile if set).",
            },
            "ports": {
                "type": "string",
                "description": "Port specification e.g. '80,443' or '1-1000'.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Max scan duration in seconds (default: 300).",
            },
            "store_results": {
                "type": "boolean",
                "description": "Store results in the database (default: true).",
            },
        },
        "required": ["target"],
    }

    async def run(
        self,
        target: str,
        profile: str = "quick",
        custom_args: Optional[str] = None,
        ports: Optional[str] = None,
        timeout_seconds: int = 300,
        store_results: bool = True,
    ) -> ToolResult:
        # Validate target format
        if not target or len(target) > 500:
            return ToolResult(success=False, error="Invalid target")

        # Build args
        if custom_args:
            try:
                args = shlex.split(custom_args)
            except ValueError as e:
                return ToolResult(success=False, error=f"Invalid custom args: {e}")
        else:
            profile_config = SCAN_PROFILES.get(profile)
            if not profile_config:
                return ToolResult(
                    success=False,
                    error=f"Unknown profile '{profile}'. Available: {', '.join(SCAN_PROFILES.keys())}"
                )
            args = list(profile_config["args"])

        if ports:
            args.extend(["-p", ports])

        # Add target
        args.append(target)

        # Add XML output for parsing
        args.extend(["-oX", "-"])

        timeout = min(max(10, timeout_seconds), 600)

        try:
            proc = await asyncio.create_subprocess_exec(
                "nmap", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                error="nmap is not installed. Install it with: apt install nmap"
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to start nmap: {e}")

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(success=False, error=f"Scan timed out after {timeout}s")

        stdout_text = stdout.decode(errors="replace")
        stderr_text = stderr.decode(errors="replace")

        if proc.returncode != 0 and proc.returncode != 1:
            # Return code 1 means "no open ports" — not an error
            return ToolResult(
                success=False,
                error=f"nmap exited with code {proc.returncode}: {stderr_text[:2000]}"
            )

        # Parse XML output for structured results
        parsed = self._parse_nmap_xml(stdout_text)

        result = {
            "target": target,
            "profile": profile,
            "command": f"nmap {' '.join(args)}",
            "ports_found": len(parsed.get("ports", [])),
            "open_ports": parsed.get("ports", []),
            "os_detection": parsed.get("os", {}),
            "host_status": parsed.get("host_status", "unknown"),
            "raw_output": stdout_text[:10000],
        }

        # Store in database if requested
        if store_results:
            try:
                await self._store_results(target, profile, result)
            except Exception as e:
                logger.warning(f"Failed to store scan results: {e}")

        return ToolResult(success=True, output=result)

    def _parse_nmap_xml(self, xml_text: str) -> dict:
        """Basic XML parsing for nmap output."""
        import re
        
        result = {"ports": [], "os": {}}
        
        # Parse host status
        status_match = re.search(r'<status state="(\w+)"', xml_text)
        if status_match:
            result["host_status"] = status_match.group(1)
        
        # Parse ports
        port_pattern = re.compile(
            r'<port protocol="(\w+)" portid="(\d+)">.*?'
            r'<state state="(\w+)".*?/>.*?'
            r'<service name="([^"]*)"(?: product="([^"]*)")?(?: version="([^"]*)")?',
            re.DOTALL
        )
        for match in port_pattern.finditer(xml_text):
            port_info = {
                "port": int(match.group(2)),
                "protocol": match.group(1),
                "state": match.group(3),
                "service": match.group(4) or "unknown",
                "product": match.group(5) or "",
                "version": match.group(6) or "",
            }
            result["ports"].append(port_info)
        
        # Parse OS detection
        os_match = re.search(r'<osmatch name="([^"]*)"', xml_text)
        if os_match:
            result["os"] = {"name": os_match.group(1)}
            accuracy = re.search(r'accuracy="(\d+)"', xml_text)
            if accuracy:
                result["os"]["accuracy"] = int(accuracy.group(1))
        
        return result

    async def _store_results(self, target: str, profile: str, result: dict):
        """Store scan results in the database."""
        try:
            import db.client as db
            supabase = db.get_db()
            
            # Find or create target
            target_res = supabase.table("pentest_targets").select("id").eq("target", target).execute()
            if target_res.data:
                target_id = target_res.data[0]["id"]
            else:
                target_res = supabase.table("pentest_targets").insert({
                    "target": target,
                    "target_type": "ip" if target.replace(".", "").isdigit() else "domain",
                    "label": f"Auto-scanned: {target}",
                    "authorized": False,
                }).execute()
                target_id = target_res.data[0]["id"] if target_res.data else None
            
            if target_id:
                supabase.table("nmap_scan_results").insert({
                    "target_id": target_id,
                    "scan_profile": profile,
                    "target_host": target,
                    "ports_found": result["ports_found"],
                    "open_ports": json.dumps(result["open_ports"]),
                    "os_detection": json.dumps(result["os_detection"]),
                    "raw_output": result["raw_output"][:50000],
                }).execute()
        except Exception as e:
            logger.warning(f"Failed to store nmap results: {e}")
