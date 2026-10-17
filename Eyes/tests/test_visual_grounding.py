"""Unit tests for instruction-conditioned visual grounding subsystem."""

import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from Eyes.visual_grounding import (
    CVGroundingBackend,
    Florence2GroundingBackend,
    GroundingCandidate,
    InstructionGrounder,
    VisualGroundingBackend,
)


def test_candidate_dataclass_and_serialization():
    cand = GroundingCandidate(
        box=[10, 20, 110, 80],
        center=(60, 50),
        confidence=0.885,
        label="search button",
        source="florence2",
    )
    d = cand.to_dict()
    assert d["box"] == [10, 20, 110, 80]
    assert d["center"] == [60, 50]
    assert d["confidence"] == 0.885
    assert d["label"] == "search button"
    assert d["source"] == "florence2"


def test_out_of_bounds_and_collapsed_box_rejection():
    grounder = InstructionGrounder(backends=[])
    fake_backend = MagicMock(spec=VisualGroundingBackend)
    fake_backend.is_available.return_value = True

    # 1. Valid box
    # 2. Collapsed box (width < 4)
    # 3. Oversized box covering entire screen
    # 4. Out-of-bounds box that gets clamped
    fake_backend.ground.return_value = [
        GroundingCandidate(box=[100, 100, 200, 150], center=(150, 125), confidence=0.9, label="valid", source="mock"),
        GroundingCandidate(box=[100, 100, 102, 102], center=(101, 101), confidence=0.9, label="collapsed", source="mock"),
        GroundingCandidate(box=[0, 0, 5000, 5000], center=(2500, 2500), confidence=0.9, label="oversized", source="mock"),
        GroundingCandidate(box=[-50, -50, 150, 150], center=(50, 50), confidence=0.85, label="clamped", source="mock"),
    ]

    grounder.backends = [fake_backend]
    dummy_img = Image.new("RGB", (640, 480))

    candidates = grounder.ground_target(dummy_img, "test target")

    # Should reject collapsed and oversized, but keep valid and clamped
    labels = [c.label for c in candidates]
    assert "valid" in labels
    assert "collapsed" not in labels
    assert "oversized" not in labels
    assert "clamped" in labels

    # Verify clamped box starts at 0, 0
    clamped_cand = next(c for c in candidates if c.label == "clamped")
    assert clamped_cand.box[0] >= 0
    assert clamped_cand.box[1] >= 0


def test_model_unavailable_graceful_fallback():
    backend = Florence2GroundingBackend()
    # torch is not installed or unavailable
    with patch.object(backend, "is_available", return_value=False):
        results = backend.ground(Image.new("RGB", (100, 100)), "search bar")
        assert results == []


def test_cv_grounding_backend_available():
    cv_backend = CVGroundingBackend()
    assert cv_backend.is_available() is True

    # Run on a mock image containing a drawn rectangle
    img = Image.new("RGB", (300, 200), (255, 255, 255))
    candidates = cv_backend.ground(img, "button", offset=(10, 10))
    assert isinstance(candidates, list)


def test_strict_separation_no_mouse_clicks():
    """Grounding engine must only emit coordinate candidates and never invoke mouse clicks."""
    grounder = InstructionGrounder()
    fake_backend = MagicMock(spec=VisualGroundingBackend)
    fake_backend.is_available.return_value = True
    fake_backend.ground.return_value = [
        GroundingCandidate(box=[10, 10, 50, 50], center=(30, 30), confidence=0.95, label="target", source="mock")
    ]
    grounder.backends = [fake_backend]

    with patch("pyautogui.click") as mock_click:
        res = grounder.ground_target(Image.new("RGB", (100, 100)), "button")
        assert len(res) == 1
        # Asserts no mouse click was triggered by the grounding pipeline
        mock_click.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__])
