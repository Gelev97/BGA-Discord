"""Board Game Arena custom ELO tracker and win rate analyzer."""

import os
import time
from datetime import datetime
from typing import Dict, Optional, Any

from utils.bga import BGAClient
from utils.calculations import apply_score_change, bga_win_rate
from utils.data import load_database, save_database
from utils.discord import (
	send_embed,
	print_embed,
	format_update,
	format_leaderboard,
	format_game_details,
)


DATABASE_FILE = "data/bga_games_database.json"

USER_LIST = {
	"85361014": "Gelev",
	"97981932": "matthewcrumby",
	"98250223": "xuzheng863",
	"98366299": "YEYE",
	"98343487": "StinsonOvO",
	"93577018": "simonzhushiyu",
	"97997444": "mashiro66",
}

NAME_ALIASES = {
	"Gelev": "Gelev",
	"gggggggg12": "Gelev",
	"matthewcrumby": "matthewcrumby",
	"xuzheng863": "xuzheng863",
	"YEYE": "YEYE",
	"StinsonOvO": "StinsonOvO",
	"simonzhushiyu": "simonzhushiyu",
	"mashiro66": "mashiro66",
}


def ensure_player(db, name):
	"""Ensure player exists in player_stats."""
	if name not in db["player_stats"]:
		db["player_stats"][name] = {
			"custom_elo": 100.0,
			"total_games": 0,
			"total_wins": 0,
			"wins_by_player_count": {},
			"games_by_player_count": {},
		}


def ensure_game(db, game_id, game_name):
	"""Ensure game exists in game_stats."""
	if game_id not in db["game_stats"]:
		db["game_stats"][game_id] = {
			"game_name": game_name,
			"total_tables": 0,
			"players": {},
		}


def process_table(db, table_data, game_metadata, user_names, cooperative_games):
	"""Process one table: update player_stats and game_stats in db.

	Returns a log dict {player: elo_delta} for the update message, or None if skipped.
	"""
	game_id = table_data.get("game_id", "")
	game_name = table_data.get("game_name", "Unknown")

	# Skip cooperative
	if game_id in cooperative_games:
		return None
	if str(table_data.get("ranking_disabled", "0")) == "1":
		cooperative_games.add(game_id)
		return None

	is_friendly = str(table_data.get("unranked", "0")) == "1"
	players = table_data.get("players", {})
	num_players = len(table_data.get("all_player_names", []))
	if num_players < 2:
		num_players = len(players)
	if num_players < 2:
		return None

	pc_str = str(num_players)

	# Get game weight
	meta = game_metadata.get(game_id, {})
	max_elo = meta.get("max_elo", 0) or 0
	ensure_game(db, game_id, game_name)

	# Count this table
	db["game_stats"][game_id]["total_tables"] += 1

	# Check if all group members below 1400
	group_in_table = {n: players[n] for n in user_names if n in players}
	all_below_100 = all(
		(p.get("elo_after", 0) or 0) < 1400
		for p in group_in_table.values()
	) if group_in_table else False

	base_weight = min(max_elo / 1000.0, 1.0)
	elo_log = {}

	for name in user_names:
		if name not in players:
			continue
		pdata = players[name]
		rank = pdata.get("rank", 0)
		won = rank == 1

		ensure_player(db, name)
		ps = db["player_stats"][name]
		gs_players = db["game_stats"][game_id]["players"]

		# Game stats
		if name not in gs_players:
			gs_players[name] = {"plays": 0, "wins": 0}
		gs_players[name]["plays"] += 1
		if won:
			gs_players[name]["wins"] += 1

		# Win rate counts (all non-cooperative, including friendly)
		ps["total_games"] += 1
		ps["games_by_player_count"][pc_str] = ps["games_by_player_count"].get(pc_str, 0) + 1
		if won:
			ps["total_wins"] += 1
			ps["wins_by_player_count"][pc_str] = ps["wins_by_player_count"].get(pc_str, 0) + 1

		# ELO (ranked only)
		if not is_friendly:
			weight = base_weight
			if all_below_100:
				weight /= 5.0
			raw_change = pdata.get("elo_change", 0)
			old_elo = ps["custom_elo"]
			ps["custom_elo"] = apply_score_change(old_elo, raw_change, weight)
			delta = ps["custom_elo"] - old_elo
			if abs(delta) > 0.01:
				elo_log[name] = delta

	return elo_log


