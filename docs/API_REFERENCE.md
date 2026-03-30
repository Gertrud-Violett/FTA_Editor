# API Reference

**Version**: 1.5.0 | **Updated**: December 16, 2025

Complete API documentation for programmatic use of FTA/ETA Editor.

## Overview

This document covers three main modules:
- **FTACore**: Core business logic for FTA/ETA operations
- **AIAgentHandler**: AI assistant integration (new in v1.5)
- **FTAStructureAnalyzer**: FTA data conversion utilities

## FTACore Class

Main class for fault tree and event tree analysis operations.

### Constructor

```python
from src.FTA_Editor_core import FTACore

core = FTACore()
```

Initializes with default root node and metadata.

### Metadata Methods

#### `set_metadata(title=None, date=None, mode=None)`

Set analysis metadata.

**Parameters**:
- `title` (str, optional): Analysis title
- `date` (str, optional): Analysis date
- `mode` (str, optional): "FTA" or "ETA"

**Example**:
```python
core.set_metadata(
    title="Server Reliability Analysis",
    date="2025-10-31",
    mode="FTA"
)
```

#### `get_metadata()`

Get current metadata.

**Returns**: dict with keys `title`, `date`, `mode`

**Example**:
```python
metadata = core.get_metadata()
print(f"Mode: {metadata['mode']}")
```

### Data Management Methods

#### `get_data()`

Get the current tree data structure.

**Returns**: dict - Complete tree structure

**Example**:
```python
tree = core.get_data()
print(f"Root: {tree['name']}")
```

#### `set_data(data)`

Set the tree data structure.

**Parameters**:
- `data` (dict): Complete tree structure

**Example**:
```python
tree_data = {
    "id": "root",
    "name": "System Failure",
    "type": "Root",
    "probability": 0.5,
    "logicGate": "OR",
    "children": [],
    "links": []
}
core.set_data(tree_data)
```

### Node Operations

#### `add_node(parent_id, node_data)`

Add a new node as child of specified parent.

**Parameters**:
- `parent_id` (str): ID of parent node
- `node_data` (dict): Node data (name, type, probability, etc.)

**Returns**: tuple (success: bool, error: str or None)

**Example**:
```python
success, error = core.add_node("root", {
    "name": "Hardware Failure",
    "type": "Event",
    "probability": 0.1,
    "logicGate": "OR"
})
```

#### `update_node(node_id, updates)`

Update an existing node.

**Parameters**:
- `node_id` (str): ID of node to update
- `updates` (dict): Fields to update

**Returns**: tuple (success: bool, error: str or None)

**Example**:
```python
success, error = core.update_node("root_0", {
    "name": "Updated Name",
    "probability": 0.15
})
```

#### `delete_node(node_id)`

Delete a node and all its children.

**Parameters**:
- `node_id` (str): ID of node to delete

**Returns**: tuple (success: bool, error: str or None)

**Example**:
```python
success, error = core.delete_node("root_0_1")
```

#### `find_node_by_id(node_id)`

Find and return a node by its ID.

**Parameters**:
- `node_id` (str): Node ID to find

**Returns**: dict or None - Node data if found

**Example**:
```python
node = core.find_node_by_id("root_0")
if node:
    print(f"Found: {node['name']}")
```

### Probability Calculations

#### `recalculate_probabilities()`

Recalculate all node probabilities based on current mode.

**Note**: Automatically called after loading data. Call manually after modifications.

**Example**:
```python
core.recalculate_probabilities()
```

#### `get_zero_probability_nodes()`

Get list of node IDs with zero probability.

**Returns**: list of str - Node IDs

**Example**:
```python
zero_nodes = core.get_zero_probability_nodes()
print(f"Zero probability nodes: {zero_nodes}")
```

### File I/O Methods

#### `load_from_json(file_path)`

Load tree data from JSON file.

**Parameters**:
- `file_path` (str): Path to JSON file

**Returns**: tuple (success: bool, error: str or None)

**Supports**: Both new format (with metadata) and legacy format

**Example**:
```python
success, error = core.load_from_json("data/analysis.json")
if not success:
    print(f"Error: {error}")
```

#### `save_to_json(file_path=None)`

