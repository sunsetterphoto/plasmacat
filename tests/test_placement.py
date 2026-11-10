"""Placement / arrange mode and fullscreen hiding (headless, fake bridge)."""
import pytest
from conftest import dispose
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from plasmacat.persist import Settings


@pytest.fixture
def overlay(qapp):
    from plasmacat.bridge.kwin import FakeBridge
    from plasmacat.world.overlay import Overlay
    b = FakeBridge()
    ov = Overlay(b, settings=Settings())
    b.start()
    ov.bridge_for_test = b
    yield ov
    dispose(*ov.furniture_layers, ov)


def click(ov, x, y, button=Qt.MouseButton.LeftButton):
    ov.desktop.set_cursor(int(x), int(y))
    ov.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y),
                                   QPointF(x, y), button, button,
                                   Qt.KeyboardModifier.NoModifier))


def key(ov, k):
    ov.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier))


def test_esc_cancels_placement(overlay):
    overlay.begin_placement("cat_bed")
    key(overlay, Qt.Key.Key_Escape)
    assert overlay._placing is None
    assert overlay.cat.brain.bed_x is None


def test_click_existing_prop_picks_it_up(overlay):
    b = overlay.cat.brain
    b.bed_x = 800.0
    overlay.begin_arrange()
    r = overlay._prop_rect("cat_bed", None)
    click(overlay, r.center().x(), r.center().y())
    assert overlay._placing == "cat_bed"          # carrying it now
    click(overlay, 1200, 600)
    assert b.bed_x == 1200.0
    assert overlay._placing is None


def test_delete_removes_the_prop_under_the_cursor(overlay):
    b = overlay.cat.brain
    b.tree_x = 700.0
    overlay.begin_arrange()
    r = overlay._prop_rect("cat_tree", None)
    overlay.desktop.set_cursor(r.center().x(), r.center().y())
    key(overlay, Qt.Key.Key_Delete)
    assert b.tree_x is None


def test_bowls_are_never_deleted(overlay):
    b = overlay.cat.brain
    overlay.begin_arrange()
    r = overlay._prop_rect("food_bowl", None)
    overlay.desktop.set_cursor(r.center().x(), r.center().y())
    key(overlay, Qt.Key.Key_Delete)
    assert b.food_x is not None


def test_fullscreen_hides_layers(overlay):
    overlay.show()
    overlay.bridge_for_test.fullscreenChanged.emit(True)
    assert overlay.hidden
    overlay.bridge_for_test.fullscreenChanged.emit(False)
    assert not overlay.hidden


def test_fullscreen_ignored_when_disabled(overlay):
    overlay.settings.hide_on_fullscreen = False
    overlay.bridge_for_test.fullscreenChanged.emit(True)
    assert not overlay.hidden
