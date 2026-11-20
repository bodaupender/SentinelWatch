"""Administrative commands for bootstrapping a SentinelWatch installation."""

import argparse
import asyncio
import getpass
import os
import re
import secrets
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import func, select

from .auth.password import hash_password
from .config import BackendConfig, set_config
from .database import close_database, get_db_session, init_database
from .models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    OrganizationStatus,
    User,
)
from .models.user import UserRole, UserStatus


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2].parent


def _load_installation(config_path: str | None) -> Path:
    root = _project_root()
    load_dotenv(root / ".env", override=False)
    backend_dir = root / "backend"
    selected_config = Path(config_path).resolve() if config_path else backend_dir / "config" / "backend.yaml"
    if not selected_config.exists():
        raise FileNotFoundError(f"Backend configuration not found: {selected_config}")
    os.chdir(backend_dir)
    set_config(BackendConfig.load(selected_config))
    return root


def _slug(value: str) -> str:
    parts = re.findall(r"[a-z0-9]+", value.lower())
    return "-".join(parts)[:80].strip("-") or "sentinelwatch"


async def _create_owner() -> None:
    await init_database()
    try:
        async with get_db_session() as db:
            user_count = await db.scalar(select(func.count(User.id))) or 0
            if user_count:
                raise RuntimeError(
                    "An account already exists. Owner bootstrap is only available before the first account is created."
                )

            active_organizations = (await db.execute(
                select(Organization).where(Organization.status == OrganizationStatus.ACTIVE)
            )).scalars().all()
            if len(active_organizations) > 1:
                raise RuntimeError(
                    "Multiple organizations already exist but no users do. Resolve organization ownership manually."
                )

            username = input("Owner username: ").strip()
            email = input("Owner email: ").strip().lower()
            full_name = input("Owner full name: ").strip() or None
            password = getpass.getpass("Owner password (12–128 characters): ")
            confirmation = getpass.getpass("Confirm password: ")
            if password != confirmation:
                raise ValueError("Passwords do not match.")

            # Reuse the public registration schema's username/email/password rules.
            from .api.v1.auth import UserRegistration

            owner_data = UserRegistration(
                username=username,
                email=email,
                full_name=full_name,
                password=password,
            )
            organization = active_organizations[0] if active_organizations else None
            if organization is None:
                base_slug = _slug(owner_data.username)
                organization = Organization(
                    name=f"{owner_data.full_name or owner_data.username}'s Organization",
                    slug=f"{base_slug}-{secrets.token_hex(4)}",
                )
                db.add(organization)
                await db.flush()

            owner = User(
                username=owner_data.username,
                email=str(owner_data.email).lower(),
                full_name=owner_data.full_name,
                password_hash=hash_password(owner_data.password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
            db.add(owner)
            await db.flush()
            db.add(OrganizationMembership(
                user_id=owner.id,
                organization_id=organization.id,
                role=OrganizationRole.OWNER,
            ))
            await db.commit()
            print(f"Owner account '{owner.username}' created for organization '{organization.name}'.")
            print("Sign in through the SentinelWatch dashboard. The password was not written to a file.")
    finally:
        await close_database()


def main() -> None:
    parser = argparse.ArgumentParser(prog="sentinelwatch-backend")
    subparsers = parser.add_subparsers(dest="command", required=True)
    owner_parser = subparsers.add_parser(
        "create-owner",
        help="Create the first local owner account before anyone can sign in",
    )
    owner_parser.add_argument(
        "--config",
        help="Path to backend.yaml (defaults to backend/config/backend.yaml)",
    )
    args = parser.parse_args()
    _load_installation(args.config)
    asyncio.run(_create_owner())


if __name__ == "__main__":
    main()
