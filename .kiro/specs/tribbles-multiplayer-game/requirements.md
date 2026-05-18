# Requirements Document

## Introduction

Tribbles Multiplayer Game is a networked, turn-based card game system based on the customizable card game Tribbles. The system consists of a Python server designed to run on a Raspberry Pi and a Godot 4 / GDScript client that runs on Windows and Linux. Players create accounts, log in, build decks from the full Tribbles card catalogue (spanning six expansions), and play games with 4–8 participants in real time. The server enforces all game rules, manages persistent data (players, cards, decks, game state), and handles scoring. The client provides a virtual table view, a deck builder, and full game-play interaction. The user interface supports English (default) and Swedish.

---

## Glossary

- **Server**: The Python back-end application running on a Raspberry Pi that manages authentication, data storage, game logic, and rule enforcement.
- **Client**: The Godot 4 / GDScript application running on Windows or Linux that provides the player-facing user interface.
- **Player**: A registered user who can log in, build decks, and participate in games.
- **Card**: A single Tribbles card with a denomination, a power (or compound power), a card number, an expansion, and an image reference.
- **Denomination**: The numeric value printed on a card — one of: 1, 10, 100, 1000, 10000, or 100000.
- **Power**: The special ability text on a card (e.g., Go, Skip, Poison). Compound powers are two powers on one card (e.g., Clone & Reverse).
- **Expansion**: A named set of cards, stored as a record in the expansions table. Valid expansions: Base Set, The Trouble with Tribbles, More Tribbles More Troubles, No Tribble at All, Trials and Tribble-ations, Nothing But Tribble.
- **Deck**: A named, player-owned collection of cards with specified quantities, stored on the server.
- **Draw Deck**: The face-down stack of cards a player draws from during a game.
- **Play Pile**: The face-up stack of cards a player has played during the current round.
- **Discard Pile**: The face-up stack of cards a player has discarded.
- **Hand**: The set of cards currently held by a player (not visible to other players).
- **Sequence**: The current expected denomination to be played next (cycles 1 → 10 → 100 → 1000 → 10000 → 100000 → 1 → …).
- **Direction**: The current order of play — clockwise or counterclockwise.
- **Round**: One complete cycle of play from the first card played until one or more players go out (or all remaining players are decked).
- **Go Out**: The event when a player empties their hand, triggering end-of-round scoring.
- **Decked**: The state of a player who cannot draw a card when required; that player is eliminated from the current round.
- **Game**: A session consisting of one or more rounds, ending when a predetermined score threshold or condition is met (to be configured at game creation).
- **Sequence Break**: A pass event after which the next player may choose to play a 1-denomination card instead of the next card in sequence.
- **Compound Power**: A card power consisting of two individual powers combined on one card.
- **Game_Engine**: The server-side component that enforces all game rules and manages game state.
- **Auth_Service**: The server-side component that handles player registration and authentication.
- **Deck_Service**: The server-side component that handles deck storage and retrieval.
- **Card_Repository**: The server-side component that manages the card catalogue.
- **Lobby_Service**: The server-side component that manages game creation and player joining.
- **Score_Service**: The server-side component that calculates and records scores.
- **DB**: The MariaDB relational database used for persistent storage.
- **UI**: The client-side user interface presented to the player.
- **Legal_Deck**: A deck containing at least 35 cards (sum of all card quantities), which is the minimum required to use a deck in a game.
- **Disconnection**: The loss of network connectivity between a player's Client and the Server during an active game session.
- **Reconnection_Timeout**: The configurable duration (in seconds) that the Server waits for a disconnected player to reconnect before assigning a computer-controlled player to that player's seat.
- **AI_Substitute**: A computer-controlled player that temporarily controls a disconnected player's seat, using the same automated decision-making strategy as computer players created at game start.
- **Spectator**: A logged-in player who is observing an active game session without participating as a player.

---

## Requirements

### Requirement 1: Player Registration and Authentication

**User Story:** As a new player, I want to create an account and log in, so that I can access the game and have my decks and scores saved.

#### Acceptance Criteria

