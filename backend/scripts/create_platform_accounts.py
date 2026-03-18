"""Create platform accounts using AgentMail inboxes + Browser Use cloud browser.

# RESEARCH: Checked playwright-signup-bots, puppeteer-account-creator, various signup scripts
# DECISION: Browser Use cloud + AgentMail — already in our stack, BU 2.0 handles CAPTCHAs,
#   AgentMail provides real inboxes for verification emails
# ALT: Manual signup (slow), temp-mail (no SDK, flaky)

Usage:
    python scripts/create_platform_accounts.py --platforms twitter,linkedin,instagram,reddit
    python scripts/create_platform_accounts.py --platforms twitter --dry-run
    python scripts/create_platform_accounts.py  # all platforms
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import string
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

from config import get_settings

ACCOUNTS_DIR = Path(os.path.expanduser("~/.jarvis"))
ACCOUNTS_FILE = ACCOUNTS_DIR / "accounts.json"

PLATFORMS = {
    "twitter": {
        "name": "Twitter/X",
        "signup_url": "https://x.com/i/flow/signup",
    },
    "linkedin": {
        "name": "LinkedIn",
        "signup_url": "https://www.linkedin.com/signup",
    },
    "instagram": {
        "name": "Instagram",
        "signup_url": "https://www.instagram.com/accounts/emailsignup/",
    },
    "reddit": {
        "name": "Reddit",
        "signup_url": "https://www.reddit.com/register",
    },
}

FIRST_NAMES = ["Alex", "Jordan", "Morgan", "Casey", "Riley", "Taylor", "Quinn", "Avery"]
LAST_NAMES = ["Chen", "Smith", "Patel", "Garcia", "Kim", "Davis", "Lee", "Wilson"]


def _generate_identity() -> dict[str, str]:
    """Generate a random name + password for account creation."""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    suffix = "".join(random.choices(string.digits, k=4))
    username = f"{first.lower()}{last.lower()}{suffix}"
    password = "".join(random.choices(string.ascii_letters + string.digits + "!@#$", k=16))
    return {
        "first_name": first,
        "last_name": last,
        "username": username,
        "password": password,
    }


def _load_accounts() -> dict:
    """Load existing accounts from disk."""
    if ACCOUNTS_FILE.exists():
        try:
            return json.loads(ACCOUNTS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupted accounts file, starting fresh")
    return {}


def _save_accounts(accounts: dict) -> None:
    """Save accounts to disk (outside the repo)."""
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    ACCOUNTS_FILE.write_text(json.dumps(accounts, indent=2))
    logger.info("Saved accounts to {}", ACCOUNTS_FILE)


async def _wait_for_verification(
    mail_client,
    inbox_id: str,
    max_wait: int = 120,
    poll_interval: int = 10,
) -> str | None:
    """Poll AgentMail inbox for a verification link."""
    elapsed = 0
    while elapsed < max_wait:
        link = mail_client.get_verification_link(inbox_id)
        if link:
            return link
        logger.debug("No verification email yet for {}, waiting {}s...", inbox_id, poll_interval)
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    return None


async def signup_twitter(
    mail_client,
    identity: dict[str, str],
    email: str,
    inbox_id: str,
) -> dict:
    """Create a Twitter/X account via Browser Use cloud."""
    from browser_use import Agent, Browser, ChatBrowserUse

    logger.info("twitter: starting signup with email={}", email)

    browser = Browser(use_cloud=True)
    try:
        llm = ChatBrowserUse(model="bu-2-0")
        task = (
            f"Go to https://x.com/i/flow/signup and create a new account. "
            f"Use these details:\n"
            f"- Name: {identity['first_name']} {identity['last_name']}\n"
            f"- Email: {email}\n"
            f"- Password: {identity['password']}\n"
            f"- Date of birth: January 15, 1998\n"
            f"Fill in each step of the signup flow. "
            f"If asked for a verification code, say 'NEED_VERIFICATION' and stop. "
            f"If you encounter a CAPTCHA, attempt to solve it. "
            f"If signup completes, say 'SIGNUP_COMPLETE'."
        )

        agent = Agent(task=task, llm=llm, browser=browser)
        result = await asyncio.wait_for(agent.run(), timeout=180)
        result_text = result.final_result() if hasattr(result, "final_result") else str(result)

        if "NEED_VERIFICATION" in str(result_text):
            logger.info("twitter: waiting for verification email...")
            link = await _wait_for_verification(mail_client, inbox_id)
            if link:
                logger.info("twitter: got verification link, clicking...")
                verify_agent = Agent(
                    task=f"Navigate to this verification link and complete verification: {link}",
                    llm=llm,
                    browser=browser,
                )
                await asyncio.wait_for(verify_agent.run(), timeout=60)

        return {
            "platform": "twitter",
            "status": "created",
            "result": str(result_text)[:500],
        }
    except asyncio.TimeoutError:
        logger.error("twitter: signup timed out")
        return {"platform": "twitter", "status": "timeout"}
    except Exception as exc:
        logger.error("twitter: signup failed: {}", exc)
        return {"platform": "twitter", "status": "error", "error": str(exc)}
    finally:
        await browser.close()


async def signup_linkedin(
    mail_client,
    identity: dict[str, str],
    email: str,
    inbox_id: str,
) -> dict:
    """Create a LinkedIn account via Browser Use cloud."""
    from browser_use import Agent, Browser, ChatBrowserUse

    logger.info("linkedin: starting signup with email={}", email)

    browser = Browser(use_cloud=True)
    try:
        llm = ChatBrowserUse(model="bu-2-0")
        task = (
            f"Go to https://www.linkedin.com/signup and create a new account. "
            f"Use these details:\n"
            f"- First name: {identity['first_name']}\n"
            f"- Last name: {identity['last_name']}\n"
            f"- Email: {email}\n"
            f"- Password: {identity['password']}\n"
            f"Fill in each step. If asked for email verification code, say 'NEED_VERIFICATION'. "
            f"If asked for phone number, skip if possible or say 'NEED_PHONE'. "
            f"If signup completes, say 'SIGNUP_COMPLETE'."
        )

        agent = Agent(task=task, llm=llm, browser=browser)
        result = await asyncio.wait_for(agent.run(), timeout=180)
        result_text = result.final_result() if hasattr(result, "final_result") else str(result)

        if "NEED_VERIFICATION" in str(result_text):
            logger.info("linkedin: waiting for verification email...")
            link = await _wait_for_verification(mail_client, inbox_id)
            if link:
                logger.info("linkedin: got verification link, clicking...")
                verify_agent = Agent(
                    task=f"Navigate to this verification link and complete verification: {link}",
                    llm=llm,
                    browser=browser,
                )
                await asyncio.wait_for(verify_agent.run(), timeout=60)

        return {
            "platform": "linkedin",
            "status": "created",
            "result": str(result_text)[:500],
        }
    except asyncio.TimeoutError:
        logger.error("linkedin: signup timed out")
        return {"platform": "linkedin", "status": "timeout"}
    except Exception as exc:
        logger.error("linkedin: signup failed: {}", exc)
        return {"platform": "linkedin", "status": "error", "error": str(exc)}
    finally:
        await browser.close()


async def signup_instagram(
    mail_client,
    identity: dict[str, str],
    email: str,
    inbox_id: str,
) -> dict:
    """Create an Instagram account via Browser Use cloud."""
    from browser_use import Agent, Browser, ChatBrowserUse

    logger.info("instagram: starting signup with email={}", email)

    browser = Browser(use_cloud=True)
    try:
        llm = ChatBrowserUse(model="bu-2-0")
        task = (
            f"Go to https://www.instagram.com/accounts/emailsignup/ and create a new account. "
            f"Use these details:\n"
            f"- Email: {email}\n"
            f"- Full name: {identity['first_name']} {identity['last_name']}\n"
            f"- Username: {identity['username']}\n"
            f"- Password: {identity['password']}\n"
            f"- Date of birth: January 15, 1998\n"
            f"Fill in each step. If asked for a confirmation code from email, "
            f"say 'NEED_VERIFICATION'. "
            f"If signup completes, say 'SIGNUP_COMPLETE'."
        )

        agent = Agent(task=task, llm=llm, browser=browser)
        result = await asyncio.wait_for(agent.run(), timeout=180)
        result_text = result.final_result() if hasattr(result, "final_result") else str(result)

        if "NEED_VERIFICATION" in str(result_text):
            logger.info("instagram: waiting for verification email...")
            link = await _wait_for_verification(mail_client, inbox_id)
            if link:
                logger.info("instagram: got verification link, clicking...")
                verify_agent = Agent(
                    task=f"Navigate to this verification link and complete verification: {link}",
                    llm=llm,
                    browser=browser,
                )
                await asyncio.wait_for(verify_agent.run(), timeout=60)

        return {
            "platform": "instagram",
            "status": "created",
            "result": str(result_text)[:500],
        }
    except asyncio.TimeoutError:
        logger.error("instagram: signup timed out")
        return {"platform": "instagram", "status": "timeout"}
    except Exception as exc:
        logger.error("instagram: signup failed: {}", exc)
        return {"platform": "instagram", "status": "error", "error": str(exc)}
    finally:
        await browser.close()


async def signup_reddit(
    mail_client,
    identity: dict[str, str],
    email: str,
    inbox_id: str,
) -> dict:
    """Create a Reddit account via Browser Use cloud."""
    from browser_use import Agent, Browser, ChatBrowserUse

    logger.info("reddit: starting signup with email={}", email)

    browser = Browser(use_cloud=True)
    try:
        llm = ChatBrowserUse(model="bu-2-0")
        task = (
            f"Go to https://www.reddit.com/register and create a new account. "
            f"Use these details:\n"
            f"- Email: {email}\n"
            f"- Username: {identity['username']}\n"
            f"- Password: {identity['password']}\n"
            f"Fill in each step. If asked for email verification, say 'NEED_VERIFICATION'. "
            f"If you encounter a CAPTCHA, attempt to solve it. "
            f"If signup completes, say 'SIGNUP_COMPLETE'."
        )

        agent = Agent(task=task, llm=llm, browser=browser)
        result = await asyncio.wait_for(agent.run(), timeout=180)
        result_text = result.final_result() if hasattr(result, "final_result") else str(result)

        if "NEED_VERIFICATION" in str(result_text):
            logger.info("reddit: waiting for verification email...")
            link = await _wait_for_verification(mail_client, inbox_id)
            if link:
                logger.info("reddit: got verification link, clicking...")
                verify_agent = Agent(
                    task=f"Navigate to this verification link and complete verification: {link}",
                    llm=llm,
                    browser=browser,
                )
                await asyncio.wait_for(verify_agent.run(), timeout=60)

        return {
            "platform": "reddit",
            "status": "created",
            "result": str(result_text)[:500],
        }
    except asyncio.TimeoutError:
        logger.error("reddit: signup timed out")
        return {"platform": "reddit", "status": "timeout"}
    except Exception as exc:
        logger.error("reddit: signup failed: {}", exc)
        return {"platform": "reddit", "status": "error", "error": str(exc)}
    finally:
        await browser.close()


SIGNUP_FUNCTIONS = {
    "twitter": signup_twitter,
    "linkedin": signup_linkedin,
    "instagram": signup_instagram,
    "reddit": signup_reddit,
}


async def create_account_for_platform(
    platform: str,
    mail_client,
    dry_run: bool = False,
) -> dict:
    """Create an AgentMail inbox + platform account for a single platform."""
    info = PLATFORMS[platform]
    identity = _generate_identity()

    logger.info("{}: generating identity — {} {}", platform, identity["first_name"], identity["last_name"])

    if dry_run:
        logger.info("{}: DRY RUN — would create inbox and sign up at {}", platform, info["signup_url"])
        return {
            "platform": platform,
            "status": "dry_run",
            "identity": identity,
            "signup_url": info["signup_url"],
        }

    # Create AgentMail inbox
    inbox = mail_client.create_inbox(label=f"jarvis-{platform}")
    email = inbox["email"]
    inbox_id = inbox["inbox_id"]
    logger.info("{}: created inbox email={}", platform, email)

    # Run the platform-specific signup
    signup_fn = SIGNUP_FUNCTIONS[platform]
    result = await signup_fn(mail_client, identity, email, inbox_id)

    return {
        **result,
        "email": email,
        "inbox_id": inbox_id,
        "identity": identity,
        "created_at": datetime.now(UTC).isoformat(),
    }


async def main():
    parser = argparse.ArgumentParser(description="Create platform accounts for JARVIS demo")
    parser.add_argument(
        "--platforms",
        type=str,
        default=",".join(PLATFORMS.keys()),
        help=f"Comma-separated list of platforms ({','.join(PLATFORMS.keys())})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually doing it",
    )
    args = parser.parse_args()

    selected = [p.strip().lower() for p in args.platforms.split(",")]
    invalid = [p for p in selected if p not in PLATFORMS]
    if invalid:
        logger.error("Unknown platforms: {}. Valid: {}", invalid, list(PLATFORMS.keys()))
        sys.exit(1)

    settings = get_settings()

    # Check required API keys
    if not settings.agentmail_api_key:
        logger.error(
            "AGENTMAIL_API_KEY not set. Get one at https://agentmail.to and add to .env"
        )
        sys.exit(1)

    if not settings.browser_use_api_key:
        logger.error(
            "BROWSER_USE_API_KEY not set. Get one at https://browser-use.com and add to .env"
        )
        sys.exit(1)

    # Ensure Browser Use SDK picks up the key
    os.environ["BROWSER_USE_API_KEY"] = settings.browser_use_api_key

    from agents.agentmail_client import AgentMailClient

    mail_client = AgentMailClient(api_key=settings.agentmail_api_key)

    logger.info("Creating accounts for platforms: {}", selected)
    if args.dry_run:
        logger.info("DRY RUN mode — no accounts will actually be created")

    # Run all platform signups in parallel
    tasks = [
        create_account_for_platform(platform, mail_client, dry_run=args.dry_run)
        for platform in selected
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results and save
    accounts = _load_accounts()
    summary = []

    for platform, result in zip(selected, results):
        if isinstance(result, Exception):
            logger.error("{}: failed with exception: {}", platform, result)
            summary.append({"platform": platform, "status": "exception", "error": str(result)})
            continue

        summary.append(result)
        if result.get("status") not in ("dry_run", "exception"):
            accounts[platform] = result

    if not args.dry_run:
        _save_accounts(accounts)

    # Print summary
    logger.info("--- Account Creation Summary ---")
    for entry in summary:
        status = entry.get("status", "unknown")
        platform = entry.get("platform", "?")
        email = entry.get("email", "n/a")
        logger.info("  {}: status={} email={}", platform, status, email)


if __name__ == "__main__":
    asyncio.run(main())
