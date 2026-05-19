-- Tribbles Multiplayer Game - MariaDB Schema
-- Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6

-- Players table: stores registered player accounts
CREATE TABLE IF NOT EXISTS players (
    player_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Sessions table: stores active login sessions
CREATE TABLE IF NOT EXISTS sessions (
    token VARCHAR(128) PRIMARY KEY,
    player_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (player_id) REFERENCES players(player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Expansions table: stores card expansion/set metadata
CREATE TABLE IF NOT EXISTS expansions (
    expansion_id INT AUTO_INCREMENT PRIMARY KEY,
    expansion_name VARCHAR(128) NOT NULL UNIQUE,
    pack_art_filename VARCHAR(255) NOT NULL,
    expansion_description TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Cards table: stores individual card definitions
CREATE TABLE IF NOT EXISTS cards (
    card_id INT AUTO_INCREMENT PRIMARY KEY,
    card_name VARCHAR(128) NOT NULL,
    denomination INT NOT NULL,
    power_text VARCHAR(255) NOT NULL,
    card_number VARCHAR(32) NOT NULL,
    expansion_id INT NOT NULL,
    image_filename VARCHAR(255) NOT NULL,
    FOREIGN KEY (expansion_id) REFERENCES expansions(expansion_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Decks table: stores player-created decks
CREATE TABLE IF NOT EXISTS decks (
    deck_id INT AUTO_INCREMENT PRIMARY KEY,
    owner_player_id INT NOT NULL,
    deck_name VARCHAR(128) NOT NULL,
    is_public BOOLEAN DEFAULT FALSE,
    comment_text TEXT,
    FOREIGN KEY (owner_player_id) REFERENCES players(player_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Deck_cards table: stores card entries within a deck
CREATE TABLE IF NOT EXISTS deck_cards (
    deck_id INT NOT NULL,
    card_id INT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    PRIMARY KEY (deck_id, card_id),
    FOREIGN KEY (deck_id) REFERENCES decks(deck_id) ON DELETE CASCADE,
    FOREIGN KEY (card_id) REFERENCES cards(card_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_sessions_player_id ON sessions(player_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_cards_expansion_id ON cards(expansion_id);
CREATE INDEX IF NOT EXISTS idx_cards_denomination ON cards(denomination);
CREATE INDEX IF NOT EXISTS idx_cards_card_name ON cards(card_name);
CREATE INDEX IF NOT EXISTS idx_decks_owner_player_id ON decks(owner_player_id);
CREATE INDEX IF NOT EXISTS idx_decks_is_public ON decks(is_public);
