"""Behavior state handlers: one function per brain state, grouped by theme.

Brain._continue dispatches through REGISTRY instead of one long if/elif chain.
"""

from __future__ import annotations

from plasmacat.cat.behaviors import care, furniture, human, motion, play, rest, social

REGISTRY: dict = {}
for _mod in (motion, rest, care, furniture, social, play, human):
    for _name, _fn in _mod.STATES.items():
        assert _name not in REGISTRY, f"state {_name!r} handled twice"
        REGISTRY[_name] = _fn
del _mod, _name, _fn