1. THE Auth_Service SHALL store each player record with at minimum: a unique username, a hashed password, an email address, and a creation timestamp.
2. WHEN a registration request is received with a unique username and a valid password, THE Auth_Service SHALL create a new player record and return a success response.
3. WHEN a registration request is received with a username that already exists, THE Auth_Service SHALL return an error response indicating the username is taken.
4. WHEN a login request is received with a valid username and correct password, THE Auth_Service SHALL return a session token valid for the duration of the session.
5. WHEN a login request is received with an invalid username or incorrect password, THE Auth_Service SHALL return an authentication failure response without revealing which field is incorrect.
6. WHEN a session token expires or is invalidated, THE Auth_Service SHALL reject subsequent requests using that token and return an unauthorised error response.
7. THE Client SHALL provide a login screen allowing the player to enter a server address, username, and password, and SHALL provide a toggle or link to switch between login mode and registration mode.
8. WHEN the player switches to registration mode, THE Client SHALL display a registration form collecting username, password, email address, and server address.
9. WHEN the player submits valid credentials on the login screen, THE Client SHALL store the session token and navigate to the main menu.
10. IF the server returns an authentication failure, THEN THE Client SHALL display an error message without clearing the username field.

---

### Requirement 2: Card Catalogue Management

**User Story:** As a system administrator, I want all Tribbles cards from all expansions stored in the database, so that players can browse and use them in decks and games.

#### Acceptance Criteria

1. THE Card_Repository SHALL store each card record with: card name, denomination (1 / 10 / 100 / 1000 / 10000 / 100000), power text, card number, expansion_id (foreign key referencing the expansions table), and image filename.
2. THE Card_Repository SHALL contain all cards defined in the six expansions: Base Set, The Trouble with Tribbles, More Tribbles More Troubles, No Tribble at All, Trials and Tribble-ations, and Nothing But Tribble.
3. WHEN a card search request is received with filter parameters (denomination, power name, expansion, or card name substring), THE Card_Repository SHALL return only cards matching all supplied filter criteria.
4. WHEN a card search request is received with no filter parameters, THE Card_Repository SHALL return all cards in the catalogue.
5. THE Card_Repository SHALL treat compound powers (e.g., Clone & Reverse) as a distinct power identity separate from their component individual powers.
6. THE Card_Repository SHALL support adding new expansions without requiring changes to the database schema or existing application code; adding a new expansion SHALL require inserting a record into the expansions table AND inserting card records into the cards table referencing that expansion's ID.
7. THE Server SHALL include a separate seed script for each expansion that inserts the expansion record into the expansions table and then inserts all cards for that expansion into the database referencing that expansion's ID; each script SHALL be independently runnable so that expansions can be added one at a time, and each script SHALL read card data (card name, denomination, power text, card number, and image filename) from a structured data file (JSON or CSV) specific to that expansion.
8. THE Card_Repository SHALL NOT hard-code the list of valid expansion names; valid expansion names SHALL be derived from the expansions table and appear in filter options returned to the Client.

---

### Requirement 3: Deck Builder — Deck Management

**User Story:** As a player, I want to create, edit, save, load, and copy decks, so that I can prepare my card selection before a game.

#### Acceptance Criteria

1. THE Deck_Service SHALL store each deck record with: owner player ID, deck name, public/private flag, comment text, and a list of card entries each containing a card ID and a quantity.
2. WHEN a save-deck request is received with a valid session token and deck data, THE Deck_Service SHALL persist the deck and associate it with the authenticated player.
3. WHEN a load-deck request is received with a valid session token and a deck ID owned by the requesting player, THE Deck_Service SHALL return the full deck data.
4. WHEN a load-deck request is received for a deck marked public, THE Deck_Service SHALL return the full deck data regardless of the requesting player's identity.
5. WHEN a copy-deck request is received referencing an existing deck owned by the requesting player, THE Deck_Service SHALL create a new deck record with identical card entries and a new name, associated with the requesting player.
6. WHEN a copy-deck request is received referencing a public deck, THE Deck_Service SHALL create a new deck record with identical card entries associated with the requesting player.
7. WHEN a copy-deck request is received referencing a private deck not owned by the requesting player, THE Deck_Service SHALL return an authorisation error.
8. THE Client SHALL provide a deck builder screen with the ability to search and filter the card catalogue, add a card to the current deck, change the quantity of a card already in the deck, save the deck to the server, load an existing deck, copy an owned deck, and copy a public deck.
9. WHEN the player changes the quantity of a card in the deck builder to zero, THE Client SHALL remove that card entry from the deck.
10. WHEN a save-deck request is received, THE Deck_Service SHALL persist the deck regardless of the total card count, allowing players to save decks with fewer than 35 cards.
11. THE Client SHALL display the current total card count (sum of all card quantities) in the deck builder at all times.
12. WHEN the total card count in the deck builder is fewer than 35, THE Client SHALL display a visual indicator that the deck does not meet the minimum card count required for game use.

