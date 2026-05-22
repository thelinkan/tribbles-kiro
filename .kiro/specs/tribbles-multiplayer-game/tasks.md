# Implementation Plan: Tribbles Multiplayer Game

## Overview

This plan implements a networked, turn-based card game system with a Python/asyncio WebSocket server (Raspberry Pi) and a Godot 4/GDScript client (Windows/Linux). The implementation proceeds from foundational infrastructure (database, project structure) through core game logic, card powers, and finally client UI and integration wiring.

## Tasks

- [x] 1. Set up server project structure and database schema
  - [x] 1.1 Create Python server project with async WebSocket foundation
    - Create `server/` directory with `pyproject.toml` (dependencies: websockets, asyncio, aiomysql, pytest, hypothesis)
    - Create `server/src/` package structure: `auth/`, `cards/`, `decks/`, `lobby/`, `game/`, `scoring/`, `ai/`, `protocol/`
    - Create `server/src/main.py` entry point with asyncio WebSocket server skeleton
    - Create `server/src/protocol/messages.py` with message type constants and JSON serialisation helpers
    - Create `server/src/protocol/handler.py` with WebSocket message router dispatching to services
    - _Requirements: 18.1, 18.2, 20.7_

  - [x] 1.2 Create MariaDB schema and migration script
    - Create `server/db/schema.sql` with all tables: players, sessions, expansions, cards, decks, deck_cards
    - Include foreign keys, indexes, and constraints as defined in the design
    - Create `server/db/migrate.py` script to apply schema to a MariaDB instance
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6_

  - [x] 1.3 Create expansion seed script framework and data files
    - Create `server/db/seeds/` directory with one seed script per expansion
    - Each script reads from a JSON data file and inserts expansion + card records
    - Create placeholder JSON data files for all six expansions with correct structure (card_name, denomination, power_text, card_number, image_filename)
    - _Requirements: 2.7, 2.6_

  - [x] 1.4 Create shared data models and type definitions
    - Create `server/src/models.py` with Python dataclasses: `CardInstance`, `PlayerState`, `GameState`, `DisconnectionState`, `DeckSummary`, `GameSessionSummary`
    - Include full type annotations on all fields
    - _Requirements: 18.2_


- [x] 2. Implement Auth_Service
  - [x] 2.1 Implement player registration and login
    - Create `server/src/auth/service.py` with `Auth_Service` class
    - Implement `register(username, password, email)` — hash password with bcrypt, insert into players table, return PlayerID
    - Implement `login(username, password)` — verify credentials, generate session token, insert into sessions table, return token
    - Implement `validate_token(token)` — check sessions table, verify not expired, return PlayerID
    - Implement `invalidate_token(token)` — delete from sessions table
    - Return generic error on invalid login without revealing which field failed
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x]* 2.2 Write property tests for Auth_Service
    - **Property 1: Registration and login round-trip**
    - **Property 2: Invalid login does not reveal which field is wrong**
    - **Property 3: Invalidated token is rejected**
    - **Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6**

  - [x]* 2.3 Write unit tests for Auth_Service
    - Test duplicate username registration returns error
    - Test expired token rejection
    - Test password hashing is not reversible
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 3. Implement Card_Repository
  - [x] 3.1 Implement card catalogue access
    - Create `server/src/cards/repository.py` with `Card_Repository` class
    - Implement `search_cards(filters: CardFilter)` — build dynamic SQL query from filter params (denomination, power_name, expansion, card_name_substring)
    - Implement `get_card(card_id)` — single card lookup
    - Implement `get_all_expansions()` — return all expansion records
    - Ensure compound powers are treated as distinct identities in search
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.8_

  - [x]* 3.2 Write property tests for Card_Repository
    - **Property 4: Card search filter correctness**
    - **Property 5: Compound powers are distinct from component powers**
    - **Validates: Requirements 2.3, 2.5**