def run(first_time: bool = False) -> None:
	"""Main entry point."""
	username = os.environ.get("BGA_USERNAME")
	password = os.environ.get("BGA_PASSWORD")
	webhook = os.environ.get("DISCORD_WEBHOOK")

	if not username or not password:
		print("Error: BGA_USERNAME and BGA_PASSWORD environment variables required")
		return

	client = BGAClient(username, password)
	if not client.login():
		print("Failed to login to BGA")
		return

	db = load_database(DATABASE_FILE)
	previous_elos = dict(db.get("previous_elos", {}))
	cooperative_games = set(db.get("cooperative_games", []))
	game_metadata: Dict[str, Any] = {}  # fetched fresh each run

	user_names = list(set(USER_LIST.values()))
	user_ids = list(USER_LIST.keys())

	# Ensure all players exist
	for name in user_names:
		ensure_player(db, name)

	# Determine start date
	if first_time:
		start_ts = "1609459200"  # 2021-01-01
	elif db.get("last_update"):
		start_ts = str(int(datetime.strptime(db["last_update"], "%Y-%m-%d %H:%M:%S").timestamp()))
	else:
		start_ts = "1609459200"

	print(f"Searching games from timestamp {start_ts} to now")
	print(f"Known cooperative games: {len(cooperative_games)}")

	seen_table_ids = set()
	new_tables_log = []  # [(table_data, elo_log)]

	for i, pid in enumerate(user_ids):
		for j, oid in enumerate(user_ids):
			if i == j:
				continue

			pname = USER_LIST[pid]
			oname = USER_LIST[oid]
			print(f"  Fetching games: {pname} vs {oname}")

			raw_tables = client.fetch_games(pid, oid, start_ts)

			for raw in raw_tables:
				table_id = str(raw.get("table_id", ""))
				game_id = str(raw.get("game_id", ""))
				game_name = raw.get("game_name", "Unknown")

				if not table_id or not game_id:
					continue

				# Detect cooperative
				if str(raw.get("ranking_disabled", "0")) == "1":
					cooperative_games.add(game_id)

				# Parse table (only first time we see this table_id)
				if table_id not in seen_table_ids:
					seen_table_ids.add(table_id)

					all_names = [
						n.strip()
						for n in raw.get("player_names", "").split(",")
						if n.strip()
					]
					ranks_raw = raw.get("ranks", "").split(",")
					scores_raw = raw.get("scores", "").split(",")

					players_data = {}
					for idx, display_name in enumerate(all_names):
						canonical = NAME_ALIASES.get(display_name)
						if canonical is None:
							continue
						rank = 0
						if idx < len(ranks_raw) and ranks_raw[idx].strip().isdigit():
							rank = int(ranks_raw[idx].strip())
						score = 0
						if idx < len(scores_raw) and scores_raw[idx].strip().lstrip("-").isdigit():
							score = int(scores_raw[idx].strip())
						players_data[canonical] = {
							"rank": rank,
							"score": score,
							"elo_change": 0,
							"elo_after": 0,
						}

					# Store table temporarily for processing
					seen_table_ids.add(table_id)
					# We'll store it in a dict for elo updates from other perspectives
					if "_pending_tables" not in db:
						db["_pending_tables"] = {}
					db["_pending_tables"][table_id] = {
						"game_id": game_id,
						"game_name": game_name,
						"all_player_names": all_names,
						"unranked": raw.get("unranked", "0"),
						"normalend": raw.get("normalend", "1"),
						"concede": raw.get("concede", "0"),
						"ranking_disabled": raw.get("ranking_disabled", "0"),
						"players": players_data,
					}

				# Update ELO data from this player's perspective
				elo_win = raw.get("elo_win") or raw.get("elo_penalty") or 0
				try:
					elo_win = float(elo_win)
				except (ValueError, TypeError):
					elo_win = 0

				elo_after = raw.get("elo_after") or 0
				try:
					elo_after = float(elo_after)
				except (ValueError, TypeError):
					elo_after = 0

				canonical_pname = NAME_ALIASES.get(pname, pname)
				pending = db.get("_pending_tables", {}).get(table_id, {})
				if canonical_pname in pending.get("players", {}):
					if elo_win != 0 or pending["players"][canonical_pname].get("elo_change", 0) == 0:
						pending["players"][canonical_pname]["elo_change"] = elo_win
					if elo_after != 0 or pending["players"][canonical_pname].get("elo_after", 0) == 0:
						pending["players"][canonical_pname]["elo_after"] = elo_after

				# Fetch game metadata for new games
				if game_id not in game_metadata and game_id not in cooperative_games:
					max_elo = client.get_game_max_elo(game_id)
					game_metadata[game_id] = {"game_name": game_name, "max_elo": max_elo}
					time.sleep(0.3)

			time.sleep(0.3)

	# Process all pending tables
	pending_tables = db.pop("_pending_tables", {})
	print(f"\nNew tables to process: {len(pending_tables)}")

	for table_id, table_data in pending_tables.items():
		elo_log = process_table(db, table_data, game_metadata, user_names, cooperative_games)
		if elo_log is not None:
			new_tables_log.append((table_data, elo_log))

	# Update cooperative_games list
	db["cooperative_games"] = sorted(cooperative_games)

	# Compute win rates for display
	player_display = {}
	for name in user_names:
		ps = db["player_stats"][name]
		player_display[name] = {
			"custom_elo": ps["custom_elo"],
			"total_games": ps["total_games"],
			"total_wins": ps["total_wins"],
			"win_rate": bga_win_rate(ps["wins_by_player_count"], ps["games_by_player_count"]),
		}

	# Print leaderboard
	print("\n--- Leaderboard (sorted by ELO) ---")
	sorted_by_elo = sorted(player_display.items(), key=lambda x: x[1]["custom_elo"], reverse=True)
	for name, stats in sorted_by_elo:
		old_elo = previous_elos.get(name, 100.0)
		diff = stats["custom_elo"] - old_elo
		change = f" (↑{diff:.1f})" if diff > 0.5 else f" (↓{abs(diff):.1f})" if diff < -0.5 else ""
		print(f"  {name}: ELO={stats['custom_elo']:.1f}{change}  WinRate={stats['win_rate']:.1f}% ({stats['total_wins']}/{stats['total_games']})")

	# Build Discord embeds
	embeds = []

	update_embed = format_update(new_tables_log, player_display, previous_elos)
	if update_embed:
		embeds.append(update_embed)

	embeds.append(format_leaderboard(player_display, previous_elos))
	embeds.extend(format_game_details(db["game_stats"]))

	if webhook:
		for embed in embeds:
			send_embed(webhook, embed)
	else:
		for embed in embeds:
			print_embed(embed)

	# Save — update previous_elos and timestamp
	db["previous_elos"] = {name: ps["custom_elo"] for name, ps in db["player_stats"].items()}
	db["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

	# Clean: only save the 5 items
	save_data = {
		"game_stats": db["game_stats"],
		"cooperative_games": db["cooperative_games"],
		"player_stats": db["player_stats"],
		"previous_elos": db["previous_elos"],
		"last_update": db["last_update"],
	}
	save_database(DATABASE_FILE, save_data)
	print("Database saved.")

	if client.logout():
		print("Logged out from BGA.")
	else:
		print("Warning: Logout may have failed.")


if __name__ == "__main__":
	run(first_time=False)