---

### Requirement 4: Game Lobby — Creating and Joining Games

**User Story:** As a player, I want to create or join a game session, so that I can play Tribbles with other logged-in players.

#### Acceptance Criteria

1. WHEN an authenticated player submits a create-game request with a selected deck ID and a desired total player count (between 4 and 8 inclusive), THE Lobby_Service SHALL create a new game session in a waiting state with the specified total player count and return the game session ID.
2. WHEN an authenticated player submits a join-game request with a valid game session ID and a selected deck ID, THE Lobby_Service SHALL add the player to the session if the session is in a waiting state and the current human player count is fewer than the session's total player count.
3. WHEN a join-game request is received for a session whose human player count already equals the total player count, THE Lobby_Service SHALL return an error indicating the session is full.
4. WHEN a join-game request is received for a session that is not in a waiting state, THE Lobby_Service SHALL return an error indicating the game has already started.
5. THE Client SHALL provide a lobby screen listing game sessions in two categories: sessions in the waiting state (available to join) and sessions in the active state (available to watch), with clearly labelled actions for Create Game, Join Game, and Watch Game.
6. WHEN an authenticated player submits a watch-game request with a valid game session ID, THE Lobby_Service SHALL add the player as a Spectator to the session if the session is in the active state.
7. WHEN the session creator selects "Start Game", THE Lobby_Service SHALL fill any remaining seats (total player count minus human players joined) with computer-controlled players, each assigned a randomly selected deck from the card catalogue, and then transition the session to the active state and notify all joined human players.
8. THE Game_Engine SHALL control computer players using an automated decision-making strategy that follows all game rules, selecting valid plays from their hand or drawing when no valid play is available.
9. IF a create-game request specifies a total player count less than 4 or greater than 8, THEN THE Lobby_Service SHALL return an error indicating the player count is out of the valid range.
10. IF a create-game request references a deck with a total card count fewer than 35, THEN THE Lobby_Service SHALL return an error indicating the deck does not meet the minimum card count for game use.
11. IF a join-game request references a deck with a total card count fewer than 35, THEN THE Lobby_Service SHALL return an error indicating the deck does not meet the minimum card count for game use.
12. THE Client SHALL prevent the player from selecting a deck with fewer than 35 cards when creating or joining a game.

---

### Requirement 5: Game Initialisation

**User Story:** As a player, I want the game to set up correctly before the first round, so that all players start on equal footing.

#### Acceptance Criteria

1. WHEN a game session transitions to the active state, THE Game_Engine SHALL randomly assign seating positions to all players.
2. WHEN a game session transitions to the active state, THE Game_Engine SHALL randomly select one player as the starting player.
3. WHEN a game session transitions to the active state, THE Game_Engine SHALL shuffle each player's draw deck independently.
4. WHEN a game session transitions to the active state, THE Game_Engine SHALL deal 7 cards from each player's draw deck to that player's hand.
5. WHEN a game session transitions to the active state, THE Game_Engine SHALL set the initial play direction to clockwise and the initial sequence denomination to 1.

---

### Requirement 6: Core Turn Mechanics

**User Story:** As a player, I want to take turns playing cards in the correct sequence, so that the game progresses according to the rules.

#### Acceptance Criteria

