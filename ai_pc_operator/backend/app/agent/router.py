"""Agent router - main command processing pipeline.

This is the core of the agent brain. It receives user commands,
classifies intent, assesses risk, plans actions, and executes tools.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Dict, Any, List

from app.agent.planner import Planner
from app.agent.memory import Memory
from app.security.risk import RiskClassifier
from app.security.permissions import PermissionEngine
from app.approvals.manager import ApprovalManager
from app.tools.system_tools import SystemTools
from app.tools.file_tools import FileTools
from app.tools.browser_tools import BrowserTools
from app.tools.auth_tools import AuthTools
from app.db.database import db_session

logger = logging.getLogger(__name__)


class AgentRouter:
    """Main agent router that processes commands."""

    def __init__(
        self,
        approval_manager: ApprovalManager,
        system_tools: SystemTools,
        file_tools: FileTools,
        browser_tools: BrowserTools,
        auth_tools: AuthTools,
    ):
        """Initialize agent router."""
        self.planner = Planner()
        self.memory = Memory()
        self.risk_classifier = RiskClassifier()
        self.permission_engine = PermissionEngine()
        self.approval_manager = approval_manager

        # Tool registry
        self.tools = {
            "system": system_tools,
            "file": file_tools,
            "browser": browser_tools,
            "auth": auth_tools,
        }

        self.emergency_stopped = False

    async def process_command(
        self,
        text: str,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a user command through the full pipeline.

        Pipeline:
        1. Save command to database
        2. Classify intent
        3. Assess risk
        4. Check permissions
        5. Request approval if needed
        6. Plan actions
        7. Execute tools
        8. Verify results
        9. Log and return
        """
        if self.emergency_stopped:
            return {
                "status": "blocked",
                "error": "Emergency stop is active",
            }

        logger.info(f"Processing command: {text}")

        # Step 1: Save command
        command_id = await self._save_command(text, device_id)

        try:
            # Step 2: Classify intent
            intent = await self.planner.classify_intent(text)
            logger.info(f"Intent: {intent}")

            # Step 3: Assess risk
            risk_level = await self.risk_classifier.assess(text, intent)
            logger.info(f"Risk level: {risk_level}")

            # Step 4: Check permissions
            requires_approval = self.permission_engine.requires_approval(
                risk_level, intent
            )

            # Step 5: Request approval if needed. wait_for_approval uses
            # asyncio.wait_for and yields control while mobile approval is pending.
            if requires_approval:
                approval_id = await self.approval_manager.create_approval(
                    command_id=command_id,
                    risk_level=risk_level,
                    action_type=intent,
                    target=text,
                    description=f"Execute: {text}",
                )

                # Wait for approval
                approved = await self.approval_manager.wait_for_approval(
                    approval_id, timeout=300
                )

                if not approved:
                    await self._update_command_status(
                        command_id, "rejected", "User rejected approval"
                    )
                    return {
                        "command_id": command_id,
                        "status": "rejected",
                        "result": "User rejected the action",
                    }

            # Step 6: Plan actions
            plan = await self.planner.create_plan(text, intent)
            logger.info(f"Plan: {plan}")

            # Step 7: Execute tools
            results = []
            for step in plan.get("steps", []):
                if self.emergency_stopped:
                    break

                tool_name = step.get("tool")
                tool_args = step.get("args", {})

                result = await self._execute_tool(tool_name, tool_args, command_id)
                results.append(result)

            # Step 8: Verify results
            verified = all(r.get("status") == "success" for r in results)

            # Step 9: Format response
            response = {
                "command_id": command_id,
                "status": "completed" if verified else "partial",
                "result": self._format_results(results),
                "requires_approval": requires_approval,
            }

            await self._update_command_status(
                command_id,
                "completed" if verified else "partial",
                response["result"],
            )

            # Save to memory
            await self.memory.add(text, intent, response)

            return response

        except Exception as e:
            logger.error(f"Error processing command: {e}", exc_info=True)
            await self._update_command_status(
                command_id, "failed", error=str(e)
            )
            return {
                "command_id": command_id,
                "status": "failed",
                "error": str(e),
            }

    async def _execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        command_id: int,
    ) -> Dict[str, Any]:
        """Execute a single tool."""
        try:
            # Parse tool name (e.g., "file.list" -> category="file", method="list")
            if "." in tool_name:
                category, method = tool_name.split(".", 1)
            else:
                category = "system"
                method = tool_name

            tool = self.tools.get(category)
            if not tool:
                return {
                    "status": "failed",
                    "error": f"Unknown tool category: {category}",
                }

            method_func = getattr(tool, method, None)
            if not method_func:
                return {
                    "status": "failed",
                    "error": f"Unknown method: {method}",
                }

            # Execute
            if asyncio.iscoroutinefunction(method_func):
                result = await method_func(**args)
            else:
                result = method_func(**args)

            # Log action
            await self._log_action(
                command_id, tool_name, args, result, "success"
            )

            return {
                "status": "success",
                "tool": tool_name,
                "result": result,
            }

        except Exception as e:
            logger.error(f"Tool execution failed: {e}", exc_info=True)
            await self._log_action(
                command_id, tool_name, args, None, "failed", error=str(e)
            )
            return {
                "status": "failed",
                "tool": tool_name,
                "error": str(e),
            }

    async def _save_command(
        self, text: str, device_id: Optional[str]
    ) -> int:
        """Save command to database."""
        async with db_session() as db:
            cursor = await db.execute(
                """
                INSERT INTO commands (source, device_id, input_text, status)
                VALUES (?, ?, ?, ?)
                """,
                ("mobile" if device_id else "pc", device_id, text, "pending"),
            )
            await db.commit()
            command_id = cursor.lastrowid
        return command_id

    async def _update_command_status(
        self,
        command_id: int,
        status: str,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update command status."""
        async with db_session() as db:
            await db.execute(
                """
                UPDATE commands
                SET status = ?, result = ?, error = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, result, error, command_id),
            )
            await db.commit()

    async def _log_action(
        self,
        command_id: int,
        tool: str,
        input_data: Dict[str, Any],
        output_data: Optional[Dict[str, Any]],
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Log action to database."""
        import json

        async with db_session() as db:
            await db.execute(
                """
                INSERT INTO actions (command_id, tool, input_json, output_json, status, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    command_id,
                    tool,
                    json.dumps(input_data),
                    json.dumps(output_data) if output_data else None,
                    status,
                    error,
                ),
            )
            await db.commit()

    def _format_results(self, results: List[Dict[str, Any]]) -> str:
        """Format tool results into human-readable response."""
        if not results:
            return "No actions taken"

        lines = []
        for r in results:
            if r["status"] == "success":
                tool = r.get("tool", "unknown")
                result = r.get("result", "")
                lines.append(f"✓ {tool}: {result}")
            else:
                tool = r.get("tool", "unknown")
                error = r.get("error", "Unknown error")
                lines.append(f"✗ {tool}: {error}")

        return "\n".join(lines)

    async def emergency_stop(self) -> None:
        """Activate emergency stop."""
        self.emergency_stopped = True
        logger.warning("Emergency stop activated")

    def reset_emergency_stop(self) -> None:
        """Reset emergency stop."""
        self.emergency_stopped = False
        logger.info("Emergency stop reset")

    async def shutdown(self) -> None:
        """Release heavy tool resources before app shutdown."""
        browser_tools = self.tools.get("browser")
        if browser_tools and hasattr(browser_tools, "close"):
            await browser_tools.close()
