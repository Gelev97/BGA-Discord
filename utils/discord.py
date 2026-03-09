"""Discord webhook messaging utilities."""

import requests
from typing import Dict, List, Any, Optional, Tuple


def send_embed(webhook: str, embed: Dict[str, Any]) -> bool:
	"""Send a single embed to a Discord webhook."""
	try:
		response = requests.post(webhook, json={"embeds": [embed]}, timeout=10)
		if response.status_code == 204:
			return True
		print(f"Discord embed failed: {response.status_code}")
		return False
	except Exception as e:
		print(f"Discord embed error: {e}")
		return False


def print_embed(embed: Dict[str, Any]) -> None:
	"""Print a Discord embed to console for debugging."""
	print(f"\n{'='*60}")
	print(f"[EMBED] {embed.get('title', 'No title')}")
	print(f"{'='*60}")
	if "description" in embed:
		print(embed["description"])
	if "footer" in embed:
		print(f"\n({embed['footer']['text']})")
	print()


def format_update(
	new_tables_log: List[Tuple[dict, dict]],
	player_stats: Dict[str, dict],
	previous_elos: Dict[str, float],
) -> Optional[Dict[str, Any]]:
	"""Format update message showing new tables and ELO changes.

	new_tables_log: [(table_data, {player: elo_delta}), ...]
	"""
	if not new_tables_log:
		return None

	# Per-table lines
	table_lines = []
	for table_data, elo_log in new_tables_log:
		game_name = table_data.get("game_name", "Unknown")
		parts = []
		for name, delta in elo_log.items():
			parts.append(f"{name} {delta:+.1f}")
		if parts:
			table_lines.append(f"**{game_name}**: {', '.join(parts)}")
		else:
			table_lines.append(f"**{game_name}**")

	# ELO change summary
	elo_lines = []
	for name, stats in sorted(
		player_stats.items(),
		key=lambda x: x[1]["custom_elo"],
		reverse=True,
	):
		new_elo = stats["custom_elo"]
		old_elo = previous_elos.get(name, 100.0)
		diff = new_elo - old_elo
		if diff > 0.5:
			elo_lines.append(f"{name}: {old_elo:.1f} → {new_elo:.1f} (↑{diff:.1f})")
		elif diff < -0.5:
			elo_lines.append(f"{name}: {old_elo:.1f} → {new_elo:.1f} (↓{abs(diff):.1f})")

	desc = f"**New Tables ({len(new_tables_log)}):**\n"
	desc += "\n".join(table_lines)
	if elo_lines:
		desc += "\n\n**ELO Changes:**\n"
		desc += "\n".join(elo_lines)

	return {
		"title": "Weekly Update",
		"description": desc,
		"color": 0x9b59b6,
	}


def format_leaderboard(
	player_stats: Dict[str, dict],
	previous_elos: Dict[str, float],
) -> Dict[str, Any]:
	"""Format leaderboard with ELO change arrows, sorted by ELO."""
	sorted_players = sorted(
		player_stats.items(),
		key=lambda x: x[1]["custom_elo"],
		reverse=True,
	)

	lines = []
	for i, (name, stats) in enumerate(sorted_players):
		medal = ["1st", "2nd", "3rd"][i] if i < 3 else f"{i+1}th"
		elo = stats["custom_elo"]
		wr = stats["win_rate"]
		wins = stats["total_wins"]
		games = stats["total_games"]

		old_elo = previous_elos.get(name, 100.0)
		diff = elo - old_elo
		if diff > 0.5:
			change = f" ↑{diff:.0f}"
		elif diff < -0.5:
			change = f" ↓{abs(diff):.0f}"
		else:
			change = ""

		lines.append(
			f"**{medal}** {name} — ELO: {elo:.1f}{change} | {wr:.1f}% ({wins}/{games})"
		)

	return {
		"title": "BGA Leaderboard",
		"description": "\n".join(lines),
		"color": 0x3498db,
		"footer": {"text": "ELO weighted by game competitiveness. ↑↓ = change since last update."},
	}


def format_game_details(
	game_stats: Dict[str, dict],
	min_tables: int = 30,
) -> List[Dict[str, Any]]:
	"""Format game breakdown — only games with 30+ total tables.
	Shows winner (highest win rate) with crown emoji.
	"""
	eligible = [
		(gid, gs) for gid, gs in game_stats.items()
		if gs["total_tables"] >= min_tables
	]
	eligible.sort(key=lambda x: x[1]["total_tables"], reverse=True)

	if not eligible:
		return []

	lines = []
	for game_id, gs in eligible:
		name = gs["game_name"]
		total = gs["total_tables"]

		# Find winner: highest win rate, tiebreak by more plays
		players_with_rate = []
		for pname, pdata in gs["players"].items():
			plays = pdata["plays"]
			wins = pdata["wins"]
			rate = wins / plays if plays > 0 else 0
			players_with_rate.append((pname, rate, plays, wins))

		# Sort by rate desc, then plays desc
		players_with_rate.sort(key=lambda x: (x[1], x[2]), reverse=True)

		if not players_with_rate:
			continue

		# Check for ties at top
		top_rate = players_with_rate[0][1]
		top_plays = players_with_rate[0][2]
		winners = [p for p in players_with_rate if p[1] == top_rate and p[2] == top_plays]
		if len(winners) == 1:
			winner_str = winners[0][0]
		else:
			winner_str = ", ".join(w[0] for w in winners)

		lines.append(f"**{name}** ({total} games) 👑 {winner_str}")

	desc = "\n".join(lines)
	desc += "\n\n*Only games with 30+ total plays across all players are shown.*"

	return [{
		"title": "Game Breakdown",
		"description": desc,
		"color": 0xe67e22,
	}]