1. WHEN it is a player's turn, THE Game_Engine SHALL require that player to either play a card of the current sequence denomination or draw a card.
2. WHEN a player plays a valid card, THE Game_Engine SHALL move that card from the player's hand to the top of the player's play pile and advance the sequence to the next denomination.
3. WHEN the sequence denomination is 100000 and a player plays a valid card, THE Game_Engine SHALL reset the sequence denomination to 1 after that card is placed.
4. WHEN a player cannot or chooses not to play the current sequence denomination, THE Game_Engine SHALL draw the top card of that player's draw deck into the player's hand.
5. WHEN a drawn card matches the current sequence denomination, THE Game_Engine SHALL allow the player to choose whether to play it immediately or keep it in hand; IF the player chooses not to play it, THEN THE Game_Engine SHALL record a pass for that player.
6. WHEN a drawn card does not match the current sequence denomination, THE Client SHALL display the drawn card to the local player with an "Accept" button, and THE Game_Engine SHALL record a pass for that player only after the player confirms; the delay SHALL prevent opponents from distinguishing between a playable and non-playable draw based on response time.
7. WHEN a pass has occurred, THE Game_Engine SHALL allow the next player to choose between playing the current sequence denomination or playing a 1-denomination card.
8. WHEN a player must draw a card and the player's draw deck is empty, THE Game_Engine SHALL mark that player as decked.
9. THE Game_Engine SHALL track the denomination of the last card actually played (the "last played denomination") separately from the current sequence denomination, so that Clone cards can reference the last played denomination even after the sequence has been reset.

---

### Requirement 7: Decked State

**User Story:** As a player, I want the game to correctly handle a player becoming decked, so that the round continues fairly.

#### Acceptance Criteria

1. WHEN a player is marked as decked, THE Game_Engine SHALL immediately move all cards in that player's hand to that player's discard pile.
2. WHILE a player is decked, THE Game_Engine SHALL prevent that player from scoring points and prevent other players from scoring points from that player, except as modified by the Antidote power.
3. WHILE a player is decked, THE Game_Engine SHALL leave that player's play pile in place and allow it to be referenced by powers such as Copy.
4. WHILE a player is decked, THE Game_Engine SHALL allow that player to be targeted by Tribbles powers.
5. WHEN all non-decked players except one are decked, THE Game_Engine SHALL cause the last remaining non-decked player to go out by moving that player's entire hand to that player's play pile.
6. WHEN a round ends in which a player was decked, THE Game_Engine SHALL allow that player to rejoin the next round by reshuffling their play pile as their draw deck.
7. WHEN a player attempts to rejoin after being decked and the reshuffled deck contains fewer than 7 cards, THE Game_Engine SHALL immediately discard that player's hand and mark that player as sitting out for the next round.

---

### Requirement 8: End of Round and Scoring

**User Story:** As a player, I want the round to end correctly and scores to be calculated, so that the game progresses toward a winner.

#### Acceptance Criteria

1. WHEN a player's hand becomes empty, THE Game_Engine SHALL mark that player as having gone out and trigger end-of-round processing.
2. WHEN end-of-round processing is triggered, THE Score_Service SHALL sum the denominations of all cards in the play pile of each player who went out and add that total to each such player's cumulative score.
3. WHEN end-of-round processing is triggered, THE Game_Engine SHALL move all cards remaining in the hand of each player who did not go out to that player's discard pile.
4. WHEN end-of-round processing is triggered, THE Game_Engine SHALL shuffle each player's play pile into that player's draw deck.
5. WHEN a new round begins, THE Game_Engine SHALL deal 7 cards from each active player's draw deck to that player's hand.
6. WHEN a new round begins, THE Game_Engine SHALL reset the sequence denomination to 1 and the play direction to clockwise.
7. WHEN exactly one player went out, THE Game_Engine SHALL designate that player as the starting player for the new round.
8. WHEN multiple players went out simultaneously, THE Game_Engine SHALL designate the player among them with the lowest round score as the starting player for the new round.
9. THE Client SHALL display an end-of-round score screen showing each player's round score and cumulative score after each round ends.

---

### Requirement 9: Card Powers — Base Set

**User Story:** As a player, I want each card power to be enforced correctly, so that the game plays as designed.

#### Acceptance Criteria

