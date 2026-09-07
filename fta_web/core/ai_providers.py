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
        return ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"]
    
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
    """Google Gemini API provider"""
    
    @staticmethod
    def get_provider_name() -> str:
        return "Google Gemini"
    
    def get_default_endpoint(self) -> str:
        return "https://generativelanguage.googleapis.com/v1beta"
    
    def get_default_models(self) -> List[str]:
        return ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"]
    
    def get_available_models(self, api_key: str, endpoint: str) -> Tuple[List[str], Optional[str]]:
        """Fetch available models from Google Gemini API"""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=api_key)
            models = genai.list_models()
            
            # Filter for models that support generateContent
            available = []
            for model in models:
                if "generateContent" in model.supported_generation_methods:
                    model_name = model.name.replace("models/", "")
                    available.append(model_name)
            
            return sorted(available) if available else self.get_default_models(), None
        except ImportError:
            return self.get_default_models(), "Google Generative AI package not installed"
        except Exception as e:
            return self.get_default_models(), f"Could not fetch models: {str(e)}"
    
    def test_connection(self, api_key: str, endpoint: str, model: str) -> Tuple[bool, str]:
        """Test Gemini connection"""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=api_key)
            gm = genai.GenerativeModel(model)
            response = gm.generate_content("Hello, this is a test.", stream=False)
            return True, "Google Gemini connection successful!"
        except ImportError:
            return False, "Google Generative AI package not installed. Run: pip install google-generativeai"
        except Exception as e:
            return False, f"Gemini connection failed: {str(e)}"
    
    def send_message(self, api_key: str, endpoint: str, model: str,
                    messages: List[Dict[str, str]],
                    max_tokens: int = 2000) -> Tuple[Optional[str], Optional[str]]:
        """Send message via Gemini API"""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=api_key)
            
            # Prepare system instruction
            system_instruction = ""
            chat_messages = []
            
            for msg in messages:
                if msg.get("role") == "system":
                    system_instruction = msg.get("content", "")
                else:
                    chat_messages.append({
                        "role": "user" if msg.get("role") == "user" else "model",
                        "parts": msg.get("content", "")
                    })
            
            gm = genai.GenerativeModel(
                model,
                system_instruction=system_instruction if system_instruction else None
            )
            
            chat = gm.start_chat(history=chat_messages[:-1] if len(chat_messages) > 1 else [])
            response = chat.send_message(
                chat_messages[-1]["parts"] if chat_messages else "Hello",
                stream=False
            )
            
            return response.text, None
        except ImportError:
            return None, "Google Generative AI package not installed. Run: pip install google-generativeai"
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
