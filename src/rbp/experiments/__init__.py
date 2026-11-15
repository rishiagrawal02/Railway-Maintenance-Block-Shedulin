"""Experiments package."""

__all__ = ["RunRecord", "run_grid"]


def __getattr__(name):
    # Keep package-level imports without preloading the module used by python -m.
    if name in __all__:
        from . import runner
        return getattr(runner, name)
    raise AttributeError(name)
