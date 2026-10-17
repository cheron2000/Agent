"""Adaptive Perception Fusion: Semantic Scene Graph subsystem.

Evolves the perception layer from flat element lists into a relational, hierarchical
spatial graph that models:
1. Containment (Dialogs/Windows/Groups containing Controls/Buttons/Inputs).
2. Spatial Adjacency (Associating input fields with their adjacent text labels like 'Username:').
3. Action Affordances (Deducing whether an element is CLICKABLE, EDITABLE, SCROLLABLE, or READABLE).
4. Relational Target Queries ('Click Cancel inside Settings Dialog', 'Type in field next to Email').
5. Cross-Source Evidence Calibration (UIA + OCR + Visual Grounding fusion).
"""

from dataclasses import dataclass, field
from enum import Enum
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from .schema import UIElement
except (ImportError, ValueError):
    from Eyes.schema import UIElement


class ActionAffordance(str, Enum):
    CLICKABLE = "clickable"    # Buttons, links, checkboxes, radio buttons, tabs, menu items
    EDITABLE = "editable"      # Edit boxes, text inputs, search fields
    SCROLLABLE = "scrollable"  # Panes, lists, tree views, document containers
    READABLE = "readable"      # Text labels, captions, status bars
    NAVIGABLE = "navigable"    # Window titles, header bars, breadcrumbs


AFFORDANCE_MAP = {
    "Button": [ActionAffordance.CLICKABLE],
    "MenuItem": [ActionAffordance.CLICKABLE],
    "TabItem": [ActionAffordance.CLICKABLE, ActionAffordance.NAVIGABLE],
    "Hyperlink": [ActionAffordance.CLICKABLE],
    "CheckBox": [ActionAffordance.CLICKABLE],
    "RadioButton": [ActionAffordance.CLICKABLE],
    "Edit": [ActionAffordance.EDITABLE, ActionAffordance.CLICKABLE],
    "ComboBox": [ActionAffordance.EDITABLE, ActionAffordance.CLICKABLE],
    "Document": [ActionAffordance.SCROLLABLE, ActionAffordance.EDITABLE],
    "List": [ActionAffordance.SCROLLABLE],
    "Tree": [ActionAffordance.SCROLLABLE],
    "Table": [ActionAffordance.SCROLLABLE],
    "ScrollBar": [ActionAffordance.SCROLLABLE],
    "Text": [ActionAffordance.READABLE],
    "Static": [ActionAffordance.READABLE],
    "Window": [ActionAffordance.NAVIGABLE],
    "Pane": [ActionAffordance.SCROLLABLE],
    "Group": [ActionAffordance.NAVIGABLE],
}


@dataclass
class SceneNode:
    """A relational entity in the desktop semantic scene graph."""
    id: int
    name: str
    role: str
    box: List[int]
    center: Tuple[int, int]
    source: str
    confidence: float
    parent_id: Optional[int] = None
    children_ids: List[int] = field(default_factory=list)
    affordances: List[str] = field(default_factory=list)
    adjacent_label: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "box": list(self.box),
            "center": list(self.center),
            "source": self.source,
            "confidence": round(self.confidence, 3),
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "affordances": list(self.affordances),
            "adjacent_label": self.adjacent_label,
            "attributes": self.attributes,
        }


