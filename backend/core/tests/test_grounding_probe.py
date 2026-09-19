import pytest


@pytest.mark.parametrize("point, hypothesis", [
    ((750, 250), "normalized"),
    ((1440, 270), "pixels"),
    ((960, 180), "long_edge_1280"),
])
def test_scores_known_coordinate_spaces(point, hypothesis):
    from tank_backend.benchmarks.grounding_probe import score_point

    scores = score_point(point, (1920, 1080), (1440, 270))
    assert scores[hypothesis] == 0
    assert sum(error == 0 for error in scores.values()) == 1


@pytest.mark.parametrize("arguments, expected", [
    ({"x": "1440", "y": 270}, (1440, 270)),
    ({"bbox": [100, 200, 300, 400]}, (200, 300)),
    ({"bbox": "[100,200,300,400]]"}, None),
    ({"x": float("nan"), "y": 1}, None),
    ({"x": True, "y": 1}, None),
])
def test_probe_preserves_pixel_coordinates_but_rejects_malformed(arguments, expected):
    from tank_backend.benchmarks.grounding_probe import response_point

    assert response_point(arguments) == expected
