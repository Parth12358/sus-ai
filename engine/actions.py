"""Action validation and resolution logic."""


def validate_action(player, action: dict, game_state) -> bool:
    raise NotImplementedError


def resolve_action(player, action: dict, game_state):
    raise NotImplementedError
