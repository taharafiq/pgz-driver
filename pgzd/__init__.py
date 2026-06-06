"""pgzd — headless Pygame Zero driver for agents.

A persistent daemon runs a Pygame Zero game without a display window; a thin
CLI client (`pgz`) injects keyboard/mouse input and captures screenshots so an
agent can inspect and play the game.  See `pgzd.cli` for the command surface.
"""

__all__ = ["PgzDriver"]


def __getattr__(name):
    # Lazy import so that merely importing the package (e.g. for the client)
    # does not pull in pygame.
    if name == "PgzDriver":
        from pgzd.driver import PgzDriver
        return PgzDriver
    raise AttributeError(name)
