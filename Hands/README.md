# 🖐️ AgentHands: Universal Keyboard Hands for Any AI Agent

**AgentHands** equips any AI Agent (Claude, ChatGPT, Cursor, Antigravity, Open WebUI, Goose, Cline, Roo Code, etc.) with real physical keyboard hands, complete with **hyper-realistic human-like typing simulation**.

---

## 🌟 Key Features

- **⚡ Universal AI Compatibility (MCP 2.0)**: Built on the Model Context Protocol standard. Connect to Claude Desktop, Claude Code, Cursor, Antigravity IDE, Roo Code, or any agent framework in seconds.
- **🧑 Realistic Human-Like Typing Simulation**:
  - **Natural Inter-Key Intervals (IKI)**: Calibrated Gaussian/log-normal keystroke distributions (variable WPM, not robotic fixed delays).
  - **Authentic Micro-Pauses**: Longer pauses after periods, exclamation/question marks, commas, and clause breaks.
  - **Word & Sentence Boundary Dwells**: Organic spacebar and newline rhythm.
  - **Cognitive Pauses**: Simulates occasional human hesitation when formulating thoughts mid-sentence.
- **🔄 Simulated Human Typos & Auto-Correction**:
  - Uses a physical QWERTY adjacency matrix to occasionally strike neighboring keys.
  - Simulates the cognitive delay of "noticing" the error, pressing `Backspace`, and typing the intended key.
- **🎯 Smart Window Targeting**: Focuses and brings specific applications (e.g. Notepad, VS Code, Browser, Terminal) to the foreground before typing.
- **⌨️ Complete Keystroke & Hotkey Suite**:
  - Individual keys (`enter`, `tab`, `esc`, `backspace`, arrow keys, function keys).
  - Modifier hotkeys (`ctrl+c`, `alt+tab`, `ctrl+shift+p`, `win+r`) with realistic staggered key-down/up sequences.
  - Fast clipboard paste (`fast_paste`) for instant delivery of huge codeblocks.
- **🛡️ Emergency Fail-Safe**: Moving mouse to any screen corner immediately aborts typing.

---

## 🚀 Quick Start

### 1. Installation

```bash
cd "f:\Shreyash DOC\shreyash\Hands"
pip install -e .
```

### 2. Command Line Usage

```bash
# Type text with natural human cadence
agent-hands type "Hello! I am an AI agent typing with human hands." --wpm 65

# Type into a specific target application (e.g. Notepad) with realistic typos & corrections
agent-hands type "This feels completely authentic and human." --window "Notepad" --typos

# Execute shortcuts
agent-hands hotkey ctrl+s
agent-hands key enter

# Click on screen or in application window
agent-hands click --x 500 --y 300 --button left
agent-hands click --double --window "Google Chrome"

# Scroll mouse wheel (smooth or instant)
agent-hands scroll -5                   # Scroll DOWN 5 units
agent-hands scroll 5 --window "Chrome"  # Scroll UP 5 units in Chrome

# List open windows on your desktop
agent-hands windows

# Launch the MCP Server
agent-hands serve
```

---

## 🤖 Connecting to AI Agents (MCP Server Configuration)

Add AgentHands to your agent's MCP configuration (`claude_desktop_config.json`, Cursor MCP settings, or Antigravity config):

```json
{
  "mcpServers": {
    "agent-hands": {
      "command": "python",
      "args": ["-m", "agent_hands.server"]
    }
  }
}
```

### Available MCP Tools for the Agent

| Tool | Description |
|---|---|
| `hands_type_text` | Type text with human-like cadence, variable WPM, micro-pauses, and optional typo corrections |
| `hands_press_key` | Press single key (e.g., `enter`, `tab`, `esc`, `backspace`, `space`, `down`) |
| `hands_hotkey` | Trigger key combination shortcuts (e.g., `ctrl+c`, `alt+tab`, `win+r`) |
| `hands_paste_text` | Instant clipboard paste (Ctrl+V) for long multi-line code or large blocks |
| `hands_click` | Click anywhere on screen or in target window (left, right, middle, double click) |
| `hands_scroll` | Scroll mouse wheel up or down (smooth or instant, vertical or horizontal) |
| `hands_move_mouse` | Move mouse cursor smoothly to target coordinates |
| `hands_list_windows` | List all open desktop application windows |
| `hands_focus_window` | Focus and activate a target window |
| `hands_get_status` | Inspect current active window, resolution, and status |


---

## ⚙️ Typing Profiles

- **`natural`** (Default): ~65 WPM, standard human cadence, punctuation pauses, cognitive hesitations.
- **`fast`**: ~105 WPM, rapid typist, short pauses.
- **`careful`**: ~38 WPM, deliberate typing, longer sentence contemplation pauses.
- **`coder`**: ~72 WPM, tuned for code syntax, brackets, indentation, and symbols.
