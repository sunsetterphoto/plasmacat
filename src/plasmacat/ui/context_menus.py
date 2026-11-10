"""Right-click menus: the cat and every thing in her home answer a right
click with the actions that make sense for it.

entries_for() is pure data — (label, callback) pairs, None for a separator,
a None callback for an info line — so it is testable without a menu.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

from plasmacat.cat.needs import FOODS
from plasmacat.ui.tray import mood_word

LABELS = {"food_bowl": "Food bowl", "water_fountain": "Water fountain",
          "scratch_post": "Scratching post", "cat_bed": "Cat bed",
          "cat_grass": "Cat grass", "litter_0": "Litter box", "cat_tree": "Cat tree",
          "wheel_stand": "Exercise wheel", "box": "Cardboard box", "wall_shelf": "Wall shelf"}


def entries_for(ctl, thing) -> list:
    ov = ctl.overlay
    kind = thing[0]
    if kind == "cat":
        cat = thing[1]
        b = cat.brain
        steering = ov._control_on
        return [
            (f"{cat.cust.name} · {b.life_stage} · {mood_word(b.mood)}", None),
            None,
            ("Pet", lambda: b.on_stroke(cat.body)),
            ("Give treat", lambda: ctl.give_treat(cat)),
            ("Wave a string", lambda: ctl.toggle_string(True)),
            ("Laser pointer", lambda: ctl.toggle_laser(True)),
            ("Stop steering" if steering else "Steer her (WASD / arrows)",
             lambda: ctl.set_control(not steering)),
            None,
            ("Appearance…", lambda: ctl.customize(cat)),
            ("Control Center…", lambda: ctl.open_center("cats")),
            ("Pause cats", lambda: ctl.set_paused(True)),
        ]
    if kind == "toy":
        toy = thing[1]
        return [
            ("Ball" if toy.kind == "ball" else "Plush mouse", None),
            None,
            ("Toss it", lambda: ctl.toss_toy(toy)),
            ("Move", lambda: ctl.move_toy(toy)),
            ("Put away", lambda: ctl.remove_toy(toy)),
        ]
    if kind == "puke":
        return [("Clean up", ctl.clean_puke)]
    if kind == "status":
        return [("Status board", None), None,
                ("Move", ctl.place_status_board),
                ("Hide", lambda: ctl.update_settings(status_board=False)),
                ("Choose rows…", lambda: ctl.open_center("home"))]
    _p, prop, index = thing
    b = ov.cat.brain
    out: list = [(LABELS.get(prop, prop), None), None]
    if prop == "food_bowl":
        out.insert(1, (f"Food: {FOODS[b.food_type]['label']} · {int(b.food_fill)} % full", None))
        out.append(("Refill", ctl.refill_food))
        for fid, food in FOODS.items():
            if fid != b.food_type:
                out.append((f"Serve {food['label']}", lambda f=fid: ctl.buy_food(f)))
        out.append(None)
    elif prop == "litter_0":
        n = len(b.litter_deposits)
        out.append((f"Clean ({n})" if n else "Clean (nothing to do)",
                    ctl.clean_litter if n else None))
        out.append(None)
    out.append(("Move", lambda: ov.begin_move(prop, index)))
    if prop not in ov.BOWLS:
        out.append(("Remove", lambda: ctl.remove_furniture(prop, index)))
    out.append(("Arrange everything…", ctl.arrange))
    return out


def show_menu(ctl, thing, global_pos, widget) -> None:
    """Pop the menu for a right-clicked cat or thing."""
    menu = QMenu(widget)
    for entry in entries_for(ctl, thing):
        if entry is None:
            menu.addSeparator()
            continue
        label, callback = entry
        action = menu.addAction(label)
        if callback is None:
            action.setEnabled(False)
        else:
            action.triggered.connect(lambda _c=False, cb=callback: cb())
    menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    menu.popup(global_pos)
