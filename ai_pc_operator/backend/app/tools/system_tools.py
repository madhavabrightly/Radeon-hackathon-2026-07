"""System tools - status, disk, RAM, processes, app control."""

from __future__ import annotations

import psutil
import asyncio
import ctypes
import platform
import re
import shlex
import subprocess
import shutil
import time
from typing import Dict, Any, List


class SystemTools:
    """System control tools."""

    APP_ALIASES = {
        "chrome": "chrome",
        "edge": "msedge",
        "firefox": "firefox",
        "notepad": "notepad",
        "calculator": "calc",
        "calc": "calc",
        "explorer": "explorer",
        "paint": "mspaint",
        "cmd": "cmd",
        "powershell": "powershell",
        "terminal": "wt",
        "excel": "excel",
        "word": "winword",
        "powerpoint": "powerpnt",
    }

    async def status(self) -> Dict[str, Any]:
        """Get system status."""
        return {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "hostname": platform.node(),
            "cpu_percent": psutil.cpu_percent(interval=1),
            "cpu_count": psutil.cpu_count(),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_total_gb": round(
                psutil.virtual_memory().total / (1024**3), 2
            ),
            "memory_available_gb": round(
                psutil.virtual_memory().available / (1024**3), 2
            ),
            "disk_percent": psutil.disk_usage("/").percent,
            "disk_total_gb": round(
                psutil.disk_usage("/").total / (1024**3), 2
            ),
            "disk_free_gb": round(
                psutil.disk_usage("/").free / (1024**3), 2
            ),
            "boot_time": psutil.boot_time(),
            "uptime_seconds": (
                time.time() - psutil.boot_time()
            ),
        }

    async def get_status(self) -> Dict[str, Any]:
        """Alias for status."""
        return await self.status()

    async def disk_usage(self) -> Dict[str, Any]:
        """Get disk usage."""
        usage = psutil.disk_usage("/")
        return {
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
            "percent": usage.percent,
        }

    async def ram_usage(self) -> Dict[str, Any]:
        """Get RAM usage."""
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "percent": mem.percent,
        }

    async def processes(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get running processes."""
        procs = []
        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent"]
        ):
            try:
                procs.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Sort by memory usage
        procs.sort(
            key=lambda x: x.get("memory_percent", 0), reverse=True
        )
        return procs[:limit]

    async def open_app(self, name: str) -> Dict[str, Any]:
        """Open an application."""
        try:
            executable = self._resolve_app(name)
            subprocess.Popen([executable])
            return {
                "status": "success",
                "message": f"Opened {executable}",
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
            }

    async def kill_process(self, pid: int) -> Dict[str, Any]:
        """Kill a process by PID."""
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            return {
                "status": "success",
                "message": f"Killed process {pid}",
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
            }

    async def network_status(self) -> Dict[str, Any]:
        """Get network status."""
        net = psutil.net_io_counters()
        return {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        }

    async def open_settings(self, page: str = "ms-settings:") -> Dict[str, Any]:
        """Open a Windows Settings page."""
        try:
            if not page.startswith("ms-settings:"):
                page = "ms-settings:"
            subprocess.Popen(["explorer.exe", page])
            return {"status": "success", "page": page}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    async def keep_awake(self, minutes: int = 60) -> Dict[str, Any]:
        """Prevent system/display sleep for a bounded duration."""
        minutes = max(1, min(int(minutes), 120))
        if platform.system().lower() != "windows":
            return {
                "status": "failed",
                "error": "keep_awake is currently implemented for Windows only",
            }

        async def hold_awake() -> None:
            es_continuous = 0x80000000
            es_system_required = 0x00000001
            es_display_required = 0x00000002
            flags = es_continuous | es_system_required | es_display_required
            ctypes.windll.kernel32.SetThreadExecutionState(flags)
            try:
                await asyncio.sleep(minutes * 60)
            finally:
                ctypes.windll.kernel32.SetThreadExecutionState(es_continuous)

        asyncio.create_task(hold_awake())
        return {
            "status": "success",
            "minutes": minutes,
            "method": "SetThreadExecutionState",
        }

    async def run_command(self, command: str) -> Dict[str, Any]:
        """Run a shell command (HIGH RISK)."""
        try:
            args = shlex.split(command, posix=False)
            if not args:
                return {"status": "failed", "error": "Empty command"}
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "status": "success",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
            }

    def _resolve_app(self, name: str) -> str:
        """Resolve a natural app name to a safe executable name."""
        cleaned = re.sub(r"[^a-zA-Z0-9_. -]", "", name).strip().lower()
        if not cleaned:
            raise ValueError("App name is empty after sanitization")

        alias = self.APP_ALIASES.get(cleaned, cleaned.split()[0])
        found = shutil.which(alias)
        if found:
            return found
        if alias in self.APP_ALIASES.values():
            return alias
        raise ValueError(f"Unknown or unavailable app: {name}")
