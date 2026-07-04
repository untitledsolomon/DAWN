"""
SSH tool — connect to remote machines via SSH key or password.
Stores credentials encrypted at rest in the ssh_hosts table.
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional
from tools.base import BaseTool, ToolResult
from config import settings

logger = logging.getLogger(__name__)

# Try to import paramiko — it's an optional dependency
try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False
    logger.warning("paramiko not installed — SSH tool will be unavailable")


class SSHTool(BaseTool):
    name = "ssh"
    description = (
        "Connect to remote machines via SSH to run commands, transfer files, "
        "and manage servers. Supports key-based and password authentication. "
        "Hosts must be pre-configured in the host inventory. "
        "Use 'ssh_execute' to run commands, 'ssh_upload'/'ssh_download' for file transfer."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["execute", "upload", "download", "list_hosts", "connect_test"],
                "description": "The SSH operation to perform.",
            },
            "host_id": {
                "type": "string",
                "description": "ID of the pre-configured host in ssh_hosts table.",
            },
            "hostname": {
                "type": "string",
                "description": "Hostname or IP (used if host_id not provided).",
            },
            "port": {
                "type": "integer",
                "description": "SSH port (default: 22).",
            },
            "username": {
                "type": "string",
                "description": "SSH username.",
            },
            "command": {
                "type": "string",
                "description": "Command to execute on the remote host.",
            },
            "remote_path": {
                "type": "string",
                "description": "Remote file path for upload/download.",
            },
            "local_path": {
                "type": "string",
                "description": "Local file path for upload/download.",
            },
            "content": {
                "type": "string",
                "description": "File content to upload (instead of local_path).",
            },
            "timeout": {
                "type": "integer",
                "description": "Command timeout in seconds (default: 30).",
            },
        },
        "required": ["operation"],
    }

    def __init__(self):
        self.sandbox_root = Path(getattr(settings, "filesystem_sandbox_root", "./sandbox")).resolve()
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        operation: str,
        host_id: Optional[str] = None,
        hostname: Optional[str] = None,
        port: int = 22,
        username: Optional[str] = None,
        command: Optional[str] = None,
        remote_path: Optional[str] = None,
        local_path: Optional[str] = None,
        content: Optional[str] = None,
        timeout: int = 30,
    ) -> ToolResult:
        if not HAS_PARAMIKO:
            return ToolResult(
                success=False,
                error="paramiko is not installed. Run: pip install paramiko"
            )

        try:
            if operation == "list_hosts":
                return await self._list_hosts()
            
            # Resolve connection details
            ssh_config = await self._resolve_host(host_id, hostname, port, username)
            if not ssh_config:
                return ToolResult(
                    success=False,
                    error="No host specified. Provide host_id or hostname/username."
                )

            if operation == "connect_test":
                return await self._connect_test(ssh_config)
            elif operation == "execute":
                if not command:
                    return ToolResult(success=False, error="command is required for execute")
                return await self._execute(ssh_config, command, timeout)
            elif operation == "upload":
                return await self._upload(ssh_config, local_path, remote_path, content)
            elif operation == "download":
                return await self._download(ssh_config, remote_path, local_path)
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            logger.exception(f"SSH operation failed: {e}")
            return ToolResult(success=False, error=f"SSH operation failed: {e}")

    async def _resolve_host(self, host_id, hostname, port, username):
        """Resolve connection details from DB or direct params."""
        if host_id:
            try:
                import db.client as db
                supabase = db.get_db()
                res = supabase.table("ssh_hosts").select("*").eq("id", host_id).execute()
                if res.data:
                    host = res.data[0]
                    return {
                        "hostname": host["hostname"],
                        "port": host.get("port", 22),
                        "username": host.get("username", "root"),
                        "auth_method": host.get("auth_method", "key"),
                        "encrypted_key": host.get("encrypted_key"),
                        "encrypted_password": host.get("encrypted_password"),
                    }
            except Exception as e:
                logger.warning(f"Failed to look up host {host_id}: {e}")

        if hostname and username:
            return {
                "hostname": hostname,
                "port": port or 22,
                "username": username,
                "auth_method": "password",
                "encrypted_password": None,
                "encrypted_key": None,
            }
        return None

    def _connect(self, config: dict, timeout: int = 10):
        """Establish SSH connection."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        hostname = config["hostname"]
        port = config.get("port", 22)
        username = config.get("username", "root")
        
        if config.get("auth_method") == "key" and config.get("encrypted_key"):
            from io import StringIO
            key_file = StringIO(config["encrypted_key"])
            try:
                pkey = paramiko.RSAKey.from_private_key(key_file)
            except paramiko.SSHException:
                try:
                    pkey = paramiko.Ed25519Key.from_private_key(key_file)
                except paramiko.SSHException:
                    return None, "Failed to parse SSH key"
            client.connect(hostname, port=port, username=username, pkey=pkey, timeout=timeout)
        else:
            password = config.get("encrypted_password")
            client.connect(hostname, port=port, username=username, password=password, timeout=timeout)
        
        return client, None

    async def _connect_test(self, config):
        """Test SSH connectivity."""
        loop = asyncio.get_event_loop()
        client, error = await loop.run_in_executor(None, self._connect, config, 10)
        if error:
            return ToolResult(success=False, error=error)
        client.close()
        return ToolResult(success=True, output={"status": "connected", "hostname": config["hostname"]})

    async def _execute(self, config, command: str, timeout: int = 30):
        """Execute a command on the remote host."""
        loop = asyncio.get_event_loop()
        
        def _run():
            client, error = self._connect(config, min(timeout, 10))
            if error:
                return {"success": False, "error": error}
            try:
                _, stdout, stderr = client.exec_command(command, timeout=timeout)
                exit_code = stdout.channel.recv_exit_status()
                out = stdout.read().decode(errors="replace")[:50000]
                err = stderr.read().decode(errors="replace")[:10000]
                return {
                    "success": exit_code == 0,
                    "output": out,
                    "error_output": err,
                    "exit_code": exit_code,
                }
            finally:
                client.close()
        
        result = await loop.run_in_executor(None, _run)
        if "error" in result:
            return ToolResult(success=False, error=result["error"])
        return ToolResult(
            success=result["success"],
            output={
                "stdout": result.get("output", ""),
                "stderr": result.get("error_output", ""),
                "exit_code": result.get("exit_code", -1),
            },
            error=None if result["success"] else f"Exit code: {result.get('exit_code')}"
        )

    async def _upload(self, config, local_path, remote_path, content):
        """Upload a file via SFTP."""
        if not remote_path:
            return ToolResult(success=False, error="remote_path is required")
        
        loop = asyncio.get_event_loop()
        
        def _run():
            client, error = self._connect(config)
            if error:
                return {"error": error}
            try:
                sftp = client.open_sftp()
                if content:
                    with sftp.open(remote_path, "w") as f:
                        f.write(content)
                elif local_path:
                    local = self.sandbox_root / local_path
                    if not local.exists():
                        return {"error": f"Local file not found: {local_path}"}
                    sftp.put(str(local), remote_path)
                else:
                    return {"error": "Provide content or local_path"}
                sftp.close()
                return {"success": True, "output": f"Uploaded to {remote_path}"}
            finally:
                client.close()
        
        result = await loop.run_in_executor(None, _run)
        if "error" in result:
            return ToolResult(success=False, error=result["error"])
        return ToolResult(success=True, output=result["output"])

    async def _download(self, config, remote_path, local_path):
        """Download a file via SFTP."""
        if not remote_path:
            return ToolResult(success=False, error="remote_path is required")
        if not local_path:
            local_path = Path(remote_path).name
        
        loop = asyncio.get_event_loop()
        
        def _run():
            client, error = self._connect(config)
            if error:
                return {"error": error}
            try:
                sftp = client.open_sftp()
                local = self.sandbox_root / local_path
                local.parent.mkdir(parents=True, exist_ok=True)
                sftp.get(remote_path, str(local))
                sftp.close()
                content = local.read_text(encoding="utf-8", errors="replace")
                return {"success": True, "output": content, "local_path": str(local.relative_to(self.sandbox_root))}
            finally:
                client.close()
        
        result = await loop.run_in_executor(None, _run)
        if "error" in result:
            return ToolResult(success=False, error=result["error"])
        return ToolResult(success=True, output=result)

    async def _list_hosts(self):
        """List configured SSH hosts."""
        try:
            import db.client as db
            supabase = db.get_db()
            res = supabase.table("ssh_hosts").select("id, label, hostname, port, username, tags, last_connected_at, is_active").eq("is_active", True).execute()
            return ToolResult(success=True, output=res.data or [])
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list hosts: {e}")
