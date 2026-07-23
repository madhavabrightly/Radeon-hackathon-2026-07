"""Basic tests for Screen-AI backend."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))


async def test_database():
    """Test database initialization."""
    from app.db.database import init_db, get_db, close_db

    print("Testing database...")
    await init_db()
    print("[ok] Database initialized")

    db = await get_db()
    cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = await cursor.fetchall()
    print(f"[ok] Found {len(tables)} tables: {[t[0] for t in tables]}")

    await close_db()
    print("[ok] Database closed")


async def test_risk_classifier():
    """Test risk classifier."""
    from app.security.risk import RiskClassifier
    from app.agent.planner import Planner

    print("\nTesting risk classifier...")
    classifier = RiskClassifier()
    planner = Planner()

    test_cases = [
        ("check my storage", 0),
        ("open Chrome", 1),
        ("download VLC", 2),
        ("login to gmail.com", 3),
        ("delete files in Downloads", 4),
        ("format C drive", 5),
    ]

    for command, expected_risk in test_cases:
        intent = await planner.classify_intent(command)
        risk = await classifier.assess(command, intent)
        status = "[ok]" if risk == expected_risk else "[fail]"
        print(f"{status} '{command}' -> risk {risk} (expected {expected_risk})")


async def test_planner():
    """Test planner."""
    from app.agent.planner import Planner

    print("\nTesting planner...")
    planner = Planner()

    test_commands = [
        "check my storage",
        "open Chrome",
        "open YouTube",
        "search best air coolers in chrome",
        "close browser",
        "scan screen buttons",
        "click Share",
        "delete files in Downloads",
        "login to github.com",
    ]

    for command in test_commands:
        intent = await planner.classify_intent(command)
        print(f"[ok] '{command}' -> intent: {intent}")

    intent = await planner.classify_intent("search best air coolers in chrome")
    plan = await planner.create_plan("search best air coolers in chrome", intent)
    assert intent == "search_web"
    assert plan["steps"][0]["tool"] == "browser.search"
    assert plan["steps"][0]["args"]["query"] == "best air coolers"

    intent = await planner.classify_intent("open YouTube")
    plan = await planner.create_plan("open YouTube", intent)
    assert intent == "open_website"
    assert plan["steps"][0]["tool"] == "browser.open"
    assert plan["steps"][0]["args"]["url"] == "https://www.youtube.com"

    intent = await planner.classify_intent("close browser")
    plan = await planner.create_plan("close browser", intent)
    assert intent == "browser_close"
    assert plan["steps"][0]["tool"] == "browser.close"

    intent = await planner.classify_intent("scan screen buttons")
    plan = await planner.create_plan("scan screen buttons", intent)
    assert intent == "screen_scan"
    assert plan["steps"][0]["tool"] == "screen.scan"

    intent = await planner.classify_intent("click Share")
    plan = await planner.create_plan("click Share", intent)
    assert intent == "screen_click"
    assert plan["steps"][0]["tool"] == "screen.click_text"
    assert plan["steps"][0]["args"]["text"] == "Share"


async def test_permissions():
    """Test permission engine."""
    from app.security.permissions import PermissionEngine

    print("\nTesting permissions...")
    engine = PermissionEngine()

    test_cases = [
        ("check my storage", False),
        ("open Chrome", False),
        ("delete files in Downloads", True),
        ("login to gmail.com", True),
    ]

    for command, expected_approval in test_cases:
        intent = "delete_files" if "delete" in command else "login" if "login" in command else "open_app" if "open" in command else "system_status"
        risk = 4 if "delete" in command else 3 if "login" in command else 1 if "open" in command else 0
        requires = engine.requires_approval(risk, intent)
        status = "[ok]" if requires == expected_approval else "[fail]"
        print(f"{status} '{command}' -> approval: {requires} (expected {expected_approval})")


async def test_vault():
    """Test password vault."""
    from app.security.vault import PasswordVault

    print("\nTesting password vault...")
    vault = PasswordVault(kdf_memory_cost=8192, kdf_iterations=1, kdf_lanes=1)

    # Unlock with master key
    master_key = "test_master_key_123"
    unlocked = vault.unlock(master_key)
    print(f"[ok] Vault unlocked: {unlocked}")

    # Add credential
    await vault.add_credential("github.com", "user@example.com", "test_password_456")
    print("[ok] Credential added")

    # Get credential
    credential = await vault.get_credential("github.com", "user@example.com")
    print(f"[ok] Credential retrieved: {credential['password'] == 'test_password_456'}")

    # List sites
    sites = await vault.list_sites()
    print(f"[ok] Sites: {sites}")

    # Lock vault
    vault.lock()
    print("[ok] Vault locked")


async def test_redactor():
    """Test log redactor."""
    from app.logs.redactor import LogRedactor

    print("\nTesting log redactor...")
    redactor = LogRedactor()

    test_text = 'password="secret123" token="abc456" email="user@example.com"'
    redacted = redactor.redact(test_text)
    print(f"[ok] Original: {test_text}")
    print(f"[ok] Redacted: {redacted}")

    test_dict = {"username": "user", "password": "secret", "action": "login"}
    redacted_dict = redactor.redact_dict(test_dict)
    print(f"[ok] Dict redacted: {redacted_dict}")

    nested = {"steps": [{"args": {"token": "abc", "text": "password=\"secret\""}}]}
    nested_redacted = redactor.redact_dict(nested)
    assert nested_redacted["steps"][0]["args"]["token"] == "[REDACTED]"
    assert "secret" not in nested_redacted["steps"][0]["args"]["text"]
    print("[ok] Nested plan redaction works")


async def test_runtime_pipeline():
    """Test RAM budget, heat map, and tier decisions."""
    from app.runtime.heatmap import ToolHeatMap
    from app.runtime.resource_budget import ResourceBudget
    from app.runtime.tier_manager import AgentTierManager

    print("\nTesting runtime pipeline...")
    budget = ResourceBudget().measure()
    print(f"[ok] Runtime mode: {budget.mode}, model budget MB: {budget.model_budget_mb}")

    heatmap = ToolHeatMap()
    heatmap.record_plan("search_web", [{"tool": "browser.search", "args": {}}])
    hot_models = heatmap.hot_models_for_intent("search_web")
    print(f"[ok] Hot models for search_web: {hot_models}")

    decision = AgentTierManager().decide("search_web", budget, hot_models)
    print(f"[ok] Tier decision: {decision.tier} ({decision.reason})")


async def test_ssd_tier_plan():
    """Test codiii-inspired SSD tier planning for 4GB machines."""
    from app.runtime.artifact_store import ArtifactStore
    from app.runtime.resource_budget import ResourceBudget
    from app.runtime.ssd_tier import SSDTierManager
    import os

    print("\nTesting SSD tier plan...")
    previous = os.environ.get("SCREEN_AI_RAM_MB")
    os.environ["SCREEN_AI_RAM_MB"] = "1400"
    try:
        budgeter = ResourceBudget()
        budget = budgeter.measure()
        plan = SSDTierManager().plan(budget, ArtifactStore(), budgeter.reserve_mb)
        qwen = plan.placements["qwen-1.5b-q4"]
        assert qwen.tier == "ssd-off"
        assert not qwen.prefetch
        assert plan.placements["vault-crypto"].tier == "resident"
        print(f"[ok] SSD tier mode: {plan.mode}, qwen tier: {qwen.tier}")
    finally:
        if previous is None:
            os.environ.pop("SCREEN_AI_RAM_MB", None)
        else:
            os.environ["SCREEN_AI_RAM_MB"] = previous


async def test_model_artifacts_and_prompts():
    """Test model artifact discovery, loaders, screen cache, and prompt wiring."""
    from app.agent.llm_planner import LLMPlanner
    from app.runtime.artifact_store import ArtifactStore
    from app.runtime.model_loaders import browser_warmup_loader, vault_crypto_loader
    from app.runtime.screen_cache import ScreenCache

    print("\nTesting model artifacts and prompts...")
    store = ArtifactStore()
    inventory = store.inventory()
    assert "ui-detector-int8" in inventory
    assert "qwen-1.5b-q4" in inventory
    print(f"[ok] Artifact inventory keys: {list(inventory)}")

    vault = vault_crypto_loader(store)()
    assert vault["status"] in {"loaded", "unavailable"}
    print(f"[ok] Vault crypto loader: {vault['status']}")

    browser = browser_warmup_loader(store)()
    assert browser["status"] in {"loaded", "unavailable"}
    print(f"[ok] Browser warmup loader: {browser['status']}")

    prompt = LLMPlanner().build_prompt("search air coolers")
    assert "Screen-AI" in prompt
    assert "search air coolers" in prompt
    print("[ok] LLM prompt templates are wired")

    cache = ScreenCache()
    key = cache.key_text("test command", context="test")
    cache.write_json("ui", key, {"ok": True})
    assert cache.read_json("ui", key) == {"ok": True}
    print(f"[ok] Screen cache stats: {cache.stats()}")


async def test_pairing_token_verification():
    """Test paired devices must present the matching token."""
    from app.security.pairing import PairingManager

    print("\nTesting pairing token verification...")
    manager = PairingManager()
    code = await manager.generate_code()
    device = await manager.pair_device(code, "Test Phone")
    assert device
    assert await manager.verify_device(device["id"], device["token"])
    assert not await manager.verify_device(device["id"], "wrong-token")
    assert not await manager.verify_device(device["id"], None)
    print("[ok] Pairing token hash verification works")


async def main():
    """Run all tests."""
    from app.db.database import close_db

    print("=" * 60)
    print("Screen-AI Backend Tests")
    print("=" * 60)

    try:
        await test_database()
        await test_risk_classifier()
        await test_planner()
        await test_permissions()
        await test_vault()
        await test_redactor()
        await test_runtime_pipeline()
        await test_ssd_tier_plan()
        await test_model_artifacts_and_prompts()
        await test_pairing_token_verification()

        print("\n" + "=" * 60)
        print("All tests passed! [ok]")
        print("=" * 60)
    except Exception as e:
        print(f"\n[fail] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
