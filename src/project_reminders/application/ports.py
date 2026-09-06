"""Interfaces implemented by infrastructure adapters."""

from typing import Protocol

from project_reminders.domain.models import Portfolio


class PortfolioRepository(Protocol):
    """Persistence boundary for the portfolio."""

    def load(self) -> Portfolio:
        """Load the current portfolio."""
        ...

    def save(self, portfolio: Portfolio) -> None:
        """Persist the complete portfolio."""
        ...
