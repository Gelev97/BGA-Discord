"""ELO calculation utilities."""


def apply_score_change(
	current_score: float,
	raw_bga_change: float,
	game_weight: float,
	volatility_cap: float = 15.0,
	floor: float = 100.0,
	ceiling: float = 1000.0,
) -> float:
	"""Apply a single BGA elo change to the current score."""
	clamped = max(-volatility_cap, min(raw_bga_change, volatility_cap))
	weighted_change = clamped * game_weight

	if weighted_change <= 0:
		current_score += weighted_change
		return max(current_score, floor)

	multiplier = 1.0 - (current_score / ceiling)
	actual_gain = weighted_change * multiplier
	current_score += actual_gain
	return min(current_score, ceiling)


def bga_win_rate(wins_by_pc: dict, games_by_pc: dict) -> float:
	"""Calculate BGA-style win rate from cumulative counts.

	wins_by_pc / games_by_pc: {"2": N, "3": N, ...} keyed by player count.
	"""
	total_rate = 0.0
	total_games = 0
	for pc_str, games in games_by_pc.items():
		pc = int(pc_str)
		wins = wins_by_pc.get(pc_str, 0)
		total_rate += wins * 50.0 * pc
		total_games += games
	if total_games == 0:
		return 0.0
	return total_rate / total_games