- [x] 4. Implement Deck_Service
  - [x] 4.1 Implement deck CRUD operations
    - Create `server/src/decks/service.py` with `Deck_Service` class
    - Implement `save_deck(player_id, deck_data)` — insert into decks + deck_cards tables, allow any card count
    - Implement `load_deck(player_id, deck_id)` — load deck if owned or public
    - Implement `copy_deck(player_id, source_deck_id)` — copy if owned or public, reject private non-owned
    - Implement `list_decks(player_id)` — list player's own decks
    - Implement `list_public_decks()` — list all public decks
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.10_

  - [x]* 4.2 Write property tests for Deck_Service
    - **Property 6: Deck save/load round-trip**
    - **Property 7: Public deck access**
    - **Property 8: Deck copy produces identical card entries**
    - **Property 9: Private deck copy denied for non-owner**
    - **Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**


- [x] 5. Implement Lobby_Service
  - [x] 5.1 Implement game session creation and joining
    - Create `server/src/lobby/service.py` with `Lobby_Service` class
    - Implement `create_game(player_id, deck_id, player_count)` — validate player_count 4–8, validate deck ≥ 35 cards, create session in waiting state
    - Implement `join_game(player_id, deck_id, session_id)` — validate session is waiting and not full, validate deck ≥ 35 cards, add player
    - Implement `start_game(player_id, session_id)` — fill remaining seats with AI players (random decks), transition to active
    - Implement `list_waiting_games()` and `list_active_games()` — return session summaries
    - Implement `watch_game(player_id, session_id)` — add player as spectator if session is active
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 4.9, 4.10, 4.11, 22.1_

  - [x]* 5.2 Write property tests for Lobby_Service
    - **Property 10: Game session creation with valid player count**
    - **Property 11: Join game adds player when session is waiting and not full**
    - **Property 12: Join game rejected for non-waiting or full session**
    - **Property 13: Start game fills remaining seats with AI**
    - **Property 71: Deck size enforcement at game creation and joining**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6, 4.9, 4.10**

- [x] 6. Checkpoint — Foundation services complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Game_Engine — Initialisation and turn mechanics
  - [x] 7.1 Implement game initialisation
    - Create `server/src/game/engine.py` with `Game_Engine` class
    - Implement `initialise_game(session)` — assign random seat positions, select random starting player, shuffle draw decks, deal 7 cards each, set direction clockwise, sequence to 1
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x]* 7.2 Write property test for game initialisation
    - **Property 15: Game initialisation invariants**
    - **Validates: Requirements 5.1, 5.2, 5.4**

  - [x] 7.3 Implement core turn mechanics
    - Implement `process_action(game_id, player_id, action)` for play_card and draw_card actions
    - Validate turn: only active player can act
    - Play card: validate denomination matches sequence (or Clone matches last_played), move card to play pile, advance sequence
    - Draw card: move top of draw deck to hand, check if matches sequence, offer play-or-keep choice
    - Track last_played_denomination separately from sequence
    - Handle sequence break: allow next player to play 1-denomination card after a pass
    - Handle 100000 → 1 sequence wrap
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9_

  - [x]* 7.4 Write property tests for turn mechanics
    - **Property 16: Turn validity — play or draw**
    - **Property 17: Playing a card advances sequence correctly**
    - **Property 18: Drawing a card moves top of draw deck to hand**
    - **Property 19: Drawn matching card offers play-or-keep choice**
    - **Property 20: Empty draw deck causes decked state**
    - **Property 21: Last played denomination tracked independently**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9**

  - [x] 7.5 Implement decked state logic
    - When draw deck is empty and draw required, mark player as decked
    - Move all hand cards to discard pile immediately
    - Prevent scoring to/from decked player (except Antidote)
    - Keep play pile intact for power references
    - Allow decked player to be targeted by powers
    - When all but one player decked, last player goes out (hand → play pile)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x]* 7.6 Write property tests for decked state
    - **Property 22: Decked state invariants**
    - **Property 23: Decked player is valid power target**
    - **Property 24: Last non-decked player goes out**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**


