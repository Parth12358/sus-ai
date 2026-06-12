"""OpenRouter API calls, prompt building, response parsing."""


async def get_player_action(game_state, player):
    raise NotImplementedError


def build_turn_context(game_state, player) -> str:
    raise NotImplementedError


def parse_response(raw: str) -> dict:
    raise NotImplementedError
