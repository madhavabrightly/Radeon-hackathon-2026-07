"""System tools - status, disk, RAM, processes, app control."""

from __future__ import annotations

import psutil
import platform
import subprocess
import shutil
from typing import Dict, Any, List


class SystemTools:
    """System control tools."""

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
                psutil.time.time() - psutil.boot_time()
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
            # Try to open using Windows start command
            subprocess.Popen(f"start {name}", shell=True)
            return {
                "status": "success",
                "message": f"Opened {name}",
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

    async def run_command(self, command: str) -> Dict[str, Any]:
        """Run a shell command (HIGH RISK)."""
        try:
            result = subprocess.run(
                command,
                shell=True,
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