- [x] 8. Implement Score_Service and end-of-round logic
  - [x] 8.1 Implement round scoring and round transitions
    - Create `server/src/scoring/service.py` with `Score_Service` class
    - Implement `calculate_round_scores(game_state)` — sum denominations in play pile for players who went out
    - Implement `apply_immediate_score(game_id, player_id, points)` — add points to cumulative score
    - Create `server/src/game/round_manager.py` with `RoundManager` class
    - Implement end-of-round: move non-goers' hands to discard, shuffle play piles into draw decks, deal 7 cards for new round
    - Handle decked player round transition: play pile ≥ 7 cards → reshuffled draw deck; < 7 → sit out
    - Determine starting player for new round (single go-out → that player; multiple → lowest round score)
    - Reset sequence to 1 and direction to clockwise each new round
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 7.6, 7.7_

  - [x]* 8.2 Write property tests for scoring and round transitions
    - **Property 25: Decked player round transition**
    - **Property 26: End-of-round scoring and cleanup**
    - **Property 27: New round starting player selection**
    - **Validates: Requirements 7.6, 7.7, 8.1, 8.2, 8.3, 8.4, 8.7, 8.8**

  - [x] 8.3 Implement game end condition
    - End game after 5 rounds completed
    - Transition session to completed state
    - Determine winner (highest cumulative score)
    - Broadcast final scores to all players
    - _Requirements: 16.1, 16.2_

  - [x]* 8.4 Write property test for game end
    - **Property 65: Game ends after five rounds**
    - **Validates: Requirements 16.1, 16.2**

- [x] 9. Checkpoint — Core game loop complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Card Powers — Base Set
  - [x] 10.1 Implement PowerResolver framework and base powers
    - Create `server/src/game/powers/resolver.py` with `PowerResolver` class
    - Implement power activation prompt logic (activate or decline)
    - Implement Discard power: prompt player to choose card from hand → move to discard pile
    - Implement Go power: grant additional turn, advance sequence, keep active player
    - Implement Skip power: skip next player in current direction
    - Implement Poison power: prompt target selection, discard top of target's draw deck, score denomination
    - Implement Rescue power: browse discard pile, select card → top of draw deck or play if matches sequence
    - Implement Reverse power: toggle direction clockwise ↔ counterclockwise
    - Implement Clone power: allow play when denomination matches last_played_denomination
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

  - [x]* 10.2 Write property tests for base powers
    - **Property 28: Power activation choice**
    - **Property 29: Discard power effect**
    - **Property 30: Go power grants additional turn**
    - **Property 31: Skip power skips next player**
    - **Property 32: Poison power scores from opponent's draw deck**
    - **Property 33: Rescue power recovers from discard pile**
    - **Property 34: Reverse power toggles direction (idempotent pair)**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8**

- [x] 11. Implement Card Powers — The Trouble with Tribbles Expansion
  - [x] 11.1 Implement Bonus power scoring
    - In `Score_Service`, check for Bonus cards at denominations 1, 10, 100, 1000 in play pile of non-decked players
    - Award 100000 bonus points when all four are present
    - _Requirements: 10.1_

  - [x]* 11.2 Write property test for Bonus scoring
    - **Property 35: Bonus scoring condition**
    - **Validates: Requirements 10.1**


- [x] 12. Implement Card Powers — More Tribbles More Troubles Expansion
  - [x] 12.1 Implement expansion 3 powers
    - Implement Antidote power: when Poison targets a player whose top draw card has Antidote, reverse scoring and allow hand placement under draw deck
    - Implement Copy power: apply game text of top card of any other player's play pile (cannot copy Quadruple)
    - Implement Cycle power: place one hand card under draw deck, draw one from top
    - Implement Draw power: prompt target selection, target draws one card from their draw deck
    - Implement Exchange power: discard one hand card, take one card from discard pile
    - Implement Kill power: prompt target selection, discard top of target's play pile
    - Implement Recycle power: prompt target selection, shuffle target's discard pile into their draw deck
    - Implement Replay power: search own play pile, play one card again as if from hand
    - Implement Score power: mark target, if target plays next turn → activator gains that card's denomination
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9_

  - [x]* 12.2 Write property tests for expansion 3 powers
    - **Property 36: Antidote reverses Poison scoring**
    - **Property 37: Copy power applies target's top play pile card effect**
    - **Property 38: Cycle preserves hand size**
    - **Property 39: Draw power increases target's hand**
    - **Property 40: Exchange swaps hand card with discard card**
    - **Property 41: Kill removes top of target's play pile**
    - **Property 42: Recycle merges discard into draw deck**
    - **Property 43: Score power delayed scoring**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.9**