Save tree data to JSON file with metadata.

**Parameters**:
- `file_path` (str, optional): Path to save. If None, uses last loaded file.

**Returns**: tuple (success: bool, error: str or None)

**Example**:
```python
success, error = core.save_to_json("output.json")
```

#### `export_to_xml(file_path)`

Export tree to XML format.

**Parameters**:
- `file_path` (str): Path for XML file

**Returns**: tuple (success: bool, error: str or None)

**Example**:
```python
success, error = core.export_to_xml("output.xml")
```

#### `export_to_excel(file_path)`

Export tree to hierarchical Excel format.

**Parameters**:
- `file_path` (str): Path for Excel file

**Returns**: tuple (success: bool, error: str or None)

**Features**: Hierarchical columns, color coding, auto-widths

**Example**:
```python
success, error = core.export_to_excel("output.xlsx")
```

## Complete Usage Example

```python
from src.FTA_Editor_core import FTACore

# Initialize
core = FTACore()

# Set metadata
core.set_metadata(
    title="Nuclear Plant Safety Analysis",
    date="2025-10-31",
    mode="ETA"  # Event Tree Analysis
)

# Build tree structure
tree = {
    "id": "root",
    "name": "Loss of Coolant",
    "type": "Root",
    "probability": 0.001,  # Initiating event probability
    "logicGate": "OR",
    "children": [
        {
            "id": "branch1",
            "name": "ECCS Activates",
            "type": "Event",
            "probability": 0.99,
            "logicGate": "OR",
            "children": [
                {
                    "id": "outcome1",
                    "name": "Core Cooled",
                    "type": "Event",
                    "probability": 0.98,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                },
                {
                    "id": "outcome2",
                    "name": "Partial Cooling",
                    "type": "Event",
                    "probability": 0.02,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        },
        {
            "id": "branch2",
            "name": "ECCS Fails",
            "type": "Event",
            "probability": 0.01,
            "logicGate": "OR",
            "children": [
                {
                    "id": "outcome3",
                    "name": "Core Meltdown",
                    "type": "Event",
                    "probability": 1.0,
                    "logicGate": "OR",
                    "children": [],
                    "links": []
                }
            ],
            "links": []
        }
    ],
    "links": []
}

core.set_data(tree)

# Calculate probabilities
core.recalculate_probabilities()

# Access results
root = core.get_data()
print(f"Root calculated probability: {root['calculatedProbability']}")

# Access specific outcome
outcome1 = core.find_node_by_id("outcome1")
print(f"Core Cooled probability: {outcome1['calculatedProbability']}")
# In ETA mode: 0.001 × 0.99 × 0.98 = 0.00097

# Export results
core.save_to_json("analysis.json")
core.export_to_excel("analysis.xlsx")
core.export_to_xml("analysis.xml")

# Check for zero probability nodes
zero_nodes = core.get_zero_probability_nodes()
if zero_nodes:
    print(f"Warning: Zero probability nodes: {zero_nodes}")
```

## Data Structure Reference

### Node Structure

```python
{
    "id": "unique_id",              # Unique identifier
    "name": "Node Name",            # Display name
    "type": "Event",                # Node type
    "probability": 0.5,             # Base probability (0.0-1.0)
    "calculatedProbability": 0.3,   # Calculated (read-only)
    "logicGate": "OR",              # "AND" or "OR"
    "notes": "Description",         # Optional notes
    "children": [],                 # List of child nodes
    "links": [                      # Links to other nodes
        {
            "target_id": "other_node",
            "relation": "AND"       # "AND" or "OR"
        }
    ]
}
```

### Metadata Structure

```python
{
    "title": "Analysis Title",
    "date": "2025-10-31",
    "mode": "ETA"  # "FTA" or "ETA"
}
```

### JSON File Format

```python
{
    "title": "Analysis Title",
    "date": "2025-10-31",
    "mode": "ETA",
    "tree": {
        # Node structure as above
    }
}
```

## Error Handling

All methods return tuples `(success, error)`:

```python
success, error = core.save_to_json("output.json")
if not success:
    print(f"Error occurred: {error}")
else:
    print("Success!")
```

## Helper Functions

