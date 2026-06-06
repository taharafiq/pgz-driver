# Treasure Town

A Pygame Zero arcade game. Explore a small town and grab as many treasures as
you can before the 45-second timer runs out!

- **Coins** = +10  ·  **Keys** = +25  ·  **Gem chests** = +50
- Treasures respawn as you collect them, so there's always something to grab.
- Houses, trees and bushes are obstacles you have to weave around.

## Controls

- **Arrow keys** or **WASD** — move
- **SPACE** — start / play again
- **M** — back to the menu (on the game-over screen)
- **Q** — quit (from the menu)

## Screens

1. **Menu** — title, the treasure values, and the current high score.
2. **Play** — the town, with your score and remaining time in the top bar.
3. **Game over** — your final score, with a "New High Score!" callout when you beat it.

The high score persists between runs in `highscore.json`.

## Run

From the repo root (uses the project's virtualenv / pgzero):

```bash
.venv/bin/python games/collect-treasure/collect_treasure.py
```

or with the Pygame Zero runner:

```bash
.venv/bin/pgzrun games/collect-treasure/collect_treasure.py
```

Art: [Kenney](https://kenney.nl) "Tiny Town" tiles and "Roguelike Characters"
(both CC0), loaded from `../assets`.