- [x] 13. Implement Card Powers — No Tribble at All Expansion
  - [x] 13.1 Implement compound power rules and expansion 4 powers
    - Implement compound power activation logic: both powers activate together unless one is Clone
    - Implement Battle power: reveal top 3 of both players' draw decks, higher total wins all 6 cards under play pile, loser discards
    - Implement Evolve power: count hand, move hand to discard, draw same count from deck
    - Implement Freeze power: record named power as frozen until end of active player's next turn, reject frozen power plays
    - Implement Mutate power: count play pile, shuffle pile into deck, move same count from deck to pile
    - Implement Process power: draw 3 from deck, prompt player to place 2 under draw deck
    - Implement Quadruple scoring: card worth 40000 instead of 10000 for round winner
    - Implement Safety end-of-round: hand shuffled into draw deck instead of discard pile
    - Implement Tally scoring split: half denomination to scorer, half to Tally owner
    - Implement Toxin power: for each Discard card in opponents' play piles, reveal top of their draw deck; active player chooses one to score; all revealed go to owners' hands
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.11, 12.12, 12.13_

  - [x]* 13.2 Write property tests for expansion 4 powers
    - **Property 44: Compound power activation rules**
    - **Property 45: Battle resolution**
    - **Property 46: Evolve preserves hand count**
    - **Property 47: Freeze prevents playing named power**
    - **Property 48: Mutate preserves play pile count**
    - **Property 49: Process net hand gain**
    - **Property 50: Quadruple scoring modifier**
    - **Property 51: Safety end-of-round modifier**
    - **Property 52: Tally scoring split**
    - **Property 53: Toxin reveals cards per Discard count**
    - **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.11, 12.12, 12.13**


- [x] 14. Implement Card Powers — Trials and Tribble-ations Expansion
  - [x] 14.1 Implement expansion 5 powers
    - Implement Avalanche power: if active player has ≥ 4 other cards in hand, all players discard one card, active player discards one additional
    - Implement Famine power: set next sequence denomination to 1 regardless of current position
    - Implement Stampede power: all players may play one card of current sequence denomination in turn order; only active player's card power may activate
    - Implement Time Warp power: at round end, reduce next-round hand size by number of unique Time Warp denominations in play pile (min 1 card dealt), does not stack same denomination
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x]* 14.2 Write property tests for expansion 5 powers
    - **Property 54: Avalanche conditional discard**
    - **Property 55: Famine resets sequence to 1**
    - **Property 56: Stampede allows all to play, only active power triggers**
    - **Property 57: Time Warp reduces next round hand size**
    - **Validates: Requirements 13.1, 13.2, 13.3, 13.4**

- [x] 15. Implement Card Powers — Nothing But Tribble Expansion
  - [x] 15.1 Implement expansion 6 powers
    - Implement Advance power: playable in place of 1-denomination card after sequence break
    - Implement Assimilate power: move top of target's draw deck to active player's play pile as borrowed; return at round end
    - Implement Convert power: place Convert card under draw deck, move top of draw deck to play pile
    - Implement IDIC scoring: 10000 points per unique power in play pile for each IDIC card of distinct denomination (no stacking same denomination)
    - Implement Masaka power: all players place hands under draw decks, deal 3 cards to each player
    - Implement Scan power: reveal top 3 of own draw deck to self only, reorder and place on top or bottom
    - Implement Utilize power: chosen opponent (≥ 2 cards in hand) randomly places one hand card on their play pile; active player scores that card's denomination
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_

  - [x]* 15.2 Write property tests for expansion 6 powers
    - **Property 58: Advance playable after sequence break**
    - **Property 59: Assimilate borrows and returns**
    - **Property 60: Convert transforms card placement**
    - **Property 61: IDIC scoring calculation**
    - **Property 62: Masaka replaces all hands with 3 cards**
    - **Property 63: Scan preserves draw deck size**
    - **Property 64: Utilize forces opponent card to play pile and scores**
    - **Validates: Requirements 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7**

