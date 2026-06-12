"""Turn loop, resolution order, win checks."""


async def run_turn(game_state):
    raise NotImplementedError


async def run_meeting_phase(game_state):
    raise NotImplementedError


def check_win_conditions(game_state) -> str | None:
    raise NotImplementedError