@dataclass
class SceneGraph:
    """Directed acyclic semantic scene graph representing the desktop GUI."""
    nodes: Dict[int, SceneNode] = field(default_factory=dict)
    root_ids: List[int] = field(default_factory=list)
    active_window: str = ""
    timestamp: float = field(default_factory=time.time)
    observation_id: str = ""

    def get_node(self, node_id: int) -> Optional[SceneNode]:
        return self.nodes.get(node_id)

    def find_by_relation(
        self,
        target_query: str,
        relation: str,
        anchor_query: str,
    ) -> List[SceneNode]:
        """
        Locate nodes satisfying a relational query with respect to an anchor node.
        Supported relations: 'inside', 'contained_in', 'right_of', 'left_of', 'below', 'above'.
        """
        t_clean = target_query.strip().lower()
        a_clean = anchor_query.strip().lower()
        rel_clean = relation.strip().lower()

        def matches_target(node: SceneNode, q: str) -> bool:
            if not q:
                return True
            q_lower = q.strip().lower()
            if q_lower in node.name.lower() or q_lower in node.role.lower():
                return True
            # Semantic role synonyms
            if q_lower in {"field", "input", "textbox", "text field", "box", "edit"}:
                if "editable" in node.affordances or node.role.lower() in ["edit", "combobox"]:
                    return True
            if q_lower in {"button", "btn", "link"}:
                if "clickable" in node.affordances or node.role.lower() in ["button", "hyperlink"]:
                    return True
            tokens = [w for w in q_lower.split() if w not in {"the", "a", "an", "button", "field", "input", "box", "control", "icon"}]
            if tokens and any(t in node.name.lower() for t in tokens):
                return True
            return False

        # Find candidate anchor nodes
        anchors: List[SceneNode] = [
            n for n in self.nodes.values()
            if a_clean in n.name.lower() or a_clean in n.role.lower()
        ]
        if not anchors:
            return []

        results: List[SceneNode] = []

        for anchor in anchors:
            if rel_clean in ["inside", "contained_in", "in"]:
                # Check children or contained boxes
                for child_id in anchor.children_ids:
                    child = self.nodes.get(child_id)
                    if child and matches_target(child, t_clean):
                        results.append(child)

            elif rel_clean in ["right_of", "next_to", "beside"]:
                # Nodes horizontally to the right within vertical alignment
                ax1, ay1, ax2, ay2 = anchor.box
                for candidate in self.nodes.values():
                    if candidate.id == anchor.id:
                        continue
                    cx1, cy1, cx2, cy2 = candidate.box
                    # Horizontally to the right
                    if cx1 >= ax1 and (cx1 - ax2) < 400:
                        # Vertically overlapping or aligned
                        y_overlap = max(0, min(ay2, cy2) - max(ay1, cy1))
                        if y_overlap > 8 or abs((ay1 + ay2)/2 - (cy1 + cy2)/2) < 25:
                            if matches_target(candidate, t_clean):
                                results.append(candidate)

            elif rel_clean in ["below", "under"]:
                ax1, ay1, ax2, ay2 = anchor.box
                for candidate in self.nodes.values():
                    if candidate.id == anchor.id:
                        continue
                    cx1, cy1, cx2, cy2 = candidate.box
                    if cy1 >= ay1 and (cy1 - ay2) < 250:
                        x_overlap = max(0, min(ax2, cx2) - max(ax1, cx1))
                        if x_overlap > 10 or abs((ax1 + ax2)/2 - (cx1 + cy2)/2) < 50:
                            if matches_target(candidate, t_clean):
                                results.append(candidate)

        return results

    def query_target(self, natural_instruction: str) -> Optional[SceneNode]:
        """
        Resolve a natural target query with relational awareness.
        Examples:
        - "Search button inside Settings"
        - "field next to Username"
        - "Cancel button"
        """
        inst = natural_instruction.strip()

        # Check for relational phrasing: "<target> inside <anchor>"
        inside_match = re.search(r"^(.*?)\s+(?:inside|in|within)\s+(.*)$", inst, re.IGNORECASE)
        if inside_match:
            target, anchor = inside_match.group(1).strip(), inside_match.group(2).strip()
            hits = self.find_by_relation(target, "inside", anchor)
            if hits:
                return hits[0]

        # Check for relational phrasing: "<target> (next to|right of) <anchor>"
        adj_match = re.search(r"^(.*?)\s+(?:next to|right of|beside)\s+(.*)$", inst, re.IGNORECASE)
        if adj_match:
            target, anchor = adj_match.group(1).strip(), adj_match.group(2).strip()
            hits = self.find_by_relation(target, "right_of", anchor)
            if hits:
                return hits[0]

        # Direct search with adjacent label matching
        clean_inst = inst.lower()
        candidates: List[Tuple[float, SceneNode]] = []

        for node in self.nodes.values():
            score = 0.0
            name_clean = node.name.lower()
            role_clean = node.role.lower()

            # Exact or substring name match
            if clean_inst == name_clean:
                score += 1.0
            elif clean_inst in name_clean:
                score += 0.8
            elif name_clean in clean_inst and len(name_clean) > 2:
                score += 0.6

            # Adjacent label association (e.g. searching "Username" finds the adjacent Edit field)
            if node.adjacent_label and clean_inst in node.adjacent_label.lower():
                score += 0.85

            if score > 0:
                score *= node.confidence
                candidates.append((score, node))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "active_window": self.active_window,
            "node_count": len(self.nodes),
            "root_ids": self.root_ids,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "timestamp": self.timestamp,
        }


