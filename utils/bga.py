"""BGA API client for authentication and data fetching."""

import re
import time
import requests
from typing import Optional, Dict, List, Any


class BGAClient:
	"""Handles all communication with the Board Game Arena API."""

	BASE_URL = "https://boardgamearena.com"

	def __init__(self, username: str, password: str):
		self._username = username
		self._password = password
		self._session = requests.Session()
		self._request_token = None
		self._cooperative_cache: Dict[str, bool] = {}
		self._max_elo_cache: Dict[str, Optional[int]] = {}

		self._session.headers.update({
			"User-Agent": (
				"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
				"(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
			),
			"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
			"Accept-Language": "en-US,en;q=0.5",
			"Connection": "keep-alive",
		})

	def _get_request_token(self) -> bool:
		try:
			resp = self._session.get(f"{self.BASE_URL}/account")
			if resp.status_code != 200:
				print(f"Failed to access /account page: HTTP {resp.status_code}")
				return False
			match = re.search(r"requestToken:\s*['\"]([^'\"]*)['\"]", resp.text)
			if match:
				self._request_token = match.group(1)
				return True
			print("Could not find request token")
			return False
		except Exception as e:
			print(f"Error getting request token: {e}")
			return False

	def login(self) -> bool:
		print(f"Logging in to BGA as: {self._username}")
		if not self._get_request_token():
			return False
		print(f"Found request token: {self._request_token[:10]}...")

		login_url = f"{self.BASE_URL}/account/account/login.html"
		login_data = {
			"email": self._username,
			"password": self._password,
			"rememberme": "on",
			"redirect": "direct",
			"request_token": self._request_token,
			"form_id": "loginform",
			"dojo.preventCache": str(int(time.time())),
		}
		try:
			response = self._session.post(login_url, data=login_data)
			print(f"Login response: HTTP {response.status_code}")
			return True
		except Exception as e:
			print(f"Login error: {e}")
			return False

	def logout(self) -> bool:
		try:
			url = f"{self.BASE_URL}/account/account/logout.html"
			params = {"dojo.preventCache": str(int(time.time()))}
			response = self._session.get(url, params=params)
			return response.status_code == 200
		except Exception as e:
			print(f"Logout error: {e}")
			return False

	def fetch_games(self, player_id: str, opponent_id: str, start_date: str, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
		"""Fetch all game tables between two players from player's perspective.

		Returns raw table dicts with all available fields from BGA API.
		The elo_win/elo_after fields reflect the 'player_id' player's data.
		"""
		url = f"{self.BASE_URL}/gamestats/gamestats/getGames.html"
		headers = {
			"x-request-token": self._request_token,
			"Referer": url,
			"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
		}

		all_tables = []
		page = 1

		while True:
			params = {
				"player": player_id,
				"opponent_id": opponent_id,
				"start_date": start_date,
				"end_date": end_date if end_date else str(int(time.time())),
				"updateStats": "0",
				"page": str(page),
				"finished": "1",
			}
			try:
				response = self._session.post(url, headers=headers, data=params)
				if response.status_code != 200:
					print(f"Failed to get games page {page}: HTTP {response.status_code}")
					break

				data = response.json().get("data", {})
				tables = data.get("tables", [])
				if not tables:
					break

				all_tables.extend(tables)
				page += 1
				time.sleep(0.5)

			except Exception as e:
				print(f"Error getting games page {page}: {e}")
				break

		return all_tables

	def get_game_max_elo(self, game_id: str) -> Optional[int]:
		"""Get the top player's ELO for a game (above base 1300).

		Returns None if the game has no ELO rankings (cooperative game).
		Results are cached per game_id.
		"""
		if game_id in self._max_elo_cache:
			return self._max_elo_cache[game_id]

		try:
			url = f"{self.BASE_URL}/gamepanel/gamepanel/getRanking.html"
			params = {"game": game_id, "mode": "elo", "start": "0"}
			headers = {
				"x-request-token": self._request_token,
				"Referer": url,
				"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
			}

			response = self._session.post(url, headers=headers, data=params)
			if response.status_code != 200:
				self._max_elo_cache[game_id] = None
				return None

			ranks = response.json().get("data", {}).get("ranks", [])
			if ranks:
				top_elo = max(0, round(float(ranks[0].get("ranking", 1300)) - 1300))
				self._max_elo_cache[game_id] = top_elo
				return top_elo

			self._max_elo_cache[game_id] = None
			return None

		except Exception as e:
			print(f"Error getting max ELO for game {game_id}: {e}")
			self._max_elo_cache[game_id] = None
			return None