1. WHEN a player plays a card with an activatable power, THE Game_Engine SHALL prompt that player to choose whether to activate the power or decline; IF the player declines, THEN the card is placed on the play pile without triggering its power effect.
2. WHEN a player plays a card with the Discard power and chooses to activate it, THE Game_Engine SHALL prompt that player to choose one card from their hand and move it to their discard pile.
3. WHEN a player plays a card with the Go power and chooses to activate it, THE Game_Engine SHALL grant that player an additional turn by advancing the sequence and keeping the turn with that player.
4. WHEN a player plays a card with the Skip power and chooses to activate it, THE Game_Engine SHALL advance the turn past the next player in the current direction without that player taking a turn.
5. WHEN a player plays a card with the Poison power and chooses to activate it, THE Game_Engine SHALL prompt the active player to choose an opponent who has at least one card in their draw deck, discard the top card of that opponent's draw deck, and add points equal to that card's denomination to the active player's score immediately.
6. WHEN a player plays a card with the Rescue power and chooses to activate it, THE Game_Engine SHALL allow that player to look through their discard pile, select one card, and either place it face-down on top of their draw deck or, if its denomination matches the current sequence, play it immediately.
7. WHEN a player plays a card with the Reverse power and chooses to activate it, THE Game_Engine SHALL toggle the play direction between clockwise and counterclockwise.
8. WHEN a player plays a card with the Clone power, THE Game_Engine SHALL allow that card to be played even when its denomination equals the denomination of the last card played.

---

### Requirement 10: Card Powers — The Trouble with Tribbles Expansion

**User Story:** As a player, I want the Bonus power to be enforced correctly, so that the bonus scoring condition is applied at end of round.

#### Acceptance Criteria

1. WHEN end-of-round processing is triggered for a player who did not get decked and whose play pile contains one Bonus card of denomination 1, one of denomination 10, one of denomination 100, and one of denomination 1000 (all with the Bonus power), THE Score_Service SHALL add 100000 points to that player's cumulative score.

---

### Requirement 11: Card Powers — More Tribbles More Troubles Expansion

**User Story:** As a player, I want the powers from More Tribbles More Troubles to be enforced correctly, so that the expanded game plays as designed.

#### Acceptance Criteria

1. WHEN a player is targeted by the Poison power and the top card of that player's draw deck (the card about to be discarded) has the Antidote power, THE Game_Engine SHALL cause the targeted player to score points equal to that card's denomination instead of the Poison player scoring, and THE Game_Engine SHALL allow the targeted player to place their hand beneath their draw deck.
2. WHEN a player plays a card with the Copy power, THE Game_Engine SHALL allow that player to immediately apply the game text of the top card of any other player's play pile, subject to the rules of that power.
3. WHEN a player plays a card with the Cycle power, THE Game_Engine SHALL prompt that player to place one card from their hand beneath their draw deck and then draw one card from the top of their draw deck.
4. WHEN a player plays a card with the Draw power, THE Game_Engine SHALL prompt the active player to choose any player, and that chosen player SHALL draw one card from the top of their draw deck.
5. WHEN a player plays a card with the Exchange power, THE Game_Engine SHALL prompt that player to discard one card from their hand and then take one card from their discard pile into their hand.
6. WHEN a player plays a card with the Kill power, THE Game_Engine SHALL prompt the active player to choose any player and discard the top card of that player's play pile.
7. WHEN a player plays a card with the Recycle power, THE Game_Engine SHALL prompt the active player to choose any player and shuffle that player's discard pile into their draw deck.
8. WHEN a player plays a card with the Replay power, THE Game_Engine SHALL allow that player to search their play pile for one card and play it again as if it were played from hand.
9. WHEN a player plays a card with the Score power, THE Game_Engine SHALL mark the chosen player as a Score target, and if that player plays a card on their next turn, THE Score_Service SHALL add points equal to that card's denomination to the Score power activator's cumulative score.

---

### Requirement 12: Card Powers — No Tribble at All Expansion

**User Story:** As a player, I want the powers from No Tribble at All to be enforced correctly, including compound power rules.

#### Acceptance Criteria

