"""Shared pytest fixtures and Hypothesis configuration for the Tribbles test suite.

Provides reusable fixtures for core game components and configures Hypothesis
to run a minimum of 100 examples per property test.

**Validates: Requirements 18.3**
"""

import sys
import os

import pytest
from hypothesis import settings, HealthCheck

# Add src and tests to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from game.engine import GameEngine
from game.round_manager import RoundManager
from game.disconnection import DisconnectionManager
from game.spectator import SpectatorManager
from game.powers.resolver import PowerResolver
from scoring.service import ScoreService
from ai.controller import AIController


# ---------------------------------------------------------------------------
# Hypothesis settings profile: minimum 100 examples per property test
# ---------------------------------------------------------------------------

settings.register_profile(
    "ci",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "default",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("default")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def game_engine():
    """Provide a fresh GameEngine instance."""
    return GameEngine()


@pytest.fixture
def score_service():
    """Provide a fresh ScoreService instance."""
    return ScoreService()


@pytest.fixture
def round_manager(score_service):
    """Provide a fresh RoundManager instance with a ScoreService."""
    return RoundManager(score_service=score_service)


@pytest.fixture
def power_resolver(score_service):
    """Provide a fresh PowerResolver instance with a ScoreService."""
    return PowerResolver(score_service=score_service)


@pytest.fixture
def ai_controller():
    """Provide a fresh AIController instance."""
    return AIController()


@pytest.fixture
def disconnection_manager():
    """Provide a fresh DisconnectionManager instance."""
    return DisconnectionManager()


@pytest.fixture
def spectator_manager():
    """Provide a fresh SpectatorManager instance."""
    return SpectatorManager()
