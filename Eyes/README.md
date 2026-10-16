# 👁️ EYES — The Vision & Interaction Cortex for ANY AI

**EYES** gives ANY AI agent (Claude, GPT-4o, Gemini, Ollama, LangChain, Cursor, Windsurf, Antigravity) the ability to **see, read, understand, and interact with the desktop environment**.

Built with native Model Context Protocol (MCP) support, FastAPI REST server, and an intelligent **Prompt Enhancer** engine.

---

## 🌟 Key Capabilities

1. **Screen Perception (`capture`)**:
   - High-DPI aware screen capture with direct Windows GDI fallback for background execution.
   - Saves screenshots and produces base64 thumbnails for vision LLMs.

2. **Text Reading (`read_text` / OCR)**:
   - Full screen or regional OCR via Tesseract.
   - Word-level bounding boxes, spatial coordinates, and confidence metrics.

3. **Element Grounding (`find_on_screen`)**:
   - Locates buttons, labels, and text with exact pixel `(x, y)` centers.
   - Supports fuzzy matching and phrase detection.

4. **Multi-Modal Vision (`describe`)**:
   - Visual scene understanding supporting Ollama (LLaVA), OpenAI GPT-4o, Anthropic Claude, or local OCR structural summary.

5. **Desktop Interaction (`click`, `type_text`, `press_key`, `scroll`)**:
   - Mouse clicks, double clicks, right clicks.
   - Keyboard typing and hotkeys (e.g. `ctrl+c`, `alt+tab`).
   - Smooth mouse wheel scrolling.

6. **Prompt Enhancer (`prompt_enhancer.py`)**:
   - Transforms vague user prompts into precise, vision-grounded execution plans following Anthropic's state-of-the-art meta-prompting standards.

---

## 🚀 How Any AI Uses EYES

### Option 1: As an MCP Server (Claude Desktop, Cursor, Continue, Windsurf)

Add this to your MCP client config (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "eyes": {
      "command": "python",
      "args": ["F:\\Shreyash DOC\\shreyash\\Eyes\\eyes_mcp.py"]
    }
  }
}
```

Now Claude Desktop can take screenshots, click buttons, and read screen text natively!

---

### Option 2: REST API Server (FastAPI)

Start the server:
```bash
python eyes_server.py
```
- API runs at: `http://localhost:8421`
- Interactive Swagger UI: `http://localhost:8421/docs`

Example cURL:
```bash
# Capture screen
curl -X POST http://localhost:8421/api/capture -H "Content-Type: application/json" -d '{"save": true}'

# Find element
curl -X POST http://localhost:8421/api/find -H "Content-Type: application/json" -d '{"target": "Search"}'

# Click element
curl -X POST http://localhost:8421/api/click -H "Content-Type: application/json" -d '{"target": "Submit"}'
```

---

### Option 3: Python SDK & Function Calling

Import directly into your agent:
```python
import eyes
from prompt_enhancer import PromptEnhancer

# 1. Enhance task prompt
enhancer = PromptEnhancer()
plan = enhancer.enhance_task_prompt("Click the Save button in Word")

# 2. Find and click
coords = eyes.find_on_screen("Save")
if coords["found"]:
    eyes.click(coords["x"], coords["y"])
```

Tool schemas for OpenAI and Anthropic are provided in [`tool_schemas.json`](./tool_schemas.json).

---

### Option 4: Standalone CLI

```bash
# Get screen resolution & mouse cursor position
python eyes.py info

# Take screenshot
python eyes.py capture

# Read screen text
python eyes.py ocr

# Find coordinates of a button
python eyes.py find "Search"

# Click a button
python eyes.py click --target "Search"

# Enhance a task prompt
python eyes.py enhance-prompt "Find the login button and sign in"
```

---

## 📁 Repository Structure

- [`eyes.py`](./eyes.py) — Core vision engine with GDI capture, OCR, and mouse/keyboard control.
- [`prompt_enhancer.py`](./prompt_enhancer.py) — The Prompt Enhancer creating structured vision prompts.
- [`eyes_mcp.py`](./eyes_mcp.py) — Standard Model Context Protocol (MCP) server.
- [`eyes_server.py`](./eyes_server.py) — FastAPI REST server on port 8421.
- [`tool_schemas.json`](./tool_schemas.json) — Standard JSON schemas for OpenAI and Anthropic tool calling.
- [`PROMPTS.md`](./PROMPTS.md) — Comprehensive guide to master system prompts and prompt enhancement.
- `screenshots/` — Captured screenshot images.
