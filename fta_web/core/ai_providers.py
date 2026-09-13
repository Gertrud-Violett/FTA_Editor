"""
AI Provider Abstraction Layer
Supports OpenAI, Anthropic Claude, and Google Gemini APIs

Copyright (c) makkiblog.com - BSD-2 License
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Optional
import json


class AIProvider(ABC):
    """Abstract base class for AI providers"""
    
    @abstractmethod
    def test_connection(self, api_key: str, endpoint: str, model: str) -> Tuple[bool, str]:
        """Test connection to the AI provider"""
        pass
    
    @abstractmethod
    def send_message(self, api_key: str, endpoint: str, model: str,
                    messages: List[Dict[str, str]],
                    max_tokens: int = 2000) -> Tuple[Optional[str], Optional[str]]:
        """Send message to AI provider and get response"""
        pass
    
    @abstractmethod
    def get_default_endpoint(self) -> str:
        """Get the default endpoint for this provider"""
        pass
    
    @abstractmethod
    def get_default_models(self) -> List[str]:
        """Get list of default/fallback models for this provider"""
        pass
    
    @abstractmethod
    def get_available_models(self, api_key: str, endpoint: str) -> Tuple[List[str], Optional[str]]:
        """Fetch available models from the provider API"""
        pass
    
    @staticmethod
    def get_provider_name() -> str:
        """Get provider name"""
        pass


class OpenAIProvider(AIProvider):
    """OpenAI API provider (includes GitHub Copilot with OpenAI base_url)"""
    
    @staticmethod
    def get_provider_name() -> str:
        return "OpenAI"
    
    def get_default_endpoint(self) -> str:
        return "https://api.openai.com/v1"
    
    def get_default_models(self) -> List[str]:
        return ["gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"]
    
    def get_available_models(self, api_key: str, endpoint: str) -> Tuple[List[str], Optional[str]]:
        """Fetch available models from OpenAI API"""
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=api_key, base_url=endpoint)
            models = client.models.list()
            model_names = [m.id for m in models.data if "gpt" in m.id.lower()]
            return sorted(model_names), None
        except ImportError:
            return self.get_default_models(), "OpenAI package not installed"
        except Exception as e:
            return self.get_default_models(), f"Could not fetch models: {str(e)}"
    
    def test_connection(self, api_key: str, endpoint: str, model: str) -> Tuple[bool, str]:
        """Test OpenAI connection"""
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=api_key, base_url=endpoint)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello, this is a test."}],
                max_tokens=10
            )
            return True, "OpenAI connection successful!"
        except ImportError:
            return False, "OpenAI package not installed. Run: pip install openai"
        except Exception as e:
            return False, f"OpenAI connection failed: {str(e)}"
    
    def send_message(self, api_key: str, endpoint: str, model: str,
                    messages: List[Dict[str, str]],
                    max_tokens: int = 2000) -> Tuple[Optional[str], Optional[str]]:
        """Send message via OpenAI API"""
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=api_key, base_url=endpoint)
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7
            )
            return response.choices[0].message.content, None
        except ImportError:
            return None, "OpenAI package not installed. Run: pip install openai"
        except Exception as e:
            return None, f"OpenAI error: {str(e)}"


class AnthropicProvider(AIProvider):
    """Anthropic Claude API provider"""
    
    @staticmethod
    def get_provider_name() -> str:
        return "Anthropic Claude"
    
    def get_default_endpoint(self) -> str:
        return "https://api.anthropic.com"
    
    def get_default_models(self) -> List[str]:
        # Divergence D9: refreshed from the Claude 3 family, which had aged out.
        #
        # This list is only the *fallback* shown when the live model fetch fails
        # -- offline, behind a proxy, or with a key that cannot list models. That
        # is exactly when a wrong entry hurts most: the user cannot discover the
        # real names, picks the pre-selected first item, and gets an API error
        # with no obvious cause. The first entry is the one the settings dialog
        # pre-selects, so it leads.
        #
        # The model field is editable, so a name released after this list was
        # written can always be typed in. Prefer the live fetch over this.
        return [
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-haiku-4-5",
            "claude-opus-4-8",
            "claude-sonnet-4-6",
        ]
    
    def get_available_models(self, api_key: str, endpoint: str) -> Tuple[List[str], Optional[str]]:
        """Fetch available models from Anthropic API"""
        try:
            from anthropic import Anthropic
            
            # Anthropic doesn't provide a list_models endpoint
            # Return the most up-to-date known models
            return self.get_default_models(), None
        except ImportError:
            return self.get_default_models(), "Anthropic package not installed"
        except Exception as e:
            return self.get_default_models(), f"Error: {str(e)}"
    
    def test_connection(self, api_key: str, endpoint: str, model: str) -> Tuple[bool, str]:
        """Test Anthropic connection"""
        try:
            from anthropic import Anthropic
            
            client = Anthropic(api_key=api_key)
            message = client.messages.create(
                model=model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hello, this is a test."}]
            )
            return True, "Anthropic Claude connection successful!"
        except ImportError:
            return False, "Anthropic package not installed. Run: pip install anthropic"
        except Exception as e:
            return False, f"Anthropic connection failed: {str(e)}"
    
    def send_message(self, api_key: str, endpoint: str, model: str,
                    messages: List[Dict[str, str]],
                    max_tokens: int = 2000) -> Tuple[Optional[str], Optional[str]]:
        """Send message via Anthropic API"""
        try:
            from anthropic import Anthropic
            
            client = Anthropic(api_key=api_key)
            
            # Convert system message if present
            system_message = ""
            user_messages = []
            
            for msg in messages:
                if msg.get("role") == "system":
                    system_message = msg.get("content", "")
                else:
                    user_messages.append(msg)
            
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_message if system_message else None,
                messages=user_messages
            )
            return response.content[0].text, None
        except ImportError:
            return None, "Anthropic package not installed. Run: pip install anthropic"
        except Exception as e:
            return None, f"Anthropic error: {str(e)}"


class GeminiProvider(AIProvider):
    """Google Gemini API provider.

    Divergence D11 (fta_web/core/DIVERGENCE.md): migrated from
    ``google.generativeai`` to ``google.genai``. The former is end-of-life
    ("All support ... has ended ... switch to the google.genai package") and,
    as a PEP 420 namespace package, silently failed to import in a
    PyInstaller build -- see build/README.md's former "Known limitation:
    Gemini in a frozen build" section, now resolved by this migration.
    ``google.genai`` also drops the ~100 MB google-api-python-client/grpc
    dependency chain the old package pulled in for no reason this app uses.
    """

    @staticmethod
    def get_provider_name() -> str:
        return "Google Gemini"

    def get_default_endpoint(self) -> str:
        return "https://generativelanguage.googleapis.com/v1beta"

    def get_default_models(self) -> List[str]:
        # Divergence D9 refreshed the Anthropic list for the same reason this
        # one is stale: gemini-1.5-* was retired well before this migration.
        # This is the fallback shown only when the live fetch below fails, so
        # a wrong entry here does the most damage -- see D9's writeup. The
        # model field is an editable combo regardless, so a newer name can
        # always be typed in.
        return ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"]

    def _client(self, api_key: str):
        """A fresh client. ``endpoint`` is accepted by every provider in this
        module for interface uniformity, but the Gemini Developer API has no
        equivalent of an OpenAI-compatible custom base URL -- the old
        ``google.generativeai`` implementation ignored it too."""
        from google import genai

        return genai.Client(api_key=api_key)

    def get_available_models(self, api_key: str, endpoint: str) -> Tuple[List[str], Optional[str]]:
        """Fetch available models from Google Gemini API"""
        try:
            client = self._client(api_key)

            # supported_actions holds the same raw REST action names
            # (e.g. "generateContent") that the old SDK exposed as
            # supported_generation_methods -- same filter, new field name.
            available = []
            for model in client.models.list():
                if "generateContent" in (model.supported_actions or []):
                    available.append((model.name or "").replace("models/", ""))

            return sorted(available) if available else self.get_default_models(), None
        except ImportError:
            return self.get_default_models(), "google-genai package not installed"
        except Exception as e:
            return self.get_default_models(), f"Could not fetch models: {str(e)}"

    def test_connection(self, api_key: str, endpoint: str, model: str) -> Tuple[bool, str]:
        """Test Gemini connection"""
        try:
            client = self._client(api_key)
            client.models.generate_content(model=model, contents="Hello, this is a test.")
            return True, "Google Gemini connection successful!"
        except ImportError:
            return False, "google-genai package not installed. Run: pip install google-genai"
        except Exception as e:
            return False, f"Gemini connection failed: {str(e)}"

    def send_message(self, api_key: str, endpoint: str, model: str,
                    messages: List[Dict[str, str]],
                    max_tokens: int = 2000) -> Tuple[Optional[str], Optional[str]]:
        """Send message via Gemini API"""
        try:
            from google.genai import types

            client = self._client(api_key)

            # Same shape as the pre-migration code: the last "system" message
            # becomes the system instruction, everything else becomes history
            # with "assistant" remapped to Gemini's "model" role, and the
            # final turn is sent as the new message rather than replayed into
            # history.
            system_instruction = ""
            turns: List[Tuple[str, str]] = []  # (role, text), role already remapped

            for msg in messages:
                if msg.get("role") == "system":
                    system_instruction = msg.get("content", "")
                else:
                    role = "user" if msg.get("role") == "user" else "model"
                    turns.append((role, msg.get("content", "")))

            config = types.GenerateContentConfig(
                system_instruction=system_instruction or None,
                max_output_tokens=max_tokens,
            )

            # ContentDict history entries need parts as a list of PartDicts;
            # the final message goes to send_message as a plain string, which
            # -- unlike a single-element PartDict list -- is unambiguous to
            # the SDK's argument validator.
            history = [
                {"role": role, "parts": [{"text": text}]}
                for role, text in turns[:-1]
            ]
            chat = client.chats.create(model=model, config=config, history=history)
            final_message = turns[-1][1] if turns else "Hello"
            response = chat.send_message(final_message)

            return response.text, None
        except ImportError:
            return None, "google-genai package not installed. Run: pip install google-genai"
        except Exception as e:
            return None, f"Gemini error: {str(e)}"


class MicrosoftCopilotProvider(AIProvider):
    """Microsoft Copilot API provider (Azure OpenAI)"""
    
    @staticmethod
    def get_provider_name() -> str:
        return "Microsoft Copilot"
    
    def get_default_endpoint(self) -> str:
        # User needs to provide their Azure OpenAI endpoint
        return "https://YOUR-RESOURCE.openai.azure.com/openai/deployments/YOUR-DEPLOYMENT"
    
    def get_default_models(self) -> List[str]:
        return ["gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-35-turbo"]
    
    def get_available_models(self, api_key: str, endpoint: str) -> Tuple[List[str], Optional[str]]:
        """Fetch available deployments from Azure OpenAI"""
        try:
            from openai import AzureOpenAI
            
            # Extract resource name and deployment from endpoint
            # Format: https://{resource}.openai.azure.com/openai/deployments/{deployment}
            if "/deployments/" in endpoint:
                base_url = endpoint.rsplit("/deployments/", 1)[0]
                deployment = endpoint.rsplit("/deployments/", 1)[1].split("/")[0]
            else:
                base_url = endpoint
                deployment = "gpt-4o"
            
            # Try to list available models (if API supports it)
            # Otherwise return default models
            return self.get_default_models(), "Using default models (Azure doesn't provide model list API)"
        except ImportError:
            return self.get_default_models(), "OpenAI package not installed"
        except Exception as e:
            return self.get_default_models(), f"Could not fetch models: {str(e)}"
    
    def test_connection(self, api_key: str, endpoint: str, model: str) -> Tuple[bool, str]:
        """Test Microsoft Copilot (Azure OpenAI) connection"""
        try:
            from openai import AzureOpenAI
            
            # Parse endpoint to extract base URL and deployment
            # Expected format: https://{resource}.openai.azure.com/openai/deployments/{deployment}
            if "/deployments/" in endpoint:
                base_url = endpoint.rsplit("/deployments/", 1)[0]
                deployment = endpoint.rsplit("/deployments/", 1)[1].rstrip("/").split("/")[0]
                if not deployment:
                    deployment = model
            else:
                base_url = endpoint
                deployment = model
            
            # Azure OpenAI uses api_version
            client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=base_url,
                api_version="2024-08-01-preview"
            )
            
            response = client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": "Hello, this is a test."}],
                max_tokens=10
            )
            return True, "Microsoft Copilot (Azure OpenAI) connection successful!"
        except ImportError:
            return False, "OpenAI package not installed. Run: pip install openai>=1.0.0"
        except Exception as e:
            error_msg = str(e)
            # Provide helpful error messages
            if "deployment" in error_msg.lower():
                return False, f"Deployment error: Check your deployment name in the endpoint URL. Error: {error_msg}"
            elif "auth" in error_msg.lower() or "401" in error_msg:
                return False, f"Authentication failed: Check your API key. Error: {error_msg}"
            elif "404" in error_msg:
                return False, f"Endpoint not found: Verify your Azure resource URL. Error: {error_msg}"
            else:
                return False, f"Microsoft Copilot connection failed: {error_msg}"
    
    def send_message(self, api_key: str, endpoint: str, model: str,
                    messages: List[Dict[str, str]],
                    max_tokens: int = 2000) -> Tuple[Optional[str], Optional[str]]:
        """Send message via Microsoft Copilot (Azure OpenAI) API"""
        try:
            from openai import AzureOpenAI
            
            # Parse endpoint to extract base URL and deployment
            if "/deployments/" in endpoint:
                base_url = endpoint.rsplit("/deployments/", 1)[0]
                deployment = endpoint.rsplit("/deployments/", 1)[1].rstrip("/").split("/")[0]
                if not deployment:
                    deployment = model
            else:
                base_url = endpoint
                deployment = model
            
            client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=base_url,
                api_version="2024-08-01-preview"
            )
            
            response = client.chat.completions.create(
                model=deployment,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7
            )
            return response.choices[0].message.content, None
        except ImportError:
            return None, "OpenAI package not installed. Run: pip install openai>=1.0.0"
        except Exception as e:
            return None, f"Microsoft Copilot error: {str(e)}"


class AIProviderFactory:
    """Factory for creating AI provider instances"""
    
    _providers = {
        "openai": OpenAIProvider(),
        "github": OpenAIProvider(),  # GitHub Copilot uses OpenAI compatible API
        "microsoft": MicrosoftCopilotProvider(),
        "azure": MicrosoftCopilotProvider(),  # Alias for Microsoft Copilot
        "claude": AnthropicProvider(),
        "anthropic": AnthropicProvider(),
        "gemini": GeminiProvider(),
        "google": GeminiProvider(),
    }
    
    # Map full provider display names to internal keys
    _provider_name_map = {
        "openai": "openai",
        "github copilot": "github",
        "github": "github",
        "microsoft copilot": "microsoft",
        "microsoft": "microsoft",
        "azure openai": "azure",
        "azure": "azure",
        "anthropic claude": "claude",
        "claude": "claude",
        "google gemini": "gemini",
        "gemini": "gemini",
    }
    
    @staticmethod
    def get_provider(provider_name: str) -> Optional[AIProvider]:
        """Get provider by name (supports both full names and short keys)"""
        normalized = provider_name.lower().strip()
        # Try direct lookup first
        if normalized in AIProviderFactory._providers:
            return AIProviderFactory._providers[normalized]
        # Then try the name map
        if normalized in AIProviderFactory._provider_name_map:
            key = AIProviderFactory._provider_name_map[normalized]
            return AIProviderFactory._providers.get(key)
        return None
    
    @staticmethod
    def get_provider_names() -> List[str]:
        """Get list of available provider names"""
        return list(set(
            [name.replace("ai", "").replace("provider", "").strip() 
             for name in AIProviderFactory._providers.keys()]
        ))
    
    @staticmethod
    def get_all_providers() -> Dict[str, AIProvider]:
        """Get all available providers"""
        seen = set()
        unique_providers = {}
        for name, provider in AIProviderFactory._providers.items():
            provider_name = provider.get_provider_name()
            if provider_name not in seen:
                seen.add(provider_name)
                unique_providers[provider_name] = provider
        return unique_providers
