# Xì Tố (Tiến Lên) - Vietnamese Card Game with Neural Network AI

## Overview

This is a complete fullstack web application that lets you play **Xì Tố** (also known as **Tiến Lên** or **President**) against AI opponents powered by a neural network (NNUE - Neural Network with Upper Confidence Bound).

## Features

### Game Play
- **2-4 players** (you + AI opponents)
- **Standard 52-card deck** dealt evenly (13 cards each)
- **Authentic Vietnamese rules** with proper card ranking
- **All move types**: single, pair, triple, four of a kind, sequence, double sequence
- **Bomb mechanics**: four of a kind and 3+ consecutive pairs can beat a 2
- **Turn-based** with pass functionality

### Neural Network AI
- **Custom NNUE implementation** (no external dependencies)
- **3-layer neural network**: 109 inputs → 128 → 128 → 53 outputs
- **Epsilon-greedy policy** for balanced exploration and exploitation
- **Online learning** from game data
- **Model persistence** to PostgreSQL database

### Training System
- **Supervised learning** from historical game data
- **Self-play training** (AI vs AI matches)
- **Model versioning** and statistics tracking
- **On-demand training** via API endpoints

## Card Ranking

### Rank Order (lowest to highest):
3 < 4 < 5 < 6 < 7 < 8 < 9 < 10 < J < Q < K < A < **2**

### Suit Order (lowest to highest):
♠ (Spades) < ♣ (Clubs) < ♦ (Diamonds) < ♥ (Hearts)

**Note:** The 2 of Hearts is the highest card in the entire deck!

## Move Types

1. **Single**: One card (e.g., 7♥)
2. **Pair**: Two cards of same rank (e.g., 9♠ 9♥)
3. **Triple**: Three cards of same rank (e.g., K♣ K♦ K♥)
4. **Four of a Kind**: All four cards of same rank (e.g., 5♠ 5♣ 5♦ 5♥) - **BOMB**
5. **Sequence**: 3+ consecutive ranks, any suits (e.g., 4♣ 5♦ 6♥ 7♠)
6. **Double Sequence**: 3+ consecutive pairs (e.g., 8♠ 8♥ 9♣ 9♦ 10♠ 10♥) - **BOMB if 3+ pairs**

## Game Rules

1. Player with **3♠** starts first and must include it in their opening play
2. Players must **beat** the previous play with the same type and higher value
3. If you can't beat, you must **pass**
4. **Bombs** can be played out of turn to beat a 2
5. When all other players pass, the last player to play starts a new round
6. **First to empty their hand wins!**

## API Endpoints

### Game Management
- `POST /api/game` - Create a new game
- `GET /api/game/:id` - Get game state
- `POST /api/game/:id/play` - Make a move
- `GET /api/game/:id/valid-moves` - Get valid moves for current player
- `GET /api/game/:id/ai-move` - Get AI move
- `POST /api/game/:id/reset` - Reset game

### Training
- `POST /api/train` - Train on historical game data
- `GET /api/train` - Get training statistics
- `POST /api/train/self-play` - Run self-play training

### Health
- `GET /api/health` - Health check

## Project Structure

```
├── src/
│   ├── app/
│   │   ├── api/
│   │   │   ├── game/
│   │   │   │   ├── route.ts          # Create game
│   │   │   │   └── [id]/
│   │   │   │       ├── route.ts      # Game operations
│   │   │   │       └── ai-move/
│   │   │   │           └── route.ts  # AI move
│   │   │   ├── train/
│   │   │   │   └── route.ts          # Training endpoints
│   │   │   └── health/
│   │   │       └── route.ts          # Health check
│   │   ├── page.tsx                   # Main game page
│   │   ├── layout.tsx                 # Root layout
│   │   └── globals.css                # Global styles
│   ├── components/
│   │   ├── Card.tsx                   # Card component
│   │   ├── CardGrid.tsx               # Card grid
│   │   ├── GameBoard.tsx              # Game board
│   │   ├── TrainingPanel.tsx          # Training controls
│   │   └── GameSetup.tsx              # Game setup
│   ├── lib/
│   │   ├── game/
│   │   │   ├── constants.ts           # Game constants
│   │   │   ├── cardUtils.ts           # Card utilities
│   │   │   ├── moveValidator.ts       # Move validation
│   │   │   ├── gameState.ts           # Game state management
│   │   │   └── index.ts               # Game exports
│   │   ├── ai/
│   │   │   ├── nnue.ts                # Neural network
│   │   │   └── index.ts               # AI exports
│   │   └── index.ts                   # Lib exports
│   └── db/
│       ├── schema.ts                 # Database schema
│       └── index.ts                   # Database connection
├── package.json
├── drizzle.config.json
└── .env
```

