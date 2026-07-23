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
        "delete files in Downloads",
        "login to github.com",
    ]

    for command in test_commands:
        intent = await planner.classify_intent(command)
        print(f"[ok] '{command}' -> intent: {intent}")


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