1. WHEN a compound power card is played and neither component is Clone, THE Game_Engine SHALL require the player to activate both component powers together.
2. WHEN a compound power card containing Clone is played and the player does not use the Clone component, THE Game_Engine SHALL allow the non-Clone power to be activated independently.
3. WHEN a compound power card containing Clone is played and the player uses the Clone component, THE Game_Engine SHALL require the other component power to also be activated.
4. WHEN a player plays a card with the Battle power, THE Game_Engine SHALL reveal the top three cards of the chosen opponent's draw deck and the top three cards of the active player's draw deck; the player with the higher total denomination places those cards under their play pile, and the other player discards those cards.
5. WHEN a player plays a card with the Evolve power, THE Game_Engine SHALL count the cards in that player's hand, move all hand cards to the discard pile, and deal that many cards from the top of the draw deck to the hand.
6. WHEN a player plays a card with the Freeze power, THE Game_Engine SHALL record the named power as frozen until the end of the active player's next turn, and THE Game_Engine SHALL reject any attempt to play a card bearing that power during the freeze period.
7. WHEN a player plays a card with the Mutate power, THE Game_Engine SHALL count the cards in that player's play pile, shuffle the play pile into the draw deck, and then move that many cards from the top of the draw deck to the play pile.
8. WHEN a player plays a card with the Process power, THE Game_Engine SHALL deal three cards from the draw deck to the player's hand and then prompt the player to choose two cards from hand to place beneath the draw deck.
9. WHEN end-of-round processing is triggered and a player who won the round has the Quadruple card in their play pile, THE Score_Service SHALL count that card as worth 40000 points instead of 10000.
10. THE Game_Engine SHALL prevent the Copy power from copying the Quadruple power.
11. WHEN end-of-round processing is triggered and a player has the Safety card in their play pile, THE Game_Engine SHALL allow that player to shuffle their hand into their draw deck instead of placing their hand in their discard pile.
12. WHEN another player is about to score points from a card bearing the Tally power, THE Score_Service SHALL award half that card's denomination value to the scoring player and an equal number of points to the Tally card's owner.
13. WHEN a player plays a card with the Toxin power, THE Game_Engine SHALL, for each Discard card in each other player's play pile, cause that player to reveal the top card of their draw deck; the active player then chooses one revealed card and scores points equal to its denomination; all players who revealed cards place those cards into their hand.

---

### Requirement 13: Card Powers — Trials and Tribble-ations Expansion

**User Story:** As a player, I want the powers from Trials and Tribble-ations to be enforced correctly.

#### Acceptance Criteria

1. WHEN a player plays a card with the Avalanche power and that player has at least four other cards remaining in hand after playing, THE Game_Engine SHALL require all players to discard one card from their hand and then allow the active player to discard one additional card.
2. WHEN a player plays a card with the Famine power, THE Game_Engine SHALL set the next sequence denomination to 1 regardless of the current sequence position.
3. WHEN a player plays a card with the Stampede power, THE Game_Engine SHALL allow all players to immediately play one card of the current sequence denomination in turn order; only the card played by the active player may activate its power.
4. WHEN a player plays a card with the Time Warp power and that card is in the player's play pile at the end of the round and that player did not go out, THE Game_Engine SHALL reduce the number of cards dealt to that player at the start of the next round by 1, to a minimum of 1, and this reduction SHALL NOT stack with other Time Warp cards of the same denomination in the same play pile.

---

### Requirement 14: Card Powers — Nothing But Tribble Expansion

**User Story:** As a player, I want the powers from Nothing But Tribble to be enforced correctly.

#### Acceptance Criteria

