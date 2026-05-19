"""Shared data models for the Tribbles multiplayer game server.

This module defines the core dataclasses used to represent in-memory game state,
player state, card instances, disconnection tracking, and summary objects for
deck and game session listings.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class CardInstance:
    """Represents a single card instance within a game.

    Attributes:
        card_id: Unique identifier for the card in the database.
        card_name: Display name of the card.
        denomination: Numeric value of the card (1, 10, 100, 1000, 10000, or 100000).
        power_text: The power or ability text on the card.
        expansion_id: ID of the expansion this card belongs to.
    """

    card_id: int
    card_name: str
    denomination: int
    power_text: str
    expansion_id: int


@dataclass
class PlayerState:
    """Represents the full state of a player within an active game.

    Attributes:
        player_id: Unique identifier for the player.
        username: Display name of the player.
        is_computer: True if this is a computer-controlled player.
        hand: Cards currently held by the player (not visible to others).
        draw_deck: Face-down stack of cards the player draws from.
        play_pile: Face-up stack of cards the player has played this round.
        discard_pile: Face-up stack of cards the player has discarded.
        cumulative_score: Total score accumulated across all rounds.
        is_decked: True if the player cannot draw and is eliminated from the round.
        has_gone_out: True if the player has emptied their hand this round.
        seat_position: Position at the virtual table (1 through player count).
        score_target_by: Player ID of whoever used the Score power on this player.
        borrowed_cards: Cards borrowed via Assimilate, with original owner IDs.
        time_warp_reductions: Denominations of Time Warp cards in the play pile.
    """

    player_id: int
    username: str
    is_computer: bool
    hand: List[CardInstance] = field(default_factory=list)
    draw_deck: List[CardInstance] = field(default_factory=list)
    play_pile: List[CardInstance] = field(default_factory=list)
    discard_pile: List[CardInstance] = field(default_factory=list)
    cumulative_score: int = 0
    is_decked: bool = False
    has_gone_out: bool = False
    seat_position: int = 0
    # Transient state for power effects
    score_target_by: Optional[int] = None
    borrowed_cards: List[Tuple[CardInstance, int]] = field(default_factory=list)
    time_warp_reductions: Set[int] = field(default_factory=set)


@dataclass
class GameState:
    """Represents the complete state of an active game session.

    Attributes:
        game_id: Unique identifier for this game session.
        players: List of player states ordered by seat position.
        spectators: List of player IDs watching the game.
        current_player_index: Index into the players list for the active player.
        direction: Play direction (1 = clockwise, -1 = counterclockwise).
        current_sequence: The current expected denomination to be played.
        last_played_denomination: Denomination of the most recently played card.
        sequence_broken: True after a pass, allowing a 1-denomination card.
        round_number: Current round number (1-indexed).
        frozen_powers: Map of power names to the player index when freeze expires.
        game_status: Current status ("active", "round_end", or "completed").
        reconnection_timeout: Seconds to wait before activating AI substitute.
    """

    game_id: str
    players: List[PlayerState] = field(default_factory=list)
    spectators: List[int] = field(default_factory=list)
    current_player_index: int = 0
    direction: int = 1
    current_sequence: int = 1
    last_played_denomination: Optional[int] = None
    sequence_broken: bool = False
    round_number: int = 1
    frozen_powers: Dict[str, int] = field(default_factory=dict)
    game_status: str = "active"
    reconnection_timeout: int = 30


@dataclass
class DisconnectionState:
    """Tracks disconnection status for a player within a game session.

    Attributes:
        player_id: Unique identifier for the disconnected player.
        is_disconnected: True when connection lost, False when reconnected.
        disconnected_at: Server timestamp when disconnection was detected.
        ai_substitute_active: True after reconnection_timeout elapses without reconnect.
    """

    player_id: int
    is_disconnected: bool = False
    disconnected_at: Optional[float] = None
    ai_substitute_active: bool = False


@dataclass
class DeckSummary:
    """Summary information for a deck, used in listing endpoints.

    Attributes:
        deck_id: Unique identifier for the deck.
        deck_name: Display name of the deck.
        owner_player_id: Player ID of the deck owner.
        is_public: True if the deck is publicly visible.
        total_card_count: Total number of cards in the deck (sum of quantities).
    """

    deck_id: int
    deck_name: str
    owner_player_id: int
    is_public: bool
    total_card_count: int


@dataclass
class GameSessionSummary:
    """Summary information for a game session, used in lobby listings.

    Attributes:
        session_id: Unique identifier for the game session.
        creator_player_id: Player ID of the session creator.
        player_count: Total number of player slots (4-8).
        current_player_count: Number of human players currently joined.
        status: Current session status (e.g., "waiting", "active", "completed").
        players_joined: List of usernames of players who have joined.
    """

    session_id: str
    creator_player_id: int
    player_count: int
    current_player_count: int
    status: str
    players_joined: List[str] = field(default_factory=list)