def _box_contains(parent_box: List[int], child_box: List[int], margin: int = 4) -> bool:
    """Determine whether child_box is visually contained within parent_box."""
    return (
        parent_box[0] - margin <= child_box[0]
        and parent_box[1] - margin <= child_box[1]
        and parent_box[2] + margin >= child_box[2]
        and parent_box[3] + margin >= child_box[3]
    )


def build_scene_graph(
    elements: List[UIElement],
    active_window: str = "",
    observation_id: str = "",
) -> SceneGraph:
    """
    Synthesize flat UIElements into a relational Semantic Scene Graph.
    Enriches nodes with containment hierarchies, spatial adjacency, and action affordances.
    """
    nodes: Dict[int, SceneNode] = {}
    container_ids: List[int] = []

    # 1. Initialize nodes and assign action affordances
    for el in elements:
        affordances = list(AFFORDANCE_MAP.get(el.role, []))
        if not affordances:
            affordances = [ActionAffordance.CLICKABLE] if el.role.lower() in ["control", "button"] else [ActionAffordance.READABLE]

        # Calibrate confidence based on source
        if el.source == "uia":
            conf = min(0.98, max(0.85, el.conf))
        elif el.source == "ocr":
            conf = min(0.90, max(0.70, el.conf))
        elif el.source == "visual_grounding":
            conf = min(0.88, max(0.50, el.conf))
        else:
            conf = min(0.65, max(0.35, el.conf))

        node = SceneNode(
            id=el.id,
            name=el.name or "",
            role=el.role or "Control",
            box=list(el.box),
            center=tuple(el.center),
            source=el.source,
            confidence=conf,
            affordances=[a.value if isinstance(a, Enum) else str(a) for a in affordances],
        )
        nodes[el.id] = node

        # Track structural container candidates
        if el.role in ["Window", "Dialog", "Pane", "Group", "Document", "Table", "List"]:
            container_ids.append(el.id)

    # 2. Build Containment Hierarchy (Parent/Children edges)
    # Sort containers by area ascending so smallest containing parent is selected
    def box_area(b: List[int]) -> int:
        return max(0, b[2] - b[0]) * max(0, b[3] - b[1])

    container_ids.sort(key=lambda cid: box_area(nodes[cid].box))

    root_ids: List[int] = []
    for node in nodes.values():
        if node.id in container_ids and node.role in ["Window", "Dialog"]:
            root_ids.append(node.id)

        # Find innermost containing parent
        for cid in container_ids:
            if cid == node.id:
                continue
            parent = nodes[cid]
            if _box_contains(parent.box, node.box):
                # Ensure parent is significantly larger
                if box_area(parent.box) > box_area(node.box) * 1.05:
                    node.parent_id = cid
                    if node.id not in parent.children_ids:
                        parent.children_ids.append(node.id)
                    break

    # If no root windows identified, designate top-level parents as roots
    if not root_ids:
        root_ids = [n.id for n in nodes.values() if n.parent_id is None]

    # 3. Infer Spatial Adjacency (associate labels with inputs)
    # Collect all text labels
    labels = [n for n in nodes.values() if ActionAffordance.READABLE.value in n.affordances and n.name.strip()]
    input_nodes = [n for n in nodes.values() if ActionAffordance.EDITABLE.value in n.affordances]

    for inp in input_nodes:
        ix1, iy1, ix2, iy2 = inp.box
        best_label = None
        min_dist = float("inf")

        for lbl in labels:
            lx1, ly1, lx2, ly2 = lbl.box
            # Check if label is to the left of the input field
            if lx2 <= ix1 and (ix1 - lx2) < 250:
                y_overlap = max(0, min(iy2, ly2) - max(iy1, ly1))
                if y_overlap > 6 or abs((iy1 + iy2)/2 - (ly1 + ly2)/2) < 20:
                    dist = (ix1 - lx2)
                    if dist < min_dist:
                        min_dist = dist
                        best_label = lbl.name.strip()

            # Or label is directly above the input field
            elif ly2 <= iy1 and (iy1 - ly2) < 60:
                x_overlap = max(0, min(ix2, lx2) - max(ix1, lx1))
                if x_overlap > 10:
                    dist = (iy1 - ly2) + 20  # slight bias to prefer left labels
                    if dist < min_dist:
                        min_dist = dist
                        best_label = lbl.name.strip()

        if best_label:
            inp.adjacent_label = best_label

    return SceneGraph(
        nodes=nodes,
        root_ids=root_ids,
        active_window=active_window,
        observation_id=observation_id,
    )
