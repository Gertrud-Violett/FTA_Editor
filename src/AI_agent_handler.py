"""
AI Agent Handler for FTA Editor
Copyright (c) makkiblog.com - BSD-2 License

This module handles AI agent functionality for the FTA Editor:
- GitHub Copilot / OpenAI API authentication
- Local credential storage (outside repository)
- FTA structure analysis and suggestions
- Change proposal and confirmation workflow
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Callable


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
                        model: str = "gpt-4o") -> Tuple[bool, Optional[str]]:
        """
        Save API credentials to local storage.
        
        Args:
            api_key: The API key for OpenAI/GitHub Copilot
            api_endpoint: The API endpoint URL
            model: The model to use (default: gpt-4o)
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            credentials = {
                "api_key": api_key,
                "api_endpoint": api_endpoint,
                "model": model
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
    
    # System prompt for FTA analysis
    SYSTEM_PROMPT = """You are an expert Fault Tree Analysis (FTA) and Event Tree Analysis (ETA) assistant. 
You help users analyze and improve their fault trees by:

1. Understanding the current FTA/ETA structure
2. Identifying potential missing root causes or failure modes
3. Suggesting improvements to probability values based on industry standards
4. Recommending additional nodes, links, or structural changes
5. Validating the logical consistency of the analysis

When suggesting changes, format them clearly as:
- SUGGESTION: [brief title]
- DESCRIPTION: [detailed explanation]
- ACTION: [add/edit/delete] 
- TARGET: [node name or ID if editing/deleting, parent name if adding]
- DATA: [JSON-formatted node data if applicable]

Always explain your reasoning and ask for confirmation before suggesting structural changes.
Be concise but thorough in your analysis."""

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
        self._client = None
    
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
                  model: str = "gpt-4o") -> Tuple[bool, Optional[str]]:
        """
        Configure AI credentials.
        
        Args:
            api_key: OpenAI/GitHub Copilot API key
            api_endpoint: API endpoint URL
            model: Model to use
            
        Returns:
            Tuple of (success, error_message)
        """
        success, error = self.credential_manager.save_credentials(
            api_key, api_endpoint, model
        )
        if success:
            self._client = None  # Reset client to reload credentials
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
            client = self._get_client()
            credentials, _ = self.credential_manager.load_credentials()
            model = credentials.get("model", "gpt-4o")
            
            # Build messages array
            messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
            
            # Include FTA context if requested and available
            context_message = ""
            if include_fta_context and self.current_fta_context:
                context_message = f"\n\n--- Current FTA Structure ---\n{self.current_fta_context}\n--- End FTA Structure ---\n\n"
            
            # Add conversation history
            for msg in self.conversation_history:
                messages.append(msg)
            
            # Add current message with context
            full_message = user_message
            if context_message and not self.conversation_history:
                # Only include context in first message
                full_message = context_message + user_message
            
            messages.append({"role": "user", "content": full_message})
            
            # Make API call
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=2000,
                temperature=0.7
            )
            
            assistant_message = response.choices[0].message.content
            
            # Update conversation history
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
        Parse proposed changes from AI response.
        
        Args:
            response: The AI response text
            
        Returns:
            List of proposed changes found in the response
        """
        changes = []
        
        # Look for structured change suggestions
        # Pattern: SUGGESTION: ... ACTION: add/edit/delete ... TARGET: ... DATA: {...}
        suggestion_pattern = r'SUGGESTION:\s*(.+?)(?=SUGGESTION:|$)'
        suggestions = re.findall(suggestion_pattern, response, re.DOTALL | re.IGNORECASE)
        
        for suggestion_block in suggestions:
            try:
                # Extract components
                description_match = re.search(r'DESCRIPTION:\s*(.+?)(?=ACTION:|$)', 
                                             suggestion_block, re.DOTALL | re.IGNORECASE)
                action_match = re.search(r'ACTION:\s*(add|edit|delete|move)', 
                                        suggestion_block, re.IGNORECASE)
                target_match = re.search(r'TARGET:\s*(.+?)(?=DATA:|$)', 
                                        suggestion_block, re.DOTALL | re.IGNORECASE)
                data_match = re.search(r'DATA:\s*(\{.+?\})', 
                                      suggestion_block, re.DOTALL | re.IGNORECASE)
                
                if action_match:
                    change = AIProposedChange(
                        change_type=action_match.group(1).lower().strip(),
                        target_id=target_match.group(1).strip() if target_match else None,
                        description=description_match.group(1).strip() if description_match else suggestion_block[:100],
                        data=json.loads(data_match.group(1)) if data_match else {}
                    )
                    changes.append(change)
            except (json.JSONDecodeError, AttributeError):
                # If parsing fails, create a text-only suggestion
                continue
        
        return changes
    
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


# Convenience function for testing
def test_connection(api_key: str, api_endpoint: str = "https://api.openai.com/v1",
                   model: str = "gpt-4o") -> Tuple[bool, str]:
    """
    Test the API connection with provided credentials.
    
    Args:
        api_key: API key to test
        api_endpoint: API endpoint
        model: Model to use
        
    Returns:
        Tuple of (success, message)
    """
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=api_endpoint)
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello, this is a test."}],
            max_tokens=10
        )
        
        return True, "Connection successful!"
    except ImportError:
        return False, "OpenAI package not installed. Run: pip install openai"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"
