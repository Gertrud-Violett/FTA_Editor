"""
Test script for Microsoft Copilot provider
Tests the Microsoft Copilot (Azure OpenAI) integration
"""

import sys
from pathlib import Path

# Add src directory to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from ai_providers import AIProviderFactory, MicrosoftCopilotProvider

def test_microsoft_copilot_provider():
    """Test Microsoft Copilot provider registration and basic functionality"""
    
    print("=" * 60)
    print("Microsoft Copilot Provider Test")
    print("=" * 60)
    
    # Test 1: Provider registration
    print("\n1. Testing provider registration...")
    provider = AIProviderFactory.get_provider("microsoft")
    assert provider is not None, "Microsoft provider not found!"
    print(f"   ✓ Provider found: {provider.get_provider_name()}")
    
    # Test 2: Provider aliases
    print("\n2. Testing provider aliases...")
    for alias in ["microsoft", "azure", "microsoft copilot", "azure openai"]:
        p = AIProviderFactory.get_provider(alias)
        assert p is not None, f"Alias '{alias}' not working"
        assert p.get_provider_name() == "Microsoft Copilot", f"Wrong provider for alias '{alias}'"
        print(f"   ✓ Alias '{alias}' works")
    
    # Test 3: Get all providers
    print("\n3. Testing provider listing...")
    all_providers = AIProviderFactory.get_all_providers()
    provider_names = list(all_providers.keys())
    print(f"   Available providers: {', '.join(provider_names)}")
    assert "Microsoft Copilot" in provider_names, "Microsoft Copilot not in provider list!"
    print("   ✓ Microsoft Copilot appears in provider list")
    
    # Test 4: Default endpoint
    print("\n4. Testing default endpoint...")
    default_endpoint = provider.get_default_endpoint()
    print(f"   Default endpoint: {default_endpoint}")
    assert "openai.azure.com" in default_endpoint, "Incorrect default endpoint"
    print("   ✓ Default endpoint is correct")
    
    # Test 5: Default models
    print("\n5. Testing default models...")
    default_models = provider.get_default_models()
    print(f"   Default models: {', '.join(default_models)}")
    assert "gpt-4o" in default_models, "gpt-4o not in default models"
    print("   ✓ Default models include gpt-4o")
    
    # Test 6: Connection test (will fail without valid credentials, but tests the method exists)
    print("\n6. Testing connection method (expected to fail with test credentials)...")
    success, message = provider.test_connection(
        api_key="test_key",
        endpoint="https://test.openai.azure.com/openai/deployments/test",
        model="gpt-4o"
    )
    print(f"   Connection test: {message}")
    print("   ✓ Connection test method works (failure expected with test credentials)")
    
    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
    print("\nMicrosoft Copilot provider is ready to use!")
    print("\nTo configure in FTA Editor:")
    print("1. Launch: python src/FTA_Editor_UI.py")
    print("2. Click ⚙️ AI Settings")
    print("3. Select 'Microsoft Copilot' from provider dropdown")
    print("4. Enter your Azure OpenAI credentials:")
    print("   - API Key: From Azure Portal → Keys and Endpoint")
    print("   - Endpoint: https://{resource}.openai.azure.com/openai/deployments/{deployment}")
    print("   - Model: Your deployment name")
    print("5. Click 'Test & Save'")
    print("\nSee docs/MICROSOFT_COPILOT_SETUP.md for detailed setup instructions.")

if __name__ == "__main__":
    try:
        test_microsoft_copilot_provider()
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
