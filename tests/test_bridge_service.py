from plasmacat.bridge.kwin import BridgeService, KWinBridge


def test_activate_emits_signal(qapp):
    svc = BridgeService()
    got = []
    svc.activateRequested.connect(lambda: got.append(True))
    svc.Activate("")
    assert got == [True]


def test_start_reports_running_instance(qapp, monkeypatch):
    b = KWinBridge("unused.js")

    class Bus:
        def registerService(self, name):
            return False

    monkeypatch.setattr("plasmacat.bridge.kwin.QDBusConnection.sessionBus",
                        staticmethod(lambda: Bus()))
    monkeypatch.setattr("PySide6.QtCore.QThread.msleep", staticmethod(lambda ms: None))
    assert b.start() is False
    assert b.error == "running"