### `sanitize_name(s)`

Remove extra whitespace from strings.

**Parameters**:
- `s` (str): String to sanitize

**Returns**: str - Sanitized string

**Example**:
```python
from src.FTA_Editor_core import sanitize_name

clean = sanitize_name("  Spaced   Text  ")
# Returns: "Spaced Text"
```

## Constants

None - all configuration is data-driven.

## Thread Safety

FTACore is **not** thread-safe. Use separate instances for concurrent operations.

## Performance Notes

- Tree traversal is recursive - very deep trees may hit recursion limits
- Probability recalculation is memoized - efficient for large trees
- Circular reference detection prevents infinite loops

---

## AIAgentHandler Class

New in v1.5.0. Handles AI assistant functionality.

### Constructor

```python
from src.AI_agent_handler import AIAgentHandler

handler = AIAgentHandler()
```

### Methods

#### `is_configured()`

Check if AI credentials are set up.

**Returns**: bool

```python
if handler.is_configured():
    print("AI is ready")
```

#### `configure(api_key, api_endpoint, model)`

Configure AI credentials.

**Parameters**:
- `api_key` (str): OpenAI API key
- `api_endpoint` (str): API endpoint URL (default: "https://api.openai.com/v1")
- `model` (str): Model name (default: "gpt-4o")

**Returns**: tuple (success, error_message)

```python
success, error = handler.configure(
    api_key="sk-...",
    api_endpoint="https://api.openai.com/v1",
    model="gpt-4o"
)
```

#### `set_fta_context(fta_data, mode, title)`

Set the FTA context for AI analysis.

**Parameters**:
- `fta_data` (dict): Current FTA data structure
- `mode` (str): "FTA" or "ETA"
- `title` (str): Analysis title

```python
handler.set_fta_context(
    core.get_data(),
    core.mode,
    core.title
)
```

#### `send_message(user_message, include_fta_context=True)`

Send a message to the AI and get a response.

**Parameters**:
- `user_message` (str): User's message
- `include_fta_context` (bool): Include FTA context in first message

**Returns**: tuple (response_text, list of AIProposedChange)

```python
response, changes = handler.send_message(
    "What root causes might be missing?"
)
print(response)
for change in changes:
    print(f"Proposed: {change.description}")
```

#### `get_quick_analysis(fta_data, mode, title)`

Get a quick AI analysis of the current FTA.

**Returns**: tuple (analysis_text, proposed_changes)

```python
analysis, changes = handler.get_quick_analysis(
    core.get_data(), "FTA", "My Analysis"
)
```

#### `clear_conversation()`

Reset conversation history.

```python
handler.clear_conversation()
```

---

## AICredentialManager Class

Manages API credentials storage.

### Credential Location

Credentials are stored at:
- Windows: `C:\Users\<username>\.fta_editor\ai_credentials.json`
- macOS/Linux: `~/.fta_editor/ai_credentials.json`

### Methods

#### `save_credentials(api_key, api_endpoint, model)`

Save credentials to local storage.

**Returns**: tuple (success, error_message)

#### `load_credentials()`

Load credentials from local storage.

**Returns**: tuple (credentials_dict or None, error_message or None)

#### `delete_credentials()`

Delete stored credentials.

**Returns**: tuple (success, error_message)

#### `has_credentials()`

Check if credentials file exists.

**Returns**: bool

---

## FTAStructureAnalyzer Class

Utilities for converting FTA data to text format for AI.

### Static Methods

#### `fta_to_text(fta_data, mode, title, indent=0)`

Convert FTA data to human-readable text.

**Parameters**:
- `fta_data` (dict): FTA data structure
- `mode` (str): "FTA" or "ETA"
- `title` (str): Analysis title
- `indent` (int): Current indentation level

**Returns**: str - Formatted text representation

```python
from src.AI_agent_handler import FTAStructureAnalyzer

text = FTAStructureAnalyzer.fta_to_text(
    core.get_data(), "FTA", "My Analysis"
)
print(text)
```

#### `get_summary(fta_data, mode)`

Get a brief summary of the FTA.

**Returns**: str - Summary text

---

For examples, see `tests/` directory and `data/examples/`.
