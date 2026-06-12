"""Entry point — pregame setup, starts engine + pygame."""

import asyncio
import pygame
from engine.game_state import GameState
from frontend.renderer import init_display, render, handle_events


async def main():
    game_state = GameState()
    screen = init_display()

    clock = pygame.time.Clock()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            handle_events(game_state)

        render(screen, game_state)
        pygame.display.flip()
        clock.tick(60)

        await asyncio.sleep(0)  # yield to asyncio event loop

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
