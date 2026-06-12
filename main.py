"""Entry point — pregame setup, starts engine + pygame."""

import asyncio
import pygame
from engine.game_state import GameState
from engine.engine import setup_game, run_game
from engine.llm import set_mock
from frontend.renderer import init_display, render, handle_events, get_lobby_config, is_mock_mode


async def main():
    game_state = GameState()
    screen = init_display()

    clock = pygame.time.Clock()
    running = True
    game_task = None

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue

            action = handle_events(event, game_state)
            if action == "quit":
                running = False
            elif action == "to_menu":
                if game_task and not game_task.done():
                    game_task.cancel()
                    game_task = None
                # Reset game state for a fresh start next time
                game_state.phase = "pregame"
                game_state.players.clear()
                game_state.bodies.clear()
                game_state.meeting_log.clear()
                game_state.vote_results = None
                game_state.winner = None
            elif action == "start_game":
                config = get_lobby_config()
                if config:
                    from frontend.renderer import _event_log
                    _event_log.clear()
                    set_mock(is_mock_mode())

                    roster = []
                    for p in config["players"]:
                        roster.append({
                            "color": p["color"],
                            "model": p["model"],
                            "role": "crewmate",
                        })

                    setup_game(game_state, roster, config["task_count"])
                    game_task = asyncio.create_task(run_game(game_state))

        render(screen, game_state)
        pygame.display.flip()
        clock.tick(60)
        await asyncio.sleep(0)

    if game_task and not game_task.done():
        game_task.cancel()
    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
