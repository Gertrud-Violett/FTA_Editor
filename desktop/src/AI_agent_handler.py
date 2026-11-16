"""
AI Agent Handler for FTA Editor
Copyright (c) makkiblog.com - BSD-2 License

This module handles AI agent functionality for the FTA Editor:
- Multi-provider support (OpenAI, Anthropic Claude, Google Gemini)
- Local credential storage (outside repository)
- FTA structure analysis and suggestions
- Change proposal and confirmation workflow
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Callable
from ai_providers import AIProviderFactory


class AICredentialManager:
    """Manages AI API credentials stored locally on the client PC"""
    
    # Store credentials in user's home directory, not in repository
    CREDENTIALS_DIR = Path.home() / ".fta_editor"
    CREDENTIALS_FILE = CREDENTIALS_DIR / "ai_credentials.json"
    
    def __init__(self):
        """Initialize the credential manager"""
        self._ensure_credentials_dir()
    
    def _ensure_credentials_dir(self):
        """Ensure the credentials directory exists"""
        self.CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    
    def save_credentials(self, api_key: str, api_endpoint: str = "https://api.openai.com/v1",
                        model: str = "gpt-4o", provider: str = "OpenAI") -> Tuple[bool, Optional[str]]:
        """
        Save API credentials to local storage.
        
        Args:
            api_key: The API key for the provider
            api_endpoint: The API endpoint URL
            model: The model to use
            provider: The AI provider name (OpenAI, Anthropic Claude, Google Gemini)
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            credentials = {
                "api_key": api_key,
                "api_endpoint": api_endpoint,
                "model": model,
                "provider": provider
            }
            with open(self.CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
                json.dump(credentials, f, indent=2)
            return True, None
        except Exception as e:
            return False, f"Failed to save credentials: {e}"
    
    def load_credentials(self) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
        """
        Load API credentials from local storage.
        
        Returns:
            Tuple of (credentials_dict or None, error_message or None)
        """
        if not self.CREDENTIALS_FILE.exists():
            return None, "Credentials not configured. Please set up AI credentials first."
        
        try:
            with open(self.CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
                credentials = json.load(f)
            return credentials, None
        except Exception as e:
            return None, f"Failed to load credentials: {e}"
    
    def delete_credentials(self) -> Tuple[bool, Optional[str]]:
        """
        Delete stored credentials.
        
        Returns:
            Tuple of (success, error_message)
        """
        try:
            if self.CREDENTIALS_FILE.exists():
                self.CREDENTIALS_FILE.unlink()
            return True, None
        except Exception as e:
            return False, f"Failed to delete credentials: {e}"
    
    def has_credentials(self) -> bool:
        """Check if credentials are configured"""
        return self.CREDENTIALS_FILE.exists()


class FTAStructureAnalyzer:
    """Analyzes FTA structure and converts it to/from AI-readable format"""
    
    @staticmethod
    def fta_to_text(fta_data: Dict[str, Any], mode: str = "FTA", 
                   title: str = "", indent: int = 0) -> str:
        """
        Convert FTA data structure to a human-readable text format for AI analysis.
        
        Args:
            fta_data: The FTA data dictionary
            mode: "FTA" or "ETA"
            title: The analysis title
            indent: Current indentation level
            
        Returns:
            Formatted text representation of the FTA
        """
        lines = []
        
        if indent == 0:
            analysis_type = "Fault Tree Analysis" if mode == "FTA" else "Event Tree Analysis"
            lines.append(f"=== {analysis_type}: {title} ===\n")
        
        prefix = "  " * indent
        name = fta_data.get("name", "Unknown")
        node_type = fta_data.get("type", "Event")
        probability = fta_data.get("probability", 1.0)
        calc_prob = fta_data.get("calculatedProbability", probability)
        logic_gate = fta_data.get("logicGate", "OR")
        notes = fta_data.get("notes", "")
        node_id = fta_data.get("id", "")
        
        # Format node info
        lines.append(f"{prefix}[{node_type}] {name}")
        lines.append(f"{prefix}  - ID: {node_id}")
        lines.append(f"{prefix}  - Base Probability: {probability}")
        lines.append(f"{prefix}  - Calculated Probability: {calc_prob}")
        
        if logic_gate:
            lines.append(f"{prefix}  - Logic Gate: {logic_gate}")
        
        if notes:
            lines.append(f"{prefix}  - Notes: {notes}")
        
        # Process links
        links = fta_data.get("links", [])
        if links:
            links_text = ", ".join([f"{l.get('relation', 'OR')}→{l.get('target_id', '')}" 
                                   for l in links])
            lines.append(f"{prefix}  - Links: {links_text}")
        
        # Process children recursively
        children = fta_data.get("children", [])
        if children:
            lines.append(f"{prefix}  - Children ({len(children)}):")
            for child in children:
                lines.append(FTAStructureAnalyzer.fta_to_text(
                    child, mode, title, indent + 2
                ))
        
        return "\n".join(lines)
    
    @staticmethod
    def get_summary(fta_data: Dict[str, Any], mode: str = "FTA") -> str:
        """
        Get a brief summary of the FTA for quick AI context.
        
        Args:
            fta_data: The FTA data dictionary
            mode: "FTA" or "ETA"
            
        Returns:
            Brief summary text
        """
        def count_nodes(node):
            count = 1
            for child in node.get("children", []):
                count += count_nodes(child)
            return count
        
        def get_leaf_nodes(node, leaves=None):
            if leaves is None:
                leaves = []
            children = node.get("children", [])
            if not children:
                leaves.append(node)
            else:
                for child in children:
                    get_leaf_nodes(child, leaves)
            return leaves
        
        total_nodes = count_nodes(fta_data)
        leaf_nodes = get_leaf_nodes(fta_data)
        root_name = fta_data.get("name", "Root")
        root_prob = fta_data.get("calculatedProbability", 
                                  fta_data.get("probability", 1.0))
        
        analysis_type = "Fault Tree" if mode == "FTA" else "Event Tree"
        
        summary = f"{analysis_type} Summary:\n"
        summary += f"- Root Event: {root_name}\n"
        summary += f"- Top-level Probability: {root_prob}\n"
        summary += f"- Total Nodes: {total_nodes}\n"
        summary += f"- Leaf/Basic Events: {len(leaf_nodes)}\n"
        
        if leaf_nodes:
            summary += f"- Basic Events: {', '.join([n.get('name', 'Unknown') for n in leaf_nodes[:5]])}"
            if len(leaf_nodes) > 5:
                summary += f"... (+{len(leaf_nodes) - 5} more)"
        
        return summary


class AIProposedChange:
    """Represents a proposed change to the FTA structure"""
    
    def __init__(self, change_type: str, target_id: str = None, 
                 description: str = "", data: Dict[str, Any] = None):
        """
        Initialize a proposed change.
        
        Args:
            change_type: Type of change ('add', 'edit', 'delete', 'move')
            target_id: ID of the target node (for edit/delete) or parent (for add)
            description: Human-readable description of the change
            data: Change data (new node data for add/edit)
        """
        self.change_type = change_type
        self.target_id = target_id
        self.description = description
        self.data = data or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "change_type": self.change_type,
            "target_id": self.target_id,
            "description": self.description,
            "data": self.data
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'AIProposedChange':
        """Create from dictionary"""
        return cls(
            change_type=d.get("change_type", ""),
            target_id=d.get("target_id"),
            description=d.get("description", ""),
            data=d.get("data", {})
        )


class AIAgentHandler:
    """Main handler for AI agent functionality"""
    
    # JSON Schema for FTA nodes - explains structure to AI
    FTA_JSON_SCHEMA = """
    FTA Node JSON Structure:
    {
        "id": "unique_identifier",
        "name": "Node Name",
        "type": "Event|Gate|Intermediate" (must be one of these),
        "probability": 0.0-1.0 (float between 0 and 1),
        "calculatedProbability": 0.0-1.0 (float, auto-calculated),
        "logicGate": "AND|OR|NOT" (only if type is Gate, optional for others),
        "notes": "Additional notes about this node",
        "children": [array of child nodes with same structure],
        "links": [array of link objects: {"target_id": "id", "relation": "AND|OR"}]
    }
    
    CRITICAL RULES:
    1. IDs must be unique strings, NO duplicates allowed
    2. Names should be descriptive and unique per level
    3. Probabilities must be floats between 0.0 and 1.0
    4. Type must be exactly "Event", "Gate", or "Intermediate"
    5. logicGate only valid if type is "Gate"
    6. Children array must be empty or contain valid node objects
    7. Links array must contain objects with "target_id" and "relation"
    8. DO NOT remove or modify the root node structure
    9. DO NOT create circular references in children
    10. DO NOT use special characters in IDs, only alphanumeric and underscores
    11. ALWAYS use existing node IDs as parent when adding children
    12. For nested additions, add parent nodes FIRST, then add children to those parents
    """
    
    # System prompt for FTA analysis - now includes JSON schema
    SYSTEM_PROMPT = f"""You are an expert Fault Tree Analysis (FTA) and Event Tree Analysis (ETA) assistant. 
You help users analyze and improve their fault trees by:

1. Understanding the current FTA/ETA structure
2. Identifying potential missing root causes or failure modes
3. Suggesting improvements to probability values based on industry standards
4. Recommending additional nodes, links, or structural changes
5. Validating the logical consistency of the analysis

{FTA_JSON_SCHEMA}

IMPORTANT: When suggesting multiple related changes (e.g., adding a parent and then child nodes):
- Suggest them in sequence: FIRST add parent, THEN add child to parent
- Each SUGGESTION block is for ONE change only
- For nested structures, provide multiple SUGGESTION blocks
- Always reference existing node IDs as parent_id in TARGET field

When suggesting changes, ALWAYS format them exactly like this:
SUGGESTION: [brief title]
DESCRIPTION: [detailed explanation]
ACTION: [add|edit|delete|move]
TARGET: [node_id or parent_id - must be an existing node ID]
DATA: {{"id": "unique_id", "name": "node_name", "type": "Event|Gate|Intermediate", "probability": 0.5, "logicGate": "AND|OR", "notes": ""}}

EXAMPLE of adding nested nodes (correct approach):
SUGGESTION: Add intermediate failure mode
DESCRIPTION: Add "Material Degradation" under root as parent
ACTION: add
TARGET: root
DATA: {{"id": "material_deg", "name": "Material Degradation", "type": "Gate", "probability": 0.1, "logicGate": "OR", "notes": ""}}

SUGGESTION: Add specific material failure
DESCRIPTION: Add "Corrosion" under Material Degradation 
ACTION: add
TARGET: material_deg
DATA: {{"id": "corrosion", "name": "Corrosion", "type": "Event", "probability": 0.05, "logicGate": "", "notes": "Caused by moisture"}}

CRITICAL RULES FOR YOUR RESPONSES:
- Never suggest changes that would break the JSON structure
- Always provide complete node data in DATA field for add/edit actions
- IDs must be unique, descriptive, and contain only alphanumeric and underscores
- Probabilities must be valid numbers between 0.0 and 1.0
- If you don't have enough information for a specific value, use reasonable defaults
- Always explain your reasoning before suggesting structural changes
- Ask for confirmation before suggesting major structural changes
- Do NOT suggest removing the root node
- Do NOT suggest circular references"""

    def __init__(self, on_message_callback: Callable[[str, str], None] = None):
        """
        Initialize the AI agent handler.
        
        Args:
            on_message_callback: Callback function(role, message) for chat updates
        """
        self.credential_manager = AICredentialManager()
        self.analyzer = FTAStructureAnalyzer()
        self.conversation_history: List[Dict[str, str]] = []
        self.current_fta_context: str = ""
        self.pending_changes: List[AIProposedChange] = []
        self.on_message_callback = on_message_callback
        self.provider = None
    
    def _get_provider(self):
        """Get the AI provider based on credentials"""
        if self.provider is not None:
            return self.provider
        
        credentials, error = self.credential_manager.load_credentials()
        if error:
            raise RuntimeError(error)
        
        provider_name = credentials.get("provider", "OpenAI")
        self.provider = AIProviderFactory.get_provider(provider_name)
        
        if self.provider is None:
            raise RuntimeError(f"❌ Unknown provider: {provider_name}")
        
        return self.provider
    
    def _get_client(self):
        """Get or create the OpenAI client"""
        if self._client is not None:
            return self._client
        
        credentials, error = self.credential_manager.load_credentials()
        if error:
            raise RuntimeError(error)
        
        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=credentials["api_key"],
                base_url=credentials.get("api_endpoint", "https://api.openai.com/v1")
            )
            return self._client
        except ImportError:
            raise RuntimeError("OpenAI package not installed. Run: pip install openai")
    
    def is_configured(self) -> bool:
        """Check if AI is properly configured"""
        return self.credential_manager.has_credentials()
    
    def configure(self, api_key: str, api_endpoint: str = "https://api.openai.com/v1",
                  model: str = "gpt-4o", provider: str = "OpenAI") -> Tuple[bool, Optional[str]]:
        """
        Configure AI credentials.
        
        Args:
            api_key: AI provider API key
            api_endpoint: API endpoint URL
            model: Model to use
            provider: AI provider name (OpenAI, Anthropic Claude, Google Gemini)
            
        Returns:
            Tuple of (success, error_message)
        """
        success, error = self.credential_manager.save_credentials(
            api_key, api_endpoint, model, provider
        )
        if success:
            self.provider = None  # Reset provider to reload credentials
        return success, error
    
    def set_fta_context(self, fta_data: Dict[str, Any], mode: str = "FTA", 
                        title: str = "") -> None:
        """
        Set the current FTA context for AI analysis.
        
        Args:
            fta_data: Current FTA data structure
            mode: "FTA" or "ETA"
            title: Analysis title
        """
        self.current_fta_context = self.analyzer.fta_to_text(fta_data, mode, title)
        # Also add a summary at the beginning
        summary = self.analyzer.get_summary(fta_data, mode)
        self.current_fta_context = summary + "\n\n" + self.current_fta_context
    
    def clear_conversation(self) -> None:
        """Clear conversation history"""
        self.conversation_history = []
        self.pending_changes = []
    
    def send_message(self, user_message: str, 
                     include_fta_context: bool = True) -> Tuple[str, List[AIProposedChange]]:
        """
        Send a message to the AI and get a response.
        
        Args:
            user_message: The user's message
            include_fta_context: Whether to include FTA context in the message
            
        Returns:
            Tuple of (AI response text, list of proposed changes)
        """
        try:
            provider = self._get_provider()
            credentials, _ = self.credential_manager.load_credentials()
            
            api_key = credentials.get("api_key")
            endpoint = credentials.get("api_endpoint")
            model = credentials.get("model")
            
            # Build messages array
            messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
            
            # Include FTA context if requested and available
            context_message = ""
            if include_fta_context and self.current_fta_context:
                # Add detailed schema reminder to first message
                schema_reminder = f"""
--- Current FTA Structure ---
{self.current_fta_context}
--- End FTA Structure ---

IMPORTANT REMINDERS FOR YOUR RESPONSE:
{self.FTA_JSON_SCHEMA}

Example of a valid node for DATA field:
{{"id": "heat_exchanger_failure", "name": "Heat Exchanger Failure", "type": "Event", "probability": 0.05, "logicGate": "OR", "notes": "Common failure mode"}}
"""
                context_message = schema_reminder
            
            # Add conversation history
            for msg in self.conversation_history:
                messages.append(msg)
            
            # Add current message with context
            # Always include context if requested - AI needs current tree state for valid suggestions
            full_message = user_message
            if context_message and include_fta_context:
                full_message = context_message + user_message
            
            messages.append({"role": "user", "content": full_message})
            
            # Make API call using provider
            assistant_message, error = provider.send_message(
                api_key, endpoint, model, messages, max_tokens=2000
            )
            
            if error:
                return f"AI Error: {error}", []
            
            # Update conversation history (without context, to keep history clean)
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": assistant_message})
            
            # Parse any proposed changes from the response
            proposed_changes = self._parse_proposed_changes(assistant_message)
            self.pending_changes.extend(proposed_changes)
            
            return assistant_message, proposed_changes
            
        except Exception as e:
            error_msg = f"AI Error: {str(e)}"
            return error_msg, []
    
    def _parse_proposed_changes(self, response: str) -> List[AIProposedChange]:
        """
        Parse proposed changes from AI response with robust validation.
        
        Args:
            response: The AI response text
            
        Returns:
            List of validated proposed changes
        """
        changes = []

        def strip_code_fences(block: str) -> str:
            block = block.strip()
            if block.startswith("```"):
                block = re.sub(r"^```[a-zA-Z]*\s*", "", block)
                block = re.sub(r"```$", "", block)
            return block

        # Accept several lead-in tokens to capture proposals
        block_pattern = r'(?i)(?:SUGGESTION|PROPOSAL|CHANGE)\s*:\s*(.+?)(?=(?:SUGGESTION|PROPOSAL|CHANGE)\s*:|$)'
        suggestions = re.findall(block_pattern, response, re.DOTALL)

        # Fallback: if no explicit labels, slice on ACTION markers so we still surface proposals
        if not suggestions:
            fallback_pattern = r'(?i)(ACTION:\s*(?:add|edit|delete|move).+?)(?=ACTION:|$)'
            suggestions = re.findall(fallback_pattern, response, re.DOTALL)

        for suggestion_block in suggestions:
            try:
                # Extract components with case-insensitive matching
                description_match = re.search(r'DESCRIPTION:\s*(.+?)(?=ACTION:|$)',
                                             suggestion_block, re.DOTALL | re.IGNORECASE)
                action_match = re.search(r'ACTION:\s*(add|edit|delete|move)',
                                          suggestion_block, re.IGNORECASE)
                target_match = re.search(r'TARGET:\s*([^\n\r]+)',
                                          suggestion_block, re.IGNORECASE)
                data_match = re.search(r'DATA:\s*(\{.+?\})',
                                        suggestion_block, re.DOTALL | re.IGNORECASE)

                # Also handle fenced JSON blocks (```json ... ```)
                if not data_match:
                    data_match = re.search(r'DATA:\s*```(?:json)?\s*(\{.+?\})\s*```',
                                            suggestion_block, re.DOTALL | re.IGNORECASE)
                
                if not action_match:
                    continue
                
                # Validate action type
                action_type = action_match.group(1).lower().strip()
                if action_type not in ['add', 'edit', 'delete', 'move']:
                    continue
                
                target_id = target_match.group(1).strip() if target_match else None
                description = description_match.group(1).strip() if description_match else suggestion_block[:100]
                
                # Parse and validate JSON data
                data = {}
                if data_match:
                    try:
                        json_str = strip_code_fences(data_match.group(1))
                        data = json.loads(json_str)
                        
                        # Validate node structure if data provided
                        if data:
                            # For add/edit, validate required fields
                            if action_type in ['add', 'edit']:
                                # Ensure ID is present and valid
                                if 'id' not in data or not isinstance(data['id'], str):
                                    continue
                                if not re.match(r'^[a-zA-Z0-9_]+$', data['id']):
                                    continue
                                
                                # Validate name
                                if 'name' not in data or not isinstance(data['name'], str):
                                    continue
                                
                                # Validate type if present
                                if 'type' in data:
                                    if data['type'] not in ['Event', 'Gate', 'Intermediate']:
                                        continue
                                
                                # Validate probability if present
                                if 'probability' in data:
                                    try:
                                        prob = float(data['probability'])
                                        if prob < 0.0 or prob > 1.0:
                                            continue
                                    except (ValueError, TypeError):
                                        continue
                                
                                # Validate logicGate if present
                                if 'logicGate' in data:
                                    if data['logicGate'] not in ['AND', 'OR', 'NOT']:
                                        continue
                        
                    except (json.JSONDecodeError, ValueError):
                        # If JSON parsing fails but we have other data, continue
                        data = {}
                
                # Create validated change object
                change = AIProposedChange(
                    change_type=action_type,
                    target_id=target_id,
                    description=description,
                    data=data
                )
                changes.append(change)
                
            except Exception as e:
                # Log but don't crash - invalid suggestions are just skipped
                continue
        
        return changes
    
    def _validate_node_data(self, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate node data structure.
        
        Args:
            data: Node data to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Required fields
        if 'id' not in data:
            return False, "Missing required field: 'id'"
        
        if not isinstance(data['id'], str) or not re.match(r'^[a-zA-Z0-9_]+$', data['id']):
            return False, "ID must be alphanumeric with underscores only"
        
        if 'name' not in data:
            return False, "Missing required field: 'name'"
        
        if not isinstance(data['name'], str) or len(data['name']) < 1:
            return False, "Name must be a non-empty string"
        
        # Optional but validated fields
        if 'type' in data:
            if data['type'] not in ['Event', 'Gate', 'Intermediate']:
                return False, f"Type must be 'Event', 'Gate', or 'Intermediate', got '{data['type']}'"
        
        if 'probability' in data:
            try:
                prob = float(data['probability'])
                if prob < 0.0 or prob > 1.0:
                    return False, f"Probability must be between 0.0 and 1.0, got {prob}"
            except (ValueError, TypeError):
                return False, f"Probability must be a number, got {type(data['probability'])}"
        
        if 'logicGate' in data:
            if data['logicGate'] not in ['AND', 'OR', 'NOT']:
                return False, f"logicGate must be 'AND', 'OR', or 'NOT', got '{data['logicGate']}'"
        
        if 'children' in data:
            if not isinstance(data['children'], list):
                return False, "Children must be an array"
        
        if 'links' in data:
            if not isinstance(data['links'], list):
                return False, "Links must be an array"
        
        return True, None
    
    def validate_change(self, change: AIProposedChange) -> Tuple[bool, Optional[str]]:
        """
        Validate a proposed change before applying it.
        
        Args:
            change: The proposed change to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if change.change_type not in ['add', 'edit', 'delete', 'move']:
            return False, f"Invalid change type: {change.change_type}"
        
        if change.change_type in ['add', 'edit']:
            if not change.data:
                return False, f"Change type '{change.change_type}' requires node data"
            
            is_valid, error = self._validate_node_data(change.data)
            if not is_valid:
                return False, f"Invalid node data: {error}"
        
        if change.change_type in ['edit', 'delete', 'move']:
            if not change.target_id:
                return False, f"Change type '{change.change_type}' requires a target node ID"
        
        return True, None
    
    def apply_change_to_fta(self, core: 'FTACore', change: AIProposedChange) -> Tuple[bool, str]:
        """
        Apply a validated AI-proposed change to the FTA using the core module.
        
        Args:
            core: FTACore instance to apply changes to
            change: AIProposedChange object
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if change.change_type == 'add':
                # For add, target_id is the parent node ID
                parent = core.find_node_by_id(change.target_id)
                if not parent:
                    return False, f"Parent node '{change.target_id}' not found"
                
                if not change.data or 'id' not in change.data or 'name' not in change.data:
                    return False, "Add requires node data with 'id' and 'name' fields"
                
                # Check for ID conflicts
                if core.find_node_by_id(change.data['id']):
                    return False, f"Node ID '{change.data['id']}' already exists"
                
                # Create properly structured node
                new_node = {
                    "id": change.data.get('id', ''),
                    "name": change.data.get('name', 'New Node'),
                    "type": change.data.get('type', 'Event'),
                    "probability": float(change.data.get('probability', 0.5)),
                    "calculatedProbability": float(change.data.get('probability', 0.5)),
                    "logicGate": change.data.get('logicGate', ''),
                    "notes": change.data.get('notes', ''),
                    "children": [],
                    "links": []
                }
                
                core.add_node_to_data(change.target_id, new_node)
                return True, f"✓ Added node '{new_node['name']}' to parent"
            
            elif change.change_type == 'edit':
                # For edit, target_id is the node to edit
                node = core.find_node_by_id(change.target_id)
                if not node:
                    return False, f"Node '{change.target_id}' not found"
                
                if not change.data:
                    return False, "Edit requires data fields"
                
                # Safe field updates - avoid modifying ID
                allowed_fields = ['name', 'type', 'probability', 'logicGate', 'notes']
                updated_fields = []
                
                for field in allowed_fields:
                    if field in change.data:
                        try:
                            if field in ['probability']:
                                value = float(change.data[field])
                                if value < 0.0 or value > 1.0:
                                    continue
                            elif field in ['type']:
                                if change.data[field] not in ['Event', 'Gate', 'Intermediate']:
                                    continue
                                value = change.data[field]
                            elif field in ['logicGate']:
                                if change.data[field] and change.data[field] not in ['AND', 'OR', 'NOT']:
                                    continue
                                value = change.data[field]
                            else:
                                value = change.data[field]
                            
                            node[field] = value
                            updated_fields.append(field)
                        except (ValueError, TypeError):
                            continue
                
                if not updated_fields:
                    return False, "No valid fields to update"
                
                return True, f"✓ Updated '{node['name']}': {', '.join(updated_fields)}"
            
            elif change.change_type == 'delete':
                # For delete, target_id is the node to delete
                if change.target_id == 'root':
                    return False, "Cannot delete the root node"
                
                node = core.find_node_by_id(change.target_id)
                if not node:
                    return False, f"Node '{change.target_id}' not found"
                
                node_name = node.get('name', change.target_id)
                core.delete_node_from_data(change.target_id)
                return True, f"✓ Deleted node '{node_name}'"
            
            elif change.change_type == 'move':
                # For move, target_id is node to move, data['parent_id'] is new parent
                if change.target_id == 'root':
                    return False, "Cannot move the root node"
                
                node = core.find_node_by_id(change.target_id)
                if not node:
                    return False, f"Node '{change.target_id}' not found"
                
                if not change.data or 'parent_id' not in change.data:
                    return False, "Move requires 'parent_id' in data"
                
                new_parent_id = change.data['parent_id']
                new_parent = core.find_node_by_id(new_parent_id)
                if not new_parent:
                    return False, f"New parent '{new_parent_id}' not found"
                
                # Check for circular reference
                if self._would_create_circular_reference(core, change.target_id, new_parent_id):
                    return False, "Cannot move: would create circular reference"
                
                # Remove from current parent
                self._remove_node_from_parent(core, change.target_id)
                
                # Add to new parent
                if 'children' not in new_parent:
                    new_parent['children'] = []
                new_parent['children'].append(node)
                
                return True, f"✓ Moved '{node['name']}' to new parent"
            
            else:
                return False, f"Unknown change type: {change.change_type}"
        
        except Exception as e:
            return False, f"Error applying change: {str(e)}"
    
    def _would_create_circular_reference(self, core: 'FTACore', node_id: str, 
                                        potential_parent_id: str) -> bool:
        """Check if moving would create circular reference"""
        if potential_parent_id == node_id:
            return True
        return core._find_node_by_id_recursive(core.fta_data, node_id) and \
               self._is_descendant_of(core, node_id, potential_parent_id)
    
    def _is_descendant_of(self, core: 'FTACore', node_id: str, 
                         potential_ancestor_id: str) -> bool:
        """Check if node_id is a descendant of potential_ancestor_id"""
        ancestor = core.find_node_by_id(potential_ancestor_id)
        if not ancestor:
            return False
        
        for child in ancestor.get('children', []):
            if child.get('id') == node_id:
                return True
            if self._is_descendant_of(core, node_id, child.get('id')):
                return True
        
        return False
    
    def _remove_node_from_parent(self, core: 'FTACore', node_id: str) -> None:
        """Remove a node from its parent's children list"""
        def remove_recursive(current_node):
            current_node['children'] = [
                child for child in current_node.get('children', [])
                if child.get('id') != node_id
            ]
            for child in current_node.get('children', []):
                remove_recursive(child)
        
        remove_recursive(core.fta_data)
    
    def get_quick_analysis(self, fta_data: Dict[str, Any], mode: str = "FTA",
                          title: str = "") -> Tuple[str, List[AIProposedChange]]:
        """
        Get a quick analysis of the current FTA with suggestions.
        
        Args:
            fta_data: Current FTA data structure
            mode: "FTA" or "ETA"
            title: Analysis title
            
        Returns:
            Tuple of (analysis text, proposed changes)
        """
        self.set_fta_context(fta_data, mode, title)
        
        prompt = """Please analyze this FTA/ETA and provide:
1. A brief assessment of the current structure
2. Any potential missing failure modes or root causes
3. Suggestions for improvement

If you have specific suggestions for changes, please format them as structured proposals."""
        
        return self.send_message(prompt, include_fta_context=True)
    
    def suggest_root_causes(self, fta_data: Dict[str, Any], node_id: str = None,
                           mode: str = "FTA", title: str = "") -> Tuple[str, List[AIProposedChange]]:
        """
        Get suggestions for additional root causes.
        
        Args:
            fta_data: Current FTA data structure
            node_id: Specific node to analyze (optional)
            mode: "FTA" or "ETA"
            title: Analysis title
            
        Returns:
            Tuple of (suggestions text, proposed changes)
        """
        self.set_fta_context(fta_data, mode, title)
        
        if node_id:
            prompt = f"Please suggest additional root causes or failure modes that could be added under the node with ID '{node_id}'. Consider industry best practices and common failure patterns."
        else:
            prompt = "Please review this analysis and suggest any additional root causes or failure modes that might be missing. Consider industry best practices and common failure patterns."
        
        return self.send_message(prompt, include_fta_context=True)

    # ===== Full FTA Update Generation =====
    def generate_full_fta_update(self, fta_data: Dict[str, Any], mode: str = "FTA",
                                 title: str = "") -> Tuple[str, Optional[Dict[str, Any]]]:
        """Ask the AI to produce a complete updated FTA JSON based on current data and its suggestions.

        Returns a tuple of (assistant_text, updated_json_or_none).
        """
        self.set_fta_context(fta_data, mode, title)
        instruction = (
            "You are to generate a complete, updated FTA JSON object based on the current analysis and your suggestions. "
            "Strict rules:\n"
            "- Do NOT delete or modify existing nodes except to add reasonable notes.\n"
            "- Only ADD new nodes or links; preserve original structure and IDs.\n"
            "- Maintain valid tree structure: each node has id, name, type, probability, logicGate, notes, children, links.\n"
            "- Ensure IDs are unique and alphanumeric/underscores.\n"
            "- Probabilities must be 0.0–1.0.\n"
            "- Return ONLY a single JSON object (no markdown fences, no commentary)."
        )
        assistant_text, _ = self.send_message(instruction, include_fta_context=True)

        # Try to parse JSON from the assistant_text
        parsed = None
        try:
            cleaned = re.sub(r"^```(?:json)?\s*", "", assistant_text.strip())
            cleaned = re.sub(r"```$", "", cleaned)
            parsed = json.loads(cleaned)
        except Exception:
            parsed = None

        return assistant_text, parsed

    def verify_updated_fta_json(self, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Verify the structure and rules of an updated full FTA JSON.

        Checks:
        - Root node exists and is valid
        - All nodes have required fields with correct types
        - IDs are unique and valid
        - Tree connectivity is consistent (children arrays contain proper nodes)
        - No cycles
        """
        if not isinstance(data, dict):
            return False, "Top-level FTA must be a JSON object"

        # Basic root checks
        required_root_fields = ["id", "name", "type", "probability", "logicGate", "children", "links", "notes"]
        for f in required_root_fields:
            if f not in data:
                return False, f"Missing root field: {f}"

        if data.get("id") != "root":
            return False, "Root ID must be 'root'"

        # Traverse and validate
        seen_ids = set()
        def validate_node(node: Dict[str, Any], path: List[str]) -> Tuple[bool, Optional[str]]:
            nid = node.get("id")
            if not isinstance(nid, str) or not re.match(r"^[a-zA-Z0-9_]+$", nid):
                return False, f"Invalid node ID at {'/'.join(path)}"
            if nid in seen_ids:
                return False, f"Duplicate node ID: {nid}"
            seen_ids.add(nid)

            name = node.get("name")
            if not isinstance(name, str) or not name:
                return False, f"Invalid name for node {nid}"
            ntype = node.get("type")
            if ntype not in ["Event", "Gate", "Intermediate", "Root"]:
                return False, f"Invalid type for node {nid}: {ntype}"
            prob = node.get("probability")
            try:
                prob = float(prob)
            except Exception:
                return False, f"Invalid probability for node {nid}"
            if prob < 0.0 or prob > 1.0:
                return False, f"Probability out of range for node {nid}"
            lg = node.get("logicGate", "")
            if lg not in ["", "AND", "OR", "NOT"]:
                return False, f"Invalid logicGate for node {nid}: {lg}"

            # Children
            children = node.get("children", [])
            if not isinstance(children, list):
                return False, f"Children must be a list for node {nid}"
            for child in children:
                if not isinstance(child, dict):
                    return False, f"Child entries must be objects for node {nid}"
                ok, err = validate_node(child, path + [nid])
                if not ok:
                    return False, err

            # Links
            links = node.get("links", [])
            if not isinstance(links, list):
                return False, f"Links must be a list for node {nid}"
            for l in links:
                if not isinstance(l, dict):
                    return False, f"Link entries must be objects for node {nid}"
                tid = l.get("target_id")
                if tid is not None and (not isinstance(tid, str) or not re.match(r"^[a-zA-Z0-9_]+$", tid)):
                    return False, f"Invalid link target_id in node {nid}"
                rel = l.get("relation", "OR")
                if rel not in ["AND", "OR"]:
                    return False, f"Invalid link relation in node {nid}: {rel}"
            return True, None

        ok, err = validate_node(data, ["root"])
        if not ok:
            return False, err

        return True, None


# Convenience function for testing
def test_connection(api_key: str, api_endpoint: str = "https://api.openai.com/v1",
                   model: str = "gpt-4o", provider: str = "OpenAI") -> Tuple[bool, str]:
    """
    Test the API connection with provided credentials.
    
    Args:
        api_key: API key to test
        api_endpoint: API endpoint
        model: Model to use
        provider: AI provider name
        
    Returns:
        Tuple of (success, message)
    """
    try:
        ai_provider = AIProviderFactory.get_provider(provider)
        if ai_provider is None:
            return False, f"Unknown provider: {provider}"
        
        return ai_provider.test_connection(api_key, api_endpoint, model)
    except Exception as e:
        return False, f"Connection failed: {str(e)}"
