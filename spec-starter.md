# Description
Build a multiplayer game for playing the customizable card game Tribbles. It should have a server run on a raspberry pi and a client possible to run on both windows and Linux. 

The players need to be able to create a user and log into the server. They should be able to build decks and play games with other players that are logged in.

## Rules of the game
The game is played with 4 to 8 players, each player having their own deck. Before the game starts, the players are seated randomly and the starting player is also chosen at random. Then all players shuffle their deck and draw a starting hand of 7 cards. The game starts in clockwise order.

There are 6 levels of tribbles, 1, 10, 100, 1000, 10000 and 100000. 

The starting player needs to play a 1-card. After a 1-card, the next player needs to play a 10-card, then the next 100 etc until 100000. After a player played a 100000 tribbles card, the next card played should be a 1-tribble. 

If a player can not, or do not want to play, the next tribble in sequence, he or she can draw a card. If that card can be played, he or she may play it. If the card can not be played, he or she passes (the drawn card is put into that players hand). The next player may choose between playing the next tribble in sequence or a 1-tribble after a pass.

When any player has no cards in their hand, he or she is considered to be going out. Any and all players who go out in a round counts all tribbles numbers on each card in their play piles and gain that many points. All other players put the cards in their hand into their discard pile. After that, all players shuffle their play piles into their draw deck and then a new round starts with all players drawing 7 cards and the player going out starting the new round. If multiple players went out at the same time, the player who went out with the lowest number of points starts.

When a new round starts, the sequence is reset and once again starts at 1 tribble. Also, the direction is reset to clockwise.

If at any point a player must draw a card from your deck and he or she is unable to do so, he or she is “decked” and cannot continue in the round.

When a player becomes “decked”, he or she immediately discards his or her hand. He or she may not score points of any kind (nor may any other player score points from him or her) while he or she is “decked.”
The player leaves his or her play pile in place, as it remains in play for other player’s reference (i.e. the power Copy).

If all opponents are “decked,” the last remaining player immediately “goes out” by placing his or her entire hand into their play pile. 

At the end of a round in which a player was “decked”, he or she may rejoin the game by reshuffling his or her play pile for use as his or her deck. If the player has less than seven cards, they must immediately discard their hand and sit out the next round.

A player that is “decked” is a valid target for Tribbles powers, but they will remain out for the remainder of the current round. They will be able to join the game in the next round if such a power restores their deck.

Each card has a denomination (number of tribbles), and a power. The cards are grouped into expansions. The following section will explain the rules for all the powers, per expansion, and list all cards available in that expansion.

### Tribbles - base set
Discard: Choose one card in your hand to place in your discard pile.

Go: Take another turn (that is, play the next tribble number in sequence).

Skip: Skip the next player.

Poison: Choose any opponent who still has card(s) in their draw deck. That opponent must discard the top card, and you immediately score points equal to the number of tribbles on that card.

Rescue: Look through your discard pile and recover a card. Place it face-down on top of your draw deck - or, if it has the proper number of tribbles, you may play it now.

Reverse: Reverse the direction of play from clockwise to counterclockwise (or vice versa).

Clone: This tribble may be played even when it has the same number of tribbles as the last card played.

The cards in the base set, per denomination
1: Discard, Go, Skip
10: Go, Poison, Skip
100: Poison, Rescue, Reverse
1000: Discard, Rescue, Reverse
10000: Clone, Reverse, Skip
100000: no cards

### The trouble with Tribbles
Bonus: At the end of the round, if you avoided getting "decked" and your play pile includes a run of all four BONUS cards (1-10-100-1,000), you score 100,000 points.

The cards in the set per denomination
1: Bonus, Discard, Go
10: Bonus, Go, Poison
100: Bonus, Poison, Rescue
1000: Bonus, Discard, Rescue
10000: Poison, Rescue, Clone
100000: Clone, Discard, Rescue

### More Tribbles, More Troubles
Antidote: If this tribble is poisoned, its owner scores points instead and may place his or her hand beneath his or her draw deck.

Copy: You may immediately use the game text of the top tribble of any other play pile.

Cycle: Place a tribble in hand beneath your draw deck to draw a card.

Draw: Choose a player. He or she must draw a card.

Exchange: Discard a tribble from hand to take a tribble into hand from your discard pile.

Kill: Choose a player to discard the top tribble of his or her play pile.

Recycle: Choose a player to shuffle his or her discard pile into his or her draw deck.

Replay: Search your play pile for a tribble and play it again.

Score: Choose a player. If that player plays a tribble on his or her next turn, you score points equal to the number of tribbles on that card.

The cards in the set per denomination
1: Cycle, Exchange, Replay
10: Copy, Cycle, Draw
100: Copy, Draw, Score
1000: Exchange, Recycle, Score
10000: Antidote, Kill, Recycle
100000: Antidote, Kill, Replay

### No Tribble at All
From this expansion, combined powers are a thing.

A compound Tribble power is a single card that contains two separate powers. In most cases, the use of one of the powers also triggers the use of the other power. For example, Matt plays a 10 Recycle & Freeze. If he chooses to activate the power, he must both select a player as the target for the Recycle, and name a Tribble power as the target for the Freeze.

When a compound tribble power is played that includes the Clone power, the non-Clone power can be activated without using the Clone power. For example, when Johnny plays a 10 Tribble, Dan 
(as the next player) can play a 100 Clone & Skip on his turn and activate the Skip power. 