- [x] 16. Checkpoint — All card powers implemented
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Implement AI_Controller
  - [x] 17.1 Implement computer player decision-making
    - Create `server/src/ai/controller.py` with `AI_Controller` class
    - Implement `choose_action(game_state, player_id)` — select valid play from hand or draw when no valid play available
    - Strategy: prefer playing cards that advance sequence, activate beneficial powers, target weakest opponent for offensive powers
    - Ensure all chosen actions pass Game_Engine validation
    - Used for both permanent computer players and AI_Substitute seats
    - _Requirements: 4.7, 4.8, 21.4, 21.5_

  - [x]* 17.2 Write property test for AI actions
    - **Property 14: AI actions are always valid**
    - **Validates: Requirements 4.7, 4.8**


- [x] 18. Implement Disconnection, Reconnection, and Spectating
  - [x] 18.1 Implement player disconnection and AI_Substitute logic
    - Create `server/src/game/disconnection.py` with disconnection tracking
    - Detect WebSocket disconnection, mark player as disconnected with timestamp
    - During grace period: skip disconnected player's turn without decking
    - After Reconnection_Timeout: activate AI_Substitute using AI_Controller on player's existing state
    - Support configurable timeout per session (default 30 seconds)
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5_

  - [x] 18.2 Implement player reconnection and state sync
    - On reconnect with valid session token: remove AI_Substitute, restore player control
    - Send `reconnect_state_sync` message with full game state (hand, piles, scores, sequence, direction, active player)
    - Broadcast `reconnect_notify` to all other players
    - Handle game ending while disconnected: record final score, allow viewing results on reconnect
    - _Requirements: 21.6, 21.7, 21.8_

  - [x]* 18.3 Write property tests for disconnection/reconnection
    - **Property 66: Disconnection marks player and starts grace period**
    - **Property 67: Disconnected player's turn is skipped without decking**
    - **Property 68: AI_Substitute activation preserves player state**
    - **Property 69: Reconnection restores player control with full state sync**
    - **Property 70: Game ending with disconnected player records score in results**
    - **Validates: Requirements 21.1, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8**

  - [x] 18.4 Implement spectator state broadcasting
    - Implement `get_spectator_visible_state(game_id)` — return all public state without hand contents
    - Send `spectator_state_update` to all spectators on game state changes
    - Send `spectator_count_update` to all players and spectators when spectator count changes
    - Implement `leave_spectate` — remove spectator without affecting game state
    - Reject any game actions from spectator player IDs
    - _Requirements: 22.1, 22.2, 22.3, 22.5, 22.6, 22.7_

  - [x]* 18.5 Write property tests for spectating
    - **Property 72: Spectator receives only public state**
    - **Property 73: Spectator cannot perform game actions**
    - **Property 74: Spectator leaving does not affect game state**
    - **Validates: Requirements 22.2, 22.3, 22.5, 22.7**

- [x] 19. Checkpoint — Server logic complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 20. Implement Hypothesis test generators
  - [x] 20.1 Create shared property test strategies and generators
    - Create `server/tests/conftest.py` with shared fixtures
    - Create `server/tests/strategies.py` with Hypothesis custom strategies:
      - `valid_game_state()` — internally consistent GameState with valid player states
      - `valid_hand(min_cards, max_cards)` — random hand of CardInstance objects
      - `valid_play_pile()` — random play pile
      - `valid_deck_data()` — random deck save data with card entries
      - `valid_credentials()` — random valid username/password/email
      - `card_with_power(power_name)` — card with specific power
      - `compound_power_card()` — compound power card
      - `disconnected_game_state()` — game state with disconnected players
    - Configure minimum 100 examples per property test
    - _Requirements: 18.3_


