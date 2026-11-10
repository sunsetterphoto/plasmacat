"""First run: meet your kitten (appearance editor with a short intro)."""

from __future__ import annotations

from plasmacat.persist import Customization
from plasmacat.ui.appearance_editor import AppearanceDialog

INTRO = ("<b>Welcome to PlasmaCat!</b> Meet your kitten — choose her look below.<br><br>"
         "• Pet her by moving your cursor <i>slowly</i> over her.<br>"
         "• Everything lives behind the PlasmaCat icon in your system tray "
         "(left click opens the Control Center).<br>"
         "• Start by placing a food bowl and a water fountain in the <b>Home</b> tab.")


def first_run(initial: Customization | None = None) -> Customization | None:
    return AppearanceDialog(initial, stage=0, title="PlasmaCat — Your new kitten",
                            intro=INTRO).customization()
