"""Comprehensive tests for Adaptive Perception Fusion and Semantic Scene Graph."""

import pytest
from Eyes.schema import UIElement
from Eyes.scene_graph import (
    ActionAffordance,
    SceneGraph,
    SceneNode,
    build_scene_graph,
)


def test_action_affordances_assignment():
    elements = [
        UIElement(id=1, role="Button", name="Save", box=[10, 10, 60, 40]),
        UIElement(id=2, role="Edit", name="", box=[70, 10, 200, 40]),
        UIElement(id=3, role="Pane", name="SidePanel", box=[0, 0, 100, 800]),
        UIElement(id=4, role="Text", name="Profile Details", box=[10, 50, 150, 70]),
    ]
    graph = build_scene_graph(elements)

    node_btn = graph.get_node(1)
    assert ActionAffordance.CLICKABLE.value in node_btn.affordances

    node_edit = graph.get_node(2)
    assert ActionAffordance.EDITABLE.value in node_edit.affordances

    node_pane = graph.get_node(3)
    assert ActionAffordance.SCROLLABLE.value in node_pane.affordances

    node_text = graph.get_node(4)
    assert ActionAffordance.READABLE.value in node_text.affordances


def test_containment_hierarchy_detection():
    """Verify dialog correctly adopts child buttons and controls."""
    elements = [
        # Large Dialog container: [100, 100, 600, 500]
        UIElement(id=1, role="Dialog", name="Settings Window", box=[100, 100, 600, 500]),
        # Button inside dialog: [150, 400, 250, 440]
        UIElement(id=2, role="Button", name="OK", box=[150, 400, 250, 440]),
        # Button inside dialog: [280, 400, 380, 440]
        UIElement(id=3, role="Button", name="Cancel", box=[280, 400, 380, 440]),
        # Button outside dialog: [700, 50, 800, 90]
        UIElement(id=4, role="Button", name="External Close", box=[700, 50, 800, 90]),
    ]
    graph = build_scene_graph(elements)

    dialog = graph.get_node(1)
    ok_btn = graph.get_node(2)
    cancel_btn = graph.get_node(3)
    ext_btn = graph.get_node(4)

    assert ok_btn.parent_id == 1
    assert cancel_btn.parent_id == 1
    assert 2 in dialog.children_ids
    assert 3 in dialog.children_ids
    assert ext_btn.parent_id != 1
    assert 4 not in dialog.children_ids


def test_spatial_adjacency_associates_label_with_input():
    """Verify input fields automatically discover adjacent text labels."""
    elements = [
        # Label 'Username:' at [50, 100, 140, 125]
        UIElement(id=1, role="Text", name="Username:", box=[50, 100, 140, 125], source="ocr"),
        # Edit field immediately to the right at [150, 95, 350, 130]
        UIElement(id=2, role="Edit", name="", box=[150, 95, 350, 130], source="uia"),
        # Unrelated text
        UIElement(id=3, role="Text", name="Footer 2026", box=[50, 900, 200, 920]),
    ]
    graph = build_scene_graph(elements)

    input_node = graph.get_node(2)
    assert input_node.adjacent_label == "Username:"


def test_relational_target_queries():
    """Verify natural queries with 'inside' and 'next to' resolve accurately."""
    elements = [
        UIElement(id=1, role="Dialog", name="Preferences Dialog", box=[200, 200, 800, 700]),
        UIElement(id=2, role="Button", name="Apply", box=[250, 600, 350, 640]),
        UIElement(id=3, role="Text", name="Server Port:", box=[250, 300, 350, 325]),
        UIElement(id=4, role="Edit", name="", box=[360, 295, 500, 330]),
    ]
    graph = build_scene_graph(elements)

    # Query 1: Inside relation
    target1 = graph.query_target("Apply button inside Preferences Dialog")
    assert target1 is not None
    assert target1.id == 2

    # Query 2: Next to / adjacent label relation
    target2 = graph.query_target("field next to Server Port")
    assert target2 is not None
    assert target2.id == 4

    # Query 3: Search by adjacent label name directly
    target3 = graph.query_target("Server Port")
    assert target3 is not None
    assert target3.id == 4  # Should resolve to the Edit field linked to that label!


def test_calibrated_confidence_scoring():
    elements = [
        UIElement(id=1, role="Button", name="UIA Btn", box=[0, 0, 10, 10], source="uia", conf=1.0),
        UIElement(id=2, role="Text", name="OCR Text", box=[20, 20, 50, 30], source="ocr", conf=0.85),
        UIElement(id=3, role="Control", name="", box=[60, 60, 80, 80], source="cv", conf=0.5),
    ]
    graph = build_scene_graph(elements)

    assert graph.get_node(1).confidence >= 0.95
    assert 0.70 <= graph.get_node(2).confidence <= 0.90
    assert graph.get_node(3).confidence <= 0.65
