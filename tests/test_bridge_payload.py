from plasmacat.bridge.kwin import BridgeService, FakeBridge


def test_setwindows_parses_ids(qapp):
    svc = BridgeService()
    got = []
    svc.windowsChanged.connect(got.append)
    svc.SetWindows('[{"id": "{a}", "x": 1, "y": 2, "w": 300, "h": 200}]')
    assert got == [[{"id": "{a}", "x": 1, "y": 2, "w": 300, "h": 200}]]


def test_setwindows_ignores_garbage(qapp):
    svc = BridgeService()
    got = []
    svc.windowsChanged.connect(got.append)
    svc.SetWindows("{not json")
    svc.SetWindows('{"x": 1}')
    svc.SetWindows('[{"id": "a"}, 5]')   # entries without geometry are dropped
    assert got == [[]]


def test_fullscreen_signal(qapp):
    svc = BridgeService()
    got = []
    svc.fullscreenChanged.connect(got.append)
    svc.SetActiveFullscreen("1")
    svc.SetActiveFullscreen("0")
    assert got == [True, False]


def test_fake_bridge_has_fullscreen_signal(qapp):
    assert hasattr(FakeBridge(), "fullscreenChanged")
