from plasmacat.world import props


def test_furniture_surfaces_match_the_art_at_scale_3():
    # values measured against the prop art at prop scale 3 (P25/P46)
    assert props.furniture_surfaces("cat_tree", 500, 1000, 3) == [
        (446, 542, 892, "Katzenbaum"), (476, 566, 808, "Katzenbaum")]
    assert props.furniture_surfaces("scratch_post", 500, 1000, 3) == [
        (470, 527, 808, "Kratzbaum")]
    assert props.furniture_surfaces("wheel_stand", 500, 1000, 3) == [
        (440, 560, 964, "Laufrad")]


def test_furniture_surfaces_scale_with_the_props():
    (x0, x1, y, _), = props.furniture_surfaces("box", 500, 1000, 6)
    assert (x0, x1, y) == (390, 610, 940)