- [x] 21. Set up Godot 4 client project structure
  - [x] 21.1 Create Godot project and scene hierarchy
    - Create `client/` directory with `project.godot` configuration
    - Create scene files: `LoginScreen.tscn`, `MainMenu.tscn`, `DeckBuilder.tscn`, `LobbyScreen.tscn`, `GameTable.tscn`, `SpectatorView.tscn`, `EndOfRoundScreen.tscn`, `EndOfGameScreen.tscn`, `SettingsScreen.tscn`
    - Create autoload singleton script `NetworkClient.gd` for WebSocket management
    - Set up GUT (Godot Unit Test) addon for client testing
    - _Requirements: 1.7, 19.2_

  - [x] 21.2 Implement NetworkClient autoload singleton
    - Create `client/scripts/autoload/NetworkClient.gd`
    - Implement WebSocket connection management (connect, disconnect, reconnect with exponential backoff)
    - Implement JSON message serialisation/deserialisation matching server protocol
    - Implement message routing via signals for each message type
    - Store session token after login
    - Handle connection lost: display reconnection overlay
    - _Requirements: 1.9, 21.6_

  - [x] 21.3 Set up localisation system
    - Create `client/translations/` directory with CSV translation files
    - Define translation keys for all UI strings
    - Implement English (default) and Swedish translations
    - Configure Godot's built-in TranslationServer
    - Persist language preference to user settings file
    - _Requirements: 17.1, 17.2, 17.3_

- [x] 22. Implement Client — Login and Registration screens
  - [x] 22.1 Implement LoginScreen and registration flow
    - Create `client/scripts/LoginScreen.gd`
    - UI elements: server address field, username field, password field, login button, register toggle/link
    - Registration mode: additional email field, register button
    - On login success: store token in NetworkClient, navigate to MainMenu
    - On error: display localised error message, do not clear username field
    - _Requirements: 1.7, 1.8, 1.9, 1.10_

- [x] 23. Implement Client — Deck Builder
  - [x] 23.1 Implement DeckBuilder screen
    - Create `client/scripts/DeckBuilder.gd`
    - Card search panel: filter by denomination, power, expansion, name substring
    - Deck editing panel: list of cards with quantities, add/remove buttons
    - Display total card count at all times
    - Visual indicator when deck < 35 cards (not legal for game use)
    - Remove card entry when quantity set to zero
    - Save/Load/Copy deck buttons communicating with server via NetworkClient
    - _Requirements: 3.8, 3.9, 3.11, 3.12_


- [x] 24. Implement Client — Lobby Screen
  - [x] 24.1 Implement LobbyScreen with game list and actions
    - Create `client/scripts/LobbyScreen.gd`
    - Two-category game list: waiting sessions (joinable) and active sessions (watchable)
    - Create Game button: select deck (prevent < 35 cards), choose player count (4–8), send create_game
    - Join Game button: select deck (prevent < 35 cards), send join_game for selected session
    - Watch Game button: send watch_game for selected active session
    - Display session details: player count, current players joined, session ID
    - _Requirements: 4.5, 4.12, 22.1_

- [x] 25. Implement Client — Game Table
  - [x] 25.1 Implement GameTable scene and player display
    - Create `client/scripts/GameTable.gd`
    - Arrange all players around virtual table with local player at bottom
    - Display each player's draw deck (face-down with count), discard pile (top card visible), play pile (top card visible)
    - Hover over pile: show enlarged top card
    - Display current active player indicator, sequence denomination, play direction
    - Display cumulative scores at each player position
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.7_

  - [x] 25.2 Implement hand display and turn interaction
    - Display local player's hand cards face-up
    - Highlight valid playable cards when it is local player's turn
    - Handle card selection → send play_card action
    - Handle draw button → send draw_card action
    - Handle power activation prompts: display options, send power_choice
    - Handle drawn card display with Accept button (for non-matching draws)
    - _Requirements: 15.5, 15.6, 6.5, 6.6, 9.1_

  - [x] 25.3 Implement game state update handling
    - Listen for `game_state_update` messages from NetworkClient
    - Update all visual elements: piles, hands, scores, active player, sequence, direction
    - Handle `prompt` messages: display power activation choices
    - Handle `disconnect_notify`: show disconnected indicator at player position
    - Handle `reconnect_notify`: remove indicator, show brief notification
    - Handle AI_Substitute indicator display
    - Handle `spectator_count_update`: display spectator count
    - _Requirements: 15.4, 21.9, 21.10, 21.11, 22.6_

  - [x] 25.4 Implement SpectatorView scene
    - Create `client/scripts/SpectatorView.gd`
    - Read-only game table: all public info (play piles, discard piles, draw deck counts, scores, sequence, direction, active player)
    - No hand contents displayed, no action buttons
    - Listen for `spectator_state_update` messages
    - Leave button to exit spectating
    - _Requirements: 22.4_