1. WHEN a player plays a card with the Advance power and the sequence was broken by a pass, THE Game_Engine SHALL allow that card to be played in place of a 1-denomination card.
2. WHEN a player plays a card with the Assimilate power, THE Game_Engine SHALL move the top card of the chosen player's draw deck to the active player's play pile and record that card as borrowed, to be returned to the original owner at the end of the round or when it leaves the play pile.
3. WHEN a player plays a card with the Convert power, THE Game_Engine SHALL place that card beneath the active player's draw deck and then move the top card of the draw deck to the active player's play pile.
4. WHEN end-of-round processing is triggered and a player who went out has one or more IDIC cards in their play pile, THE Score_Service SHALL add 10000 points per unique power in that player's play pile for each IDIC card, counting compound powers as distinct powers, and SHALL NOT stack multiple IDIC cards of the same denomination.
5. WHEN a player plays a card with the Masaka power, THE Game_Engine SHALL place all players' hands beneath their respective draw decks and deal each player a new hand of 3 cards.
6. WHEN a player plays a card with the Scan power, THE Game_Engine SHALL reveal the top 3 cards of the active player's draw deck to that player only and allow that player to reorder and place those cards on the top or bottom of the draw deck in any order.
7. WHEN a player plays a card with the Utilize power, THE Game_Engine SHALL require the chosen opponent (who has at least two cards in hand) to randomly place one card from their hand on top of their play pile, and THE Score_Service SHALL add points equal to that card's denomination to the active player's cumulative score.

---

### Requirement 15: Game Table Display

**User Story:** As a player, I want to see the full game state on screen, so that I can make informed decisions during play.

#### Acceptance Criteria

1. THE Client SHALL display all players arranged around a virtual table, with the local player's position at the bottom of the screen.
2. THE Client SHALL display each player's draw deck (as a face-down stack with card count), discard pile (top card visible), and play pile (top card visible) at that player's table position.
3. WHEN the player's mouse cursor hovers over a play pile or discard pile, THE Client SHALL display an enlarged view of the top card of that pile.
4. THE Client SHALL indicate the current active player, the current sequence denomination, and the current play direction.
5. THE Client SHALL display the local player's hand cards face-up and allow the player to select a card to play on their turn.
6. WHEN it is the local player's turn, THE Client SHALL highlight valid playable cards in the local player's hand.
7. THE Client SHALL display each player's current cumulative score at their table position, visible at all times during the game.

---

### Requirement 16: End of Game

**User Story:** As a player, I want to see a clear end-of-game screen, so that I know who won and what the final scores were.

#### Acceptance Criteria

1. THE Game_Engine SHALL end the game after five rounds have been completed; the player with the highest cumulative score after the fifth round wins.
2. WHEN the fifth round ends, THE Game_Engine SHALL transition the session to the completed state and broadcast final scores to all players.
3. WHEN the session transitions to the completed state, THE Client SHALL display an end-of-game screen showing each player's name and final cumulative score, ranked from highest to lowest.
4. WHEN the session transitions to the completed state, THE Client SHALL clearly indicate the winning player.

---

### Requirement 17: Localisation

**User Story:** As a Swedish-speaking player, I want to use the client in Swedish, so that I can play comfortably in my native language.

#### Acceptance Criteria

1. THE Client SHALL display all user interface text in English by default.
2. WHEN the player selects Swedish as the interface language, THE Client SHALL display all user interface text in Swedish.
3. THE Client SHALL persist the player's language preference across sessions.

---

### Requirement 18: Server Code Quality

**User Story:** As a developer, I want the server code to follow documentation and typing standards, so that the codebase is maintainable and testable.

#### Acceptance Criteria

1. THE Server SHALL include a docstring on every module, class, and public function describing its purpose, parameters, and return values.
2. THE Server SHALL include Python type annotations on every function signature and class attribute.
3. THE Server SHALL include a pytest test suite covering the Game_Engine rule enforcement, Score_Service calculations, Auth_Service authentication flows, and Deck_Service deck operations.

---

### Requirement 19: Client Code Quality

**User Story:** As a developer, I want the client code to be properly documented, so that the codebase is maintainable.

#### Acceptance Criteria

1. THE Client SHALL include a documentation comment on every script file, class, and public function describing its purpose and parameters.
2. THE Client SHALL include automated tests using the best available testing tool for Godot 4 / GDScript covering UI interactions, deck builder logic, and game state display updates.

---

### Requirement 20: Data Persistence and Database Schema

**User Story:** As a system, I want all persistent data stored in a relational database, so that player accounts, cards, and decks survive server restarts.

#### Acceptance Criteria

