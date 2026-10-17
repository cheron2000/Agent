"""Set-of-Marks visual overlay annotation, grid generation, and spatial text layout."""

from typing import Dict, List, Tuple
from PIL import Image, ImageDraw, ImageFont

try:
    from .coords import box_area
    from .schema import UIElement
except (ImportError, ValueError):
    from Eyes.coords import box_area
    from Eyes.schema import UIElement



def annotate_elements(
    image: Image.Image,
    elements: List[UIElement],
    outline_color: Tuple[int, int, int] = (235, 30, 30),
    badge_color: Tuple[int, int, int] = (235, 30, 30),
    text_color: Tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Draw numbered Set-of-Marks badges onto a copy of the screen image.
    
    Draws larger bounding boxes first, so smaller badges remain clearly visible on top.
    """
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)

    # Sort largest area to smallest
    sorted_elements = sorted(elements, key=lambda el: -box_area(el.box))

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for el in sorted_elements:
        x1, y1, x2, y2 = el.box
        # Draw bounding rectangle
        draw.rectangle([x1, y1, x2, y2], outline=outline_color, width=2)

        # Number badge dimensions
        id_str = str(el.id)
        badge_w = max(20, len(id_str) * 9 + 8)
        badge_h = 16

        badge_x1 = x1
        badge_y1 = max(0, y1 - badge_h) if y1 >= badge_h else y1
        badge_x2 = badge_x1 + badge_w
        badge_y2 = badge_y1 + badge_h

        # Badge background
        draw.rectangle([badge_x1, badge_y1, badge_x2, badge_y2], fill=badge_color)
        # Badge label
        draw.text((badge_x1 + 3, badge_y1 + 1), id_str, fill=text_color, font=font)

    return annotated


def draw_grid_map(
    image: Image.Image,
    columns: int = 12,
    rows: int = 8,
    grid_color: Tuple[int, int, int, int] = (255, 255, 255, 120),
) -> Image.Image:
    """Draw semi-transparent coordinate grid with alphanumeric labels (A1, B2, ...)."""
    grid_img = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", grid_img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    w, h = grid_img.size
    col_w = w / columns
    row_h = h / rows

    col_letters = [chr(65 + i) if i < 26 else f"A{chr(65 + i - 26)}" for i in range(columns)]

    for c in range(columns + 1):
        x = int(c * col_w)
        draw.line([(x, 0), (x, h)], fill=grid_color, width=1)

    for r in range(rows + 1):
        y = int(r * row_h)
        draw.line([(0, y), (w, y)], fill=grid_color, width=1)

    for c in range(columns):
        for r in range(rows):
            label = f"{col_letters[c]}{r + 1}"
            lx = int(c * col_w + 6)
            ly = int(r * row_h + 4)
            draw.text((lx, ly), label, fill=(255, 255, 255, 200))

    combined = Image.alpha_composite(grid_img, overlay).convert("RGB")
    return combined


def format_spatial_layout_text(elements: List[UIElement], screen_size: Tuple[int, int]) -> str:
    """Format elements grouped by desktop regions for text-based consumption."""
    _, screen_h = screen_size
    header_threshold = screen_h * 0.15
    footer_threshold = screen_h * 0.88

    sections: Dict[str, List[UIElement]] = {
        "Title & Top Navigation": [],
        "Main Application Area": [],
        "Bottom / Taskbar Area": [],
    }

    for el in elements:
        _, y1, _, y2 = el.box
        mid_y = (y1 + y2) / 2
        if mid_y < header_threshold:
            sections["Title & Top Navigation"].append(el)
        elif mid_y > footer_threshold:
            sections["Bottom / Taskbar Area"].append(el)
        else:
            sections["Main Application Area"].append(el)

    lines: List[str] = []
    for section_name, items in sections.items():
        if not items:
            continue
        lines.append(f"### {section_name}")
        for el in items:
            name_str = f"\"{el.name}\"" if el.name else "<unnamed>"
            lines.append(f"- [ID {el.id}] {el.role}: {name_str} at ({el.center[0]}, {el.center[1]})")
        lines.append("")

    return "\n".join(lines).strip()
