"""Pygame rendering — reads GameState and event_queue."""

import pygame
from engine.game_state import GameState


def init_display(width: int = 1200, height: int = 800, title: str = "LLM Among Us"):
    pygame.init()
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption(title)
    return screen


def render(screen: pygame.Surface, game_state: GameState):
    pass


def handle_events(game_state: GameState):
    pass