1. THE DB SHALL be MariaDB.
2. THE DB SHALL contain a players table with at minimum: player ID, username (unique), hashed password, email address, and creation timestamp.
3. THE DB SHALL contain an expansions table with at minimum: expansion_id, expansion_name (unique), pack_art_filename, and expansion_description (text).
4. THE DB SHALL contain a cards table with at minimum: card ID, card name, denomination, power text, card number, expansion_id (foreign key referencing the expansions table), and image filename.
5. THE DB SHALL contain a decks table with at minimum: deck ID, owner player ID, deck name, public flag, and comment text.
6. THE DB SHALL contain a deck_cards table (or equivalent structure) recording the card ID and quantity for each card entry in a deck.
7. WHEN the server starts, THE Server SHALL verify the database connection and schema integrity before accepting client connections.

---

### Requirement 21: Player Disconnection and Reconnection

**User Story:** As a player, I want to be able to reconnect to a game if my connection drops, so that I do not lose my seat or progress due to a temporary network issue.

#### Acceptance Criteria

1. WHEN the Server detects that a player's network connection has been lost during an active game session, THE Game_Engine SHALL mark that player as disconnected and begin a reconnection grace period equal to the configured Reconnection_Timeout value.
2. THE Server SHALL allow the Reconnection_Timeout to be configured per game session at creation time, with a default value of 30 seconds.
3. WHILE a player is in the disconnected state and the Reconnection_Timeout has not elapsed, THE Game_Engine SHALL skip that player's turn without marking the player as decked.
4. WHEN the Reconnection_Timeout elapses and the disconnected player has not reconnected, THE Game_Engine SHALL assign an AI_Substitute to control that player's seat using the same automated decision-making strategy as computer-controlled players.
5. WHILE an AI_Substitute controls a disconnected player's seat, THE Game_Engine SHALL use that player's existing hand, draw deck, play pile, and discard pile without modification.
6. WHEN a previously disconnected player reconnects to the Server with a valid session token, THE Game_Engine SHALL immediately remove the AI_Substitute and restore full control of that seat to the reconnected player.
7. WHEN a previously disconnected player reconnects, THE Game_Engine SHALL send the full current game state to that player's Client, including hand contents, all visible piles, scores, current sequence denomination, play direction, and active player.
8. IF the game ends while a player is disconnected, THEN THE Game_Engine SHALL record that player's final score and include the player in the end-of-game results; the player SHALL be able to view the final results upon reconnecting.
9. WHEN a player is marked as disconnected, THE Client SHALL display a visual indicator at that player's table position showing the disconnected status to all other players.
10. WHILE an AI_Substitute controls a disconnected player's seat, THE Client SHALL display a distinct visual indicator at that player's table position showing that a computer player is controlling the seat.
11. WHEN a disconnected player reconnects and resumes control, THE Client SHALL remove the disconnected or AI_Substitute indicator and display a brief notification to all players that the player has returned.

---

### Requirement 22: Game Spectating

**User Story:** As a player, I want to watch an active game without participating, so that I can observe other players' strategies and enjoy the game.

#### Acceptance Criteria

1. WHEN an authenticated player submits a watch-game request for a session in the active state, THE Lobby_Service SHALL add the player as a Spectator to that session and return a success response.
2. WHILE a Spectator is observing a game session, THE Game_Engine SHALL send visible game state updates to the Spectator including play piles, discard piles, draw deck card counts, scores, current sequence denomination, play direction, and the active player.
3. WHILE a Spectator is observing a game session, THE Game_Engine SHALL NOT send any player's hand contents to the Spectator.
4. THE Client SHALL provide a spectator view displaying the game table with all public information (play piles, discard piles, draw deck counts, scores, current sequence denomination, direction, and active player) without revealing any player's hand contents.
5. WHEN a Spectator chooses to leave the game session, THE Lobby_Service SHALL remove the Spectator from the session without affecting the game state or active players.
6. THE Client SHALL display the current number of Spectators watching the game at the game table, visible to all players and other Spectators.
7. WHILE a player is a Spectator, THE Game_Engine SHALL NOT allow that player to perform any game actions (playing cards, drawing cards, or activating powers).
