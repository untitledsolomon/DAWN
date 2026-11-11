"""
Runtime settings store. Precedence: DB override, then environment/config, then
registry default. Reads are synchronous and cached in memory — the agent loop
reads settings constantly and must never wait on the database.

If the database is unreachable the store keeps the last-known-good values; it
never silently reverts to defaults mid-run. llm.* changes trigger a hook that
resets the engine singleton.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from config import settings
from runtime_settings.registry import SETTING_DEFS, SettingDef

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 15


def _rpc_set_runtime_setting(p_key: str, p_value: Any, p_by: str, p_reason: str) -> None:
    import db.client as db
    supabase = db.get_db()
    supabase.rpc(
        "set_runtime_setting",
        {"p_key": p_key, "p_value": p_value, "p_by": p_by, "p_reason": p_reason},
    ).execute()


class RuntimeSettingsStore:
    def __init__(self) -> None:
        self._overrides: dict[str, Any] = {}
        self._hooks: dict[str, list[Callable[[str], None]]] = {}
        self._refresh_task: Optional[asyncio.Task] = None

    # ── resolution ────────────────────────────────────────────────────────
    def _env_value(self, d: SettingDef) -> tuple[Any, bool]:
        if d.env:
            v = getattr(settings, d.env, None)
            if v is not None:
                return v, True
        return None, False

    def get(self, key: str) -> Any:
        d = SETTING_DEFS.get(key)
        if d is None:
            return None
        if key in self._overrides:
            return self._overrides[key]
        env_val, has_env = self._env_value(d)
        if has_env:
            return env_val
        return d.default

    def get_def(self, key: str) -> Optional[SettingDef]:
        return SETTING_DEFS.get(key)

    def snapshot(self, prefix: str = "") -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in SETTING_DEFS:
            if key.startswith(prefix):
                out[key] = self.get(key)
        return out

    # ── validation ────────────────────────────────────────────────────────
    def validate(self, key: str, value: Any) -> Optional[str]:
        """Return an error string, or None when value is valid for `key`."""
        d = SETTING_DEFS.get(key)
        if d is None:
            return "unknown setting"
        t = d.type
        if value is None:
            if t in ("nullable_float",):
                return None
            return "null is not a valid value; call reset instead"
        if t == "bool":
            if not isinstance(value, bool):
                return "expected a boolean"
        elif t in ("int",):
            if isinstance(value, bool) or not isinstance(value, int):
                return "expected an integer"
            if d.min is not None and value < d.min:
                return f"must be >= {d.min}"
            if d.max is not None and value > d.max:
                return f"must be <= {d.max}"
        elif t in ("float", "nullable_float"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return "expected a number"
            if d.min is not None and value < d.min:
                return f"must be >= {d.min}"
            if d.max is not None and value > d.max:
                return f"must be <= {d.max}"
        elif t == "str":
            if not isinstance(value, str):
                return "expected a string"
        elif t == "enum":
            if value not in d.choices:
                return f"must be one of: {', '.join(d.choices)}"
        elif t == "list[str]":
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                return "expected a list of strings"
        return None

    # ── write path ────────────────────────────────────────────────────────
    async def set(self, key: str, value: Any, by: str = "api", reason: Optional[str] = None) -> Optional[str]:
        """Validate and persist an override. Returns an error message, or None."""
        err = self.validate(key, value)
        if err is not None:
            return err
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, _rpc_set_runtime_setting, key, value, by, reason or "")
        except Exception as e:
            logger.error(f"[runtime-settings] set {key} failed: {e}")
            return f"database write failed: {e}"
        self._overrides[key] = value
        self._fire(key)
        return None

    async def reset(self, key: str, by: str = "api") -> Optional[str]:
        if key not in SETTING_DEFS:
            return "unknown setting"
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, _rpc_set_runtime_setting, key, None, by, "reset to default"
            )
        except Exception as e:
            logger.error(f"[runtime-settings] reset {key} failed: {e}")
            return f"database write failed: {e}"
        self._overrides.pop(key, None)
        self._fire(key)
        return None

    # ── history ───────────────────────────────────────────────────────────
    def history(self, key: str, limit: int = 50) -> list[dict]:
        import db.client as db
        try:
            supabase = db.get_db()
            res = supabase.table("runtime_settings_history").select(
                "old_value, new_value, changed_by, reason, changed_at"
            ).eq("key", key).order("changed_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"[runtime-settings] history {key} failed: {e}")
            return []

    # ── hooks ─────────────────────────────────────────────────────────────
    def on_change(self, prefix: str, callback: Callable[[str], None]) -> None:
        self._hooks.setdefault(prefix, []).append(callback)

    def _fire(self, key: str) -> None:
        for prefix, cbs in self._hooks.items():
            if key.startswith(prefix):
                for cb in cbs:
                    try:
                        cb(key)
                    except Exception:
                        logger.exception(f"[runtime-settings] hook failed for {key}")

    # ── refresh ───────────────────────────────────────────────────────────
    async def refresh(self) -> None:
        """Reload overrides from the database. On failure keep last-known-good."""
        import db.client as db
        try:
            supabase = db.get_db()
            res = await db._async_execute(
                lambda: supabase.table("runtime_settings").select("key, value").execute()
            )
            overrides: dict[str, Any] = {}
            for row in res.data or []:
                key = row.get("key")
                if key in SETTING_DEFS:
                    overrides[key] = row.get("value")
            self._overrides = overrides
            logger.debug(f"[runtime-settings] refreshed {len(self._overrides)} override(s)")
        except Exception as e:
            logger.warning(f"[runtime-settings] refresh failed, keeping last-known-good: {e}")

    async def _run_refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(REFRESH_SECONDS)
            try:
                await self.refresh()
            except Exception:
                logger.exception("[runtime-settings] refresh loop error")

    def start(self) -> None:
        if self._refresh_task is None or self._refresh_task.done():
            try:
                self._refresh_task = asyncio.get_event_loop().create_task(self._run_refresh_loop())
            except RuntimeError:
                logger.warning("[runtime-settings] no running event loop for refresh task")


_runtime: Optional[RuntimeSettingsStore] = None


def get_runtime() -> RuntimeSettingsStore:
    global _runtime
    if _runtime is None:
        # Load any existing overrides on first access.
        _runtime = RuntimeSettingsStore()
    return _runtime
