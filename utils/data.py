"""Database persistence utilities."""

import json
import os
from typing import Dict, Any


def load_database(path: str) -> Dict[str, Any]:
	"""Load game database from JSON file."""
	if os.path.exists(path):
		try:
			with open(path, "r") as f:
				return json.load(f)
		except (json.JSONDecodeError, IOError):
			pass
	return {
		"game_stats": {},
		"cooperative_games": [],
		"player_stats": {},
		"previous_elos": {},
		"last_update": None,
	}


def save_database(path: str, data: Dict[str, Any]) -> None:
	"""Save game database to JSON file."""
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w") as f:
		json.dump(data, f, indent=2)
