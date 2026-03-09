# BGA Discord Bot — Custom ELO & Win Rate Tracker

Scrapes game data from Board Game Arena (BGA), computes custom ELO scores weighted by game competitiveness, calculates BGA-style win rates, and posts results to Discord.

## System Constants

* **Starting Score:** 100
* **Minimum Score (Hard Floor):** 100
* **Maximum Score (Hard Ceiling):** 1000
* **Volatility Cap:** ±15 BGA points per match

## Step-by-Step ELO Calculation

### 1. Volatility Cap (Shock Absorber)

New games on BGA trigger massive ELO swings (e.g. +60, +97). To prevent these from breaking the leaderboard, the raw BGA ELO change is clamped to **±15** before any math is applied.

### 2. Game Weight (Difficulty)

The clamped change is multiplied by a **weight** based on how competitive the game is globally on BGA:

```
weight = min(top_player_elo_above_1300 / 1000, 1.0)
```

For example, if a game's #1 player has ELO 2067 (767 above base 1300), the weight is `0.767`. More competitive games = higher weight = bigger impact.

### 3. Anti-Abuse: Beginner Penalty (/5)

If **all tracked group members** in a table have BGA ELO below 1400 (less than 100 above the 1300 base) in that game, the weight is **divided by 5**. This prevents farming easy ELO by spamming new games where everyone is a beginner.

### 4. Handling Losses (The Floor)

If the weighted change is negative, it is subtracted from the player's current score.

* A player's score **cannot drop below 100**.

### 5. Handling Wins (The Gravity Tax)

If the weighted change is positive, a diminishing returns multiplier is applied:

```
multiplier = 1 - (current_score / 1000)
actual_gain = weighted_change * multiplier
```

* At score 100: keep 90% of gains
* At score 500: keep 50% of gains
* At score 900: keep only 10% of gains
* Score **cannot exceed 1000**

## Game Filtering

### Cooperative Games
Games where BGA sets `ranking_disabled = 1` are **excluded entirely** (e.g. Hanabi). These have no competitive ranking — all players share the same rank.

### Friendly / Unranked Games
Games where `unranked = 1`:
* **Excluded from ELO** calculation
* **Included in win rate** calculation

### Win Rate (BGA-Style)

Win rate is normalized so the expected average is always 50% regardless of player count:

```
winner gets:     50% * num_players
non-winners get: 0%
overall rate:    average across all games
```

A dominant player can exceed 100%. A player who never wins has 0%.

## Player Name Aliases

Players can change their BGA display name. The `NAME_ALIASES` map in `bga_stats.py` maps all known display names to a canonical name, so stats are merged correctly (e.g. `gggggggg12` → `Gelev`).

## Architecture

* `bga_stats.py` — Main entry point: scrape, analyze, report, save
* `utils/bga.py` — BGA API client (login, fetch games, get max ELO)
* `utils/calculations.py` — Custom ELO and win rate computation
* `utils/discord.py` — Discord webhook formatting and sending
* `utils/data.py` — JSON database load/save
* `data/bga_games_database.json` — Persistent game database