However, when the Clone power of a compound Tribble power is activated, the other power must be activated. For example, after Dan plays his 100 Clone & Skip to skip Matt, Rogue (as the next 
player) can play his own 100 Clone & Skip; but, since he is using the Clone, he must use the Skip as well.Each compound power combination counts as a different power than its included powers. For example, Dan goes out with a 1 IDIC, a 100 Recycle & Reverse, a 1,000 Recycle, and a 10,000 Reverse in his pile. The IDIC is worth 40,000 points because there are four unique powers in his play pile.

Battle: Choose another player to reveal the top three cards of his or her draw deck. You reveal the top three cards of your draw deck. Each player with the highest total places those cards under his or her play pile; the other player discards his or her cards.

Evolve: Count the number of cards in your hand, place your hand in your discard pile, and draw that many cards.

Freeze: Name a tribble power. Until the end of your next turn this round, players cannot play tribbles with that power (whether the power is used or not).

Mutate: Count the number of cards in your play pile. Shuffle your play pile into your draw deck, then put that many cards from the top of your draw deck in your play pile.

Process: Draw three cards, then choose two cards from hand to place beneath your draw deck.

Quadruple: If you win the round with this tribble in your play pile, this tribble is worth 40,000 instead of 10,000. (This tribble cannot be copied.)

Safety: If this tribble is in your play pile at the end of the round, you may shuffle your hand into your draw deck instead of placing your hand in your discard pile.

Tally: If another player is about to score points from this tribble, he or she scores half this tribble's value instead, and you score an equal number of points.

Toxin: Each other player reveals the top card of his or her draw deck for each Discard tribble in his or her play pile. Choose one revealed card and score points equal to the number of tribbles on that card. Each player who revealed cards places those cards in his or her hand.

The cards in the set per denomination
1: Clone & Reverse, Evolve, Process
10: Battle, Evolve, Toxin
100: Battle, Clone & Skip, Recycle & Reverse
1000: Freeze, Process, Safety
10000: Go, Quadruple, Toxin
100000: Mutate, Safety, Tally

###Trials and Tribble-ations
Avalanche: If you have least four other cards in hand, all players discard a card. You may then discard one extra.

Famine: The next tribble in sequence is 1.
Stampede: All players may immediately play the next tribble in sequence. only the tribble you play may activate its power.

Time Warp: If this tribble is in your play pile at the end of the round and you did not go out, start with one less card in your hand the next round (not cumulative with other Time Warp tribbles in your play pile of the same denomination). 

The cards in the set per denomination
1: Bonus & Freeze, Discard, Go
10: Avalanche, Bonus, Go
100: Bonus, Poison, Rescue
1000: Bonus, Discard, Famine, Discard
10000: Safety, Time Warp
100000: Freeze

### Nothing But Tribble
Advance: You may play this tribble in place of 1 tribble if the sequence was "broken."

Assimilate: Choose a player. Take the top card from that player's draw deck and place it on your play pile. (Return that tribble at the end of the round or if it leaves your tribble pile.)

Convert: Place this tribble beneath your draw deck, then place the top card of your draw deck on your play pile.

IDIC: If you go out, score 10,000 points for each different tribble power in your play pile (not cumulative with other 1 IDIC tribbles in your play pile).

Masaka: All players place their hand beneath their draw deck and then draw a new hand of three cards.

Scan: Look at the top 3 cards of your draw deck. You may place those cards on top or bottom of your draw deck in any order.

Utilize: Choose an opponent with at least two cards in hand. That opponent randomly places a card from hand on top of their play pile. Score points equal to the number of tribbles on that card.

The cards in the set per denomination
1: Convert, IDIC, Skip
10: Advance, Recycle & Freeze, Skip, Utilize 
100: Scan, Utilize
1000: Masaka, Reverse, Scan
10000: Assimilate, Masaka, Reverse, Skip
100000: Assimilate, Time Warp

# Datamodell
The database needs to contain information about players, cards and decks. The database should be either mysql, mariadb or postgresql. The player logs in from the client, so the tables for players need to have the information needed for the ability to log in. The table for the cards needs to have room for card name, denomination, ability, card number, expansion, image name. The deck table needs information about whose deck it is, if it is public, name, a list of cards (and amount of each card) in the deck. Also a comment text should be in there. 

# Client requirements
1. Possibility to log into the server from the client
2. A deck builder with functions:
   - Search and filter for cards to put into the deck
   -  Put a card into the deck from filtered list
   - Change number of a certain card in the deck.
   -  save the deck to the server
   - load a deck
   - copy an old deck
   - Copy a public deck.
3. Start game
4. join game
5. Play a game.
6. Show all players around a virtual table.
7. Show draw deck, discard pile and play pile for each player
8. Show a bigger version of the card, if mouse is over a pile with a public 
9. Show end of round score
10. End of game screen, showing who won.

# Server requirements
1. Possibility to log into the server from the client
2. Handle storage of cards
3. Handle storage of decks
4. Handle the rules enforcements of the game. Being able to handle all the rules in the game.
5. Handle new round, including scoring.
6. Handle end of game

# Limits
- Database serverside in mysql, mariadb or postgresql
- Server written in python, should run on a raspberry pi
- Tests for the server in pytest
- Client written in Godot4 /GDScript
- Test for client in the best available testing tool

# Language rules
- The default language of the game is **English**
- Possibility to change language to **Swedish** for the user interface

# Non-functional requirements
- The code for the server shall have docstrings and typeannotations
- The code for the client shall be properly documented



