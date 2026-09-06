"""Composition root shared by the CLI and web interface."""

from pathlib import Path

from project_reminders.application.services import PortfolioService
from project_reminders.infrastructure.json_store import JsonPortfolioRepository


def build_service(root: Path) -> PortfolioService:
    """Build the application service for one repository root."""

    return PortfolioService(JsonPortfolioRepository(root / "data" / "projects.json"))
