---
name: agent-hands
description: Allows the AI agent to operate the computer keyboard with human-like typing simulation, micro-pauses, realistic typos and self-corrections, hotkeys, and window targeting.
---

# AgentHands: Keyboard Automation & Human-Like Typing

Use this skill when you need to type text, press keyboard shortcuts, interact with desktop applications, or simulate realistic human typing cadence.

## Prerequisites

AgentHands is installed in the environment:
```bash
python -m agent_hands.cli --help
```

## Available CLI Commands

### 1. Human-Like Typing
Simulate human typing with organic cadence, pauses after punctuation, and variable WPM:
```bash
python -m agent_hands.cli type "Text to type goes here." --wpm 65
```

With simulated typos and backspace self-corrections:
```bash
python -m agent_hands.cli type "Text with realistic human errors and fixes." --typos --typo-rate 0.02
```

Targeting a specific window before typing:
```bash
python -m agent_hands.cli type "Typing directly into Notepad." --window "Notepad"
```

### 2. Pressing Keys
```bash
# Press Enter
python -m agent_hands.cli key enter

# Press Tab 3 times
python -m agent_hands.cli key tab -c 3
```

### 3. Executing Shortcuts (Hotkeys)
```bash
# Save file
python -m agent_hands.cli hotkey ctrl+s

# Switch windows
python -m agent_hands.cli hotkey alt+tab

# Open Run dialog
python -m agent_hands.cli hotkey win+r
```

### 4. Fast Paste (Clipboard)
For large codeblocks or multi-line paragraphs:
```bash
python -m agent_hands.cli paste "Large multiline code content" --window "Visual Studio Code"
```

### 5. Window Management
```bash
# List all open windows
python -m agent_hands.cli windows

# Bring specific window to front
python -m agent_hands.cli focus "Chrome"
```

### 6. Starting MCP Server
To allow any MCP-compatible agent to call keyboard tools programmatically:
```bash
python -m agent_hands.cli serve
```