- [x] 26. Implement Client — End of Round and End of Game screens
  - [x] 26.1 Implement EndOfRoundScreen and EndOfGameScreen
    - Create `client/scripts/EndOfRoundScreen.gd` — popup showing each player's round score and cumulative score
    - Create `client/scripts/EndOfGameScreen.gd` — final rankings (highest to lowest), clearly indicate winner
    - Handle `round_end` message: display EndOfRoundScreen
    - Handle `game_end` message: display EndOfGameScreen
    - _Requirements: 8.9, 16.3, 16.4_

- [x] 27. Implement Client — Settings Screen
  - [x] 27.1 Implement SettingsScreen with language selection
    - Create `client/scripts/SettingsScreen.gd`
    - Language dropdown: English, Swedish
    - On selection: update TranslationServer locale, persist preference
    - _Requirements: 17.1, 17.2, 17.3_


- [x] 28. Checkpoint — Client UI complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 29. Integration wiring and WebSocket protocol
  - [x] 29.1 Wire server WebSocket handler to all services
    - Complete `server/src/protocol/handler.py` message routing:
      - `register` / `login` → Auth_Service
      - `create_game` / `join_game` / `start_game` / `watch_game` / `leave_spectate` → Lobby_Service
      - `play_card` / `draw_card` / `power_choice` / `accept_draw` → Game_Engine
      - `reconnect` → Disconnection handler
    - Implement session token validation middleware on all authenticated endpoints
    - Implement `get_visible_state` calls after each game action to broadcast updates
    - Implement spectator state broadcasting on game state changes
    - Implement error response formatting with localised error codes
    - _Requirements: 18.1, 18.2, 20.7_

  - [x] 29.2 Wire client NetworkClient signals to UI scenes
    - Connect NetworkClient signals to appropriate scene handlers
    - LoginScreen: handle login_success, login_error, register_success, register_error signals
    - LobbyScreen: handle game_list_update, join_success, create_success signals
    - GameTable: handle game_state_update, prompt, round_end, game_end, disconnect_notify, reconnect_notify signals
    - SpectatorView: handle spectator_state_update, spectator_count_update signals
    - DeckBuilder: handle deck_list, deck_loaded, save_success signals
    - _Requirements: 1.9, 1.10, 4.5, 15.4_

  - [ ]* 29.3 Write integration tests for WebSocket message round-trips
    - Test full login flow: register → login → receive token → authenticated request
    - Test game lifecycle: create → join → start → play cards → round end → game end
    - Test reconnection flow: disconnect → grace period → reconnect → state sync
    - Test spectator flow: watch → receive updates → leave
    - _Requirements: 18.3_

