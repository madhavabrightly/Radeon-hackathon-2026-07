"""Agent router - main command processing pipeline.

This is the core of the agent brain. It receives user commands,
classifies intent, assesses risk, plans actions, and executes tools.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List

from app.agent.llm_planner import LLMPlanner
from app.agent.planner import Planner
from app.agent.task_planner import TaskPlanner
from app.agent.memory import Memory
from app.security.risk import RiskClassifier
from app.security.permissions import PermissionEngine
from app.approvals.manager import ApprovalManager
from app.tools.system_tools import SystemTools
from app.tools.file_tools import FileTools
from app.tools.browser_tools import BrowserTools
from app.tools.auth_tools import AuthTools
from app.tools.screen_tools import ScreenTools
from app.db.database import db_session
from app.logs.redactor import LogRedactor
from app.runtime.artifact_store import ArtifactStore
from app.runtime.heatmap import ToolHeatMap
from app.runtime.io_pool import IOPool
from app.runtime.model_loaders import (
    browser_warmup_loader,
    ocr_mobile_loader,
    qwen_gguf_loader,
    ui_detector_loader,
    vault_crypto_loader,
)
from app.runtime.model_insights import ModelInsights
from app.runtime.model_registry import ModelRegistry, ModelSpec
from app.runtime.resource_budget import ResourceBudget
from app.runtime.screen_cache import ScreenCache
from app.runtime.ssd_tier import SSDTierManager
from app.runtime.tier_manager import AgentTierManager
from app.runtime.strategy import StrategyRouter
from app.runtime.telemetry import Telemetry

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
        screen_tools: ScreenTools,
    ):
        """Initialize agent router."""
        self.planner = Planner()
        self.task_planner = TaskPlanner()
        self.llm_planner = LLMPlanner()
        self.memory = Memory()
        self.redactor = LogRedactor()
        self.risk_classifier = RiskClassifier()
        self.permission_engine = PermissionEngine()
        self.approval_manager = approval_manager
        self.resource_budget = ResourceBudget()
        self.io_pool = IOPool(max_workers=2)
        self.artifacts = ArtifactStore()
        self.model_insights = ModelInsights(self.artifacts)
        self.ssd_tier = SSDTierManager()
        self.screen_cache = ScreenCache()
        self.model_registry = ModelRegistry(self.resource_budget, self.io_pool, self.ssd_tier)
        self.heatmap = ToolHeatMap()
        self.tier_manager = AgentTierManager()
        self.strategy = StrategyRouter()
        self.telemetry = Telemetry()
        self._register_lazy_models()

        # Tool registry
        self.tools = {
            "system": system_tools,
            "file": file_tools,
            "browser": browser_tools,
            "auth": auth_tools,
            "screen": screen_tools,
        }

        self.emergency_stopped = False

    def _register_lazy_models(self) -> None:
        """Register lazy model loaders for RAM-aware prefetch."""
        self.model_registry.register(
            ModelSpec("ocr-mobile", 160, ocr_mobile_loader(self.artifacts))
        )
        self.model_registry.register(
            ModelSpec("ui-detector-int8", 350, ui_detector_loader(self.artifacts))
        )
        self.model_registry.register(
            ModelSpec(
                "qwen-1.5b-q4",
                1200,
                qwen_gguf_loader(self.artifacts),
                idle_ttl_sec=300,
            )
        )
        self.model_registry.register(
            ModelSpec("vault-crypto", 64, vault_crypto_loader(self.artifacts))
        )
        self.model_registry.register(
            ModelSpec("browser-warmup", 128, browser_warmup_loader(self.artifacts))
        )

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
        pipeline_start = time.time()

        # Step 1: Save command
        command_id = await self._save_command(text, device_id)

        try:
            # Step 2: classify intent while a RAM snapshot runs off-loop.
            budget_task = asyncio.create_task(
                asyncio.to_thread(self.resource_budget.measure)
            )
            task_plan = self.task_planner.plan(text)
            intent = task_plan.intent if task_plan else await self.planner.classify_intent(text)
            budget = await budget_task
            ssd_plan = self.ssd_tier.plan(
                budget,
                self.artifacts,
                self.resource_budget.reserve_mb,
            )
            logger.info(f"Intent: {intent}")

            llm_plan: Dict[str, Any] | None = None
            qwen_allowed = self.ssd_tier.can_load("qwen-1.5b-q4", ssd_plan)
            if intent == "unknown" and budget.allow_llm and qwen_allowed:
                qwen = await self.model_registry.get("qwen-1.5b-q4")
                llm_plan = await self.llm_planner.create_plan(text, qwen)
                if llm_plan:
                    intent = llm_plan.get("intent", intent)
                    logger.info("LLM planner produced a plan for unknown intent")
            model_plan = self.model_insights.plan_for_command(
                text,
                intent,
                budget,
                self.heatmap.hot_models_for_intent(intent),
            )

            # Step 3: assess risk while runtime tiers/prefetch are decided.
            risk_task = asyncio.create_task(
                self.risk_classifier.assess(text, intent)
            )
            hot_models = self.heatmap.hot_models_for_intent(intent)
            tier_decision = self.tier_manager.decide(intent, budget, hot_models)
            prefetch_models = [
                name
                for name in [*tier_decision.prefetch_models, *model_plan.get("prefetch", [])]
                if self.ssd_tier.should_prefetch(name, ssd_plan)
            ]
            self.model_registry.prefetch(prefetch_models)
            self._prefetch_hot_tools(self.heatmap.hot_tools(intent), budget.model_budget_mb)
            risk_level = await risk_task
            if llm_plan:
                risk_level = max(risk_level, int(llm_plan.get("risk_level", 1)))
            logger.info(f"Risk level: {risk_level}")
            logger.info(f"Tier decision: {tier_decision}")
            await self._update_command_metadata(command_id, intent, risk_level)

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
                    target=self.redactor.redact(text),
                    description=f"Execute: {self.redactor.redact(text)}",
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
            plan = (
                task_plan.to_dict()
                if task_plan
                else llm_plan or await self.planner.create_plan(text, intent)
            )
            logger.info(f"Plan: {plan}")
            steps = plan.get("steps", [])
            self.heatmap.record_plan(intent, steps)
            self._write_plan_cache(text, intent, plan, tier_decision.to_dict())

            if not steps:
                message = (
                    plan.get("error")
                    or "I could not map that command to a safe tool plan yet."
                )
                response = {
                    "command_id": command_id,
                    "status": "unsupported",
                    "result": message,
                    "requires_approval": requires_approval,
                    "runtime": tier_decision.to_dict(),
                    "ssd_tier": ssd_plan.to_dict(),
                    "model_plan": model_plan,
                }
                await self._update_command_status(
                    command_id,
                    "unsupported",
                    response["result"],
                )
                await self.memory.add(self.redactor.redact(text), intent, response)
                return response

            # Step 7: Execute tools via strategy engine (circuit breaker + retry)
            results = []
            for step in steps:
                if self.emergency_stopped:
                    break

                tool_name = step.get("tool")
                tool_args = step.get("args", {})
                tool_start = time.time()

                # Use strategy engine for circuit breaker + adaptive retry
                async def _exec(tool, args):
                    return await self._execute_tool(tool, args, command_id)

                result = await self.strategy.execute_with_strategy(
                    tool_name, tool_args, _exec, intent=intent, command_id=command_id
                )

                # Record telemetry for tool call
                tool_latency = (time.time() - tool_start) * 1000
                self.telemetry.record_tool_call(
                    command_id, tool_name, tool_latency,
                    result.get("status") == "success"
                )
                results.append(result)

            # Step 8: Verify results
            verified = all(r.get("status") == "success" for r in results)

            # Step 9: Format response with telemetry + strategy data
            pipeline_ms = (time.time() - pipeline_start) * 1000
            response = {
                "command_id": command_id,
                "status": "completed" if verified else "partial",
                "result": self._format_results(results),
                "requires_approval": requires_approval,
                "runtime": tier_decision.to_dict(),
                "ssd_tier": ssd_plan.to_dict(),
                "model_plan": model_plan,
                "telemetry": {
                    "pipeline_ms": round(pipeline_ms, 1),
                    "tools_executed": len(results),
                    "tools_succeeded": sum(1 for r in results if r.get("status") == "success"),
                    "strategy": self.strategy.status(),
                },
            }

            await self._update_command_status(
                command_id,
                "completed" if verified else "partial",
                response["result"],
            )

            # Record intent success in telemetry
            self.telemetry.record_intent(intent)

            # Save to memory
            await self.memory.add(self.redactor.redact(text), intent, response)
            await self._maintenance()

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
        finally:
            await self._maintenance()

    async def preview_plan(self, text: str) -> Dict[str, Any]:
        """Return the planned interpretation of a command without executing it."""
        budget = await asyncio.to_thread(self.resource_budget.measure)
        task_plan = self.task_planner.plan(text)
        intent = task_plan.intent if task_plan else await self.planner.classify_intent(text)
        ssd_plan = self.ssd_tier.plan(
            budget,
            self.artifacts,
            self.resource_budget.reserve_mb,
        )
        llm_plan: Dict[str, Any] | None = None
        qwen_allowed = self.ssd_tier.can_load("qwen-1.5b-q4", ssd_plan)
        if intent == "unknown" and budget.allow_llm and qwen_allowed:
            qwen = await self.model_registry.get("qwen-1.5b-q4")
            llm_plan = await self.llm_planner.create_plan(text, qwen)
            if llm_plan:
                intent = llm_plan.get("intent", intent)

        risk_level = await self.risk_classifier.assess(text, intent)
        if llm_plan:
            risk_level = max(risk_level, int(llm_plan.get("risk_level", 1)))
        requires_approval = self.permission_engine.requires_approval(
            risk_level,
            intent,
        )
        model_plan = self.model_insights.plan_for_command(
            text,
            intent,
            budget,
            self.heatmap.hot_models_for_intent(intent),
        )
        plan = (
            task_plan.to_dict()
            if task_plan
            else llm_plan or await self.planner.create_plan(text, intent)
        )
        steps = plan.get("steps", [])
        return {
            "status": "planned" if steps else "unsupported",
            "input": self.redactor.redact(text),
            "intent": intent,
            "risk_level": risk_level,
            "requires_approval": requires_approval,
            "plan": self.redactor.redact_dict(plan),
            "step_count": len(steps),
            "runtime": self.tier_manager.decide(
                intent,
                budget,
                self.heatmap.hot_models_for_intent(intent),
            ).to_dict(),
            "ssd_tier": ssd_plan.to_dict(),
            "model_plan": model_plan,
            "message": (
                "Ready to execute after Send."
                if steps
                else plan.get("error", "No safe executable plan was found.")
            ),
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
                result = await self.io_pool.run(method_func, **args)

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
                (
                    "mobile" if device_id else "pc",
                    device_id,
                    self.redactor.redact(text),
                    "pending",
                ),
            )
            await db.commit()
            command_id = cursor.lastrowid
        return command_id

    async def _update_command_metadata(
        self,
        command_id: int,
        intent: str,
        risk_level: int,
    ) -> None:
        """Persist classified intent and risk for history/audit views."""
        async with db_session() as db:
            await db.execute(
                """
                UPDATE commands
                SET intent = ?, risk_level = ?
                WHERE id = ?
                """,
                (intent, risk_level, command_id),
            )
            await db.commit()

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
                    json.dumps(self.redactor.redact_dict(input_data)),
                    json.dumps(self.redactor.redact_dict(output_data)) if output_data else None,
                    status,
                    self.redactor.redact(error) if error else None,
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
        await self.model_registry.shutdown()
        self.io_pool.shutdown()

    async def _maintenance(self) -> None:
        """Unload idle heavy resources between commands."""
        browser_tools = self.tools.get("browser")
        if browser_tools and hasattr(browser_tools, "unload_idle"):
            await browser_tools.unload_idle()
        self.model_registry.unload_idle()

    def _prefetch_hot_tools(self, tool_names: list[str], model_budget_mb: int) -> None:
        """Warm safe tool dependencies from heat-map predictions."""
        if model_budget_mb < 128:
            return

        categories = []
        for tool_name in tool_names:
            if "." in tool_name:
                category, _ = tool_name.split(".", 1)
                categories.append(category)

        for category in dict.fromkeys(categories):
            tool = self.tools.get(category)
            prepare = getattr(tool, "prepare", None)
            if not prepare:
                continue
            if asyncio.iscoroutinefunction(prepare):
                asyncio.create_task(prepare())

    def _write_plan_cache(
        self,
        text: str,
        intent: str,
        plan: Dict[str, Any],
        runtime: Dict[str, Any],
    ) -> None:
        """Record plan metadata in the screen cache hierarchy."""
        key = self.screen_cache.key_text(text, context=intent)
        self.screen_cache.write_json(
            "ui",
            key,
            {
                "command": self.redactor.redact(text),
                "intent": intent,
                "plan": self.redactor.redact_dict(plan),
                "runtime": runtime,
            },
        )