## Database Schema

### games
- `id`: UUID (primary key)
- `created_at`: timestamp
- `updated_at`: timestamp
- `status`: 'waiting' | 'playing' | 'completed'
- `players`: number (2-4)
- `winner_id`: string | null
- `initial_state`: JSON (initial card distribution)

### moves
- `id`: UUID (primary key)
- `game_id`: UUID (foreign key)
- `player_index`: number
- `turn_order`: number
- `move_type`: string
- `cards`: JSON (array of card strings)
- `is_bomb`: boolean
- `is_winning_move`: boolean
- `game_state_before`: JSON
- `game_state_after`: JSON

### training_data
- `id`: UUID (primary key)
- `game_id`: UUID (foreign key)
- `state`: JSON (encoded game state)
- `action`: JSON (action taken)
- `reward`: number
- `q_value`: number

### nn_models
- `id`: UUID (primary key)
- `name`: string
- `version`: number
- `architecture`: JSON
- `weights`: JSON
- `accuracy`: number
- `loss`: number
- `epochs`: number

## How to Use

### Starting a Game
1. Visit the homepage
2. Enter your name
3. Select number of players (2-4)
4. Click "Start Game"

### Playing
- Click on cards in your hand to select them
- Click "Play Selected" to play the selected cards
- Click "Pass" to pass your turn
- The AI will automatically play when it's their turn

### Training the AI
- Click "Train on Recent Games" to train on historical data
- Click "Self-Play" to have the AI play against itself and learn
- View training statistics in the panel

## Technical Details

### Neural Network Architecture
- **Input Layer**: 109 features
  - 52 binary features for player's hand
  - 52 binary features for last play
  - 4 one-hot encoded features for current player
  - 1 normalized feature for turn order
  
- **Hidden Layers**: 2 layers of 128 neurons each with ReLU activation

- **Output Layer**: 53 neurons (one for each card + pass)

### Card Encoding
Each card is encoded as a unique index (0-51):
- Rank index (0-12): 3,4,5,6,7,8,9,10,J,Q,K,A,2
- Suit index (0-3): S,C,D,H
- Card index = rank_index * 4 + suit_index

Example: "2H" = rank 12 * 4 + suit 3 = index 51

### Move Validation
The game validates all moves according to Xì Tố rules:
- Correct card combinations for each move type
- Consecutive ranks for sequences
- Same rank for pairs, triples, four of a kind
- No 2s in sequences
- Bomb detection

### AI Decision Making
1. Encode current game state
2. Run through neural network to get Q-values for all actions
3. With ε-greedy policy:
   - With probability ε: choose random valid move (exploration)
   - With probability 1-ε: choose move with highest Q-value (exploitation)
4. Train on game outcomes to improve future decisions

## Dependencies

- Next.js 16.2.6
- React 19.2.6
- Drizzle ORM 0.45.2
- PostgreSQL
- UUID
- Tailwind CSS

## Environment Variables

```
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/app_db
```

## Running the Application

```bash
# Install dependencies
npm install

# Push database schema
npx drizzle-kit push

# Start development server
npm run dev

# Build and start production server
npm run build
npm run start
```

## Future Enhancements

- [ ] Multiplayer online support
- [ ] More sophisticated training algorithms
- [ ] Model version comparison
- [ ] Game replay functionality
- [ ] Advanced statistics and analytics
- [ ] Custom rule variations
- [ ] Mobile-responsive UI improvements

## License

MIT License

## Credits

- Game rules based on traditional Vietnamese Xì Tố (Tiến Lên)
- Neural network inspired by NNUE (Efficiently Updatable Neural Network)
- Built with Next.js, React, and Drizzle ORM