- [ ] 29.4 Fix gameplay integration issues
  - [x] 29.4.1 Fix hand cards z-order and card sizing
    - Move HandContainer to render above PlayerPositions in the GameTable scene
    - Ensure hand card buttons are always visible and clickable
    - Show only denomination and power name on card buttons (not full rules text)
    - Use an overlapping fan layout for the hand: cards overlap horizontally, with the rightmost card fully visible
    - Fan spacing adjusts dynamically so up to 15 cards fit within the available width
    - Hovered card rises above others and shows full details in tooltip
    - Show full card details on hover/tooltip
    - Move the game info panel (round, direction, sequence, spectator count) to the centre of the screen instead of the top, to avoid overlapping with player positions at the top
    - Adjust player position coordinates so all players (including leftmost, rightmost, and topmost) are fully within the visible screen area with padding
  - [x] 29.4.2 Integrate PowerResolver with play_card flow
    - After a card with an activatable power is played, server should send a prompt to the client asking activate/decline
    - Client should display the prompt overlay and send the power_choice response
    - Server should then process the power effect and continue the turn (including AI turns)
    - Handle multi-step powers (Poison target selection, Discard card choice, etc.)
  - [x] 29.4.3 Fix draw card flow to show drawn card and offer play-or-keep choice
    - Server already sends draw_choice_pending / draw_accept_pending events in the action_result
    - Client needs to detect these events in the action_result and show the drawn card UI
    - For matching draws: show card + Play/Keep buttons
    - For non-matching draws: show card + Accept button

- [ ] 29.5 Toxin power visual card reveal
  - [ ] 29.5.1 Implement positioned Toxin card reveal at player positions
    - When Toxin is activated, show revealed cards visually at each opponent's position on the table
    - Each revealed card should appear as a face-up card image/button near the owning player
    - If AI makes the choice: show revealed cards for 3 seconds before AI picks, then highlight the chosen card for 5 seconds before dismissing
    - If a human player activates in a multiplayer game: after choice is made, show the result to all human players for 5 seconds
    - Use timed animations (Godot Tween or Timer) for the delays
    - Broadcast a "toxin_reveal" event to all players in the game so everyone sees the cards

- [ ] 30. Write client automated tests
  - [ ]* 30.1 Write GUT tests for client scenes
    - Test LoginScreen: scene instantiation, mode toggle, form submission
    - Test DeckBuilder: add/remove cards, quantity changes, card count display, save/load
    - Test GameTable: card display updates, turn highlighting, score rendering
    - Test localisation: all strings render in English and Swedish
    - Test NetworkClient: message serialisation/deserialisation
    - _Requirements: 19.1, 19.2_

- [ ] 31. Final checkpoint — Full system integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (74 properties total)
- Unit tests validate specific examples and edge cases
- Server uses Python with asyncio, websockets, aiomysql, pytest, and Hypothesis
- Client uses Godot 4 / GDScript with GUT for testing
- The server is authoritative — all game logic validation happens server-side
- Card data files (JSON) for seed scripts should be populated with actual Tribbles card data when available

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.4"] },
    { "id": 1, "tasks": ["1.3", "2.1", "21.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1", "21.2", "21.3"] },
    { "id": 3, "tasks": ["3.2", "4.1", "22.1"] },
    { "id": 4, "tasks": ["4.2", "5.1", "23.1"] },
    { "id": 5, "tasks": ["5.2", "7.1", "24.1"] },
    { "id": 6, "tasks": ["7.2", "7.3"] },
    { "id": 7, "tasks": ["7.4", "7.5"] },
    { "id": 8, "tasks": ["7.6", "8.1"] },
    { "id": 9, "tasks": ["8.2", "8.3", "10.1"] },
    { "id": 10, "tasks": ["8.4", "10.2", "11.1"] },
    { "id": 11, "tasks": ["11.2", "12.1"] },
    { "id": 12, "tasks": ["12.2", "13.1"] },
    { "id": 13, "tasks": ["13.2", "14.1"] },
    { "id": 14, "tasks": ["14.2", "15.1"] },
    { "id": 15, "tasks": ["15.2", "17.1"] },
    { "id": 16, "tasks": ["17.2", "18.1", "20.1"] },
    { "id": 17, "tasks": ["18.2", "18.4"] },
    { "id": 18, "tasks": ["18.3", "18.5", "25.1"] },
    { "id": 19, "tasks": ["25.2", "25.3", "25.4"] },
    { "id": 20, "tasks": ["26.1", "27.1"] },
    { "id": 21, "tasks": ["29.1"] },
    { "id": 22, "tasks": ["29.2", "29.3"] },
    { "id": 23, "tasks": ["30.1"] }
  ]
}
```
