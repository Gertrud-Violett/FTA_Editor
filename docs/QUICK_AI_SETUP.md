# Quick AI Provider Setup Guide

**Choose your AI provider and get started in 5 minutes!**

## How Model Selection Works

Once a key for your chosen provider is saved, the FTA Editor fetches the **available models** for it, so the list shows the models your account can actually use. Until then it shows the provider's built-in default models. Microsoft Copilot always shows the built-in list, because Azure has no model list for a key. The model field also accepts any model name you type.

- **Test & Save a key** → the live model list is used from then on
- **Click Reload** (↻ in the desktop app) → Manually refresh the model list anytime
- Can't connect? Falls back to **default models** with a notification
- The legacy desktop app keeps its 1.5 provider code: older built-in lists, no live Anthropic list, and no support for current Claude models or OpenAI's reasoning models (see [desktop/README.md](../desktop/README.md))

## TL;DR - Quick Start

### 1️⃣ Google Gemini (Free + Pay-as-you-go)
```
1. Go to: https://aistudio.google.com/apikey
2. Click "Create API Key"
3. Copy your API key
4. Open FTA Editor → AI Settings (⚙)
5. Select "Google Gemini"
6. Paste API key
7. Click "Test & Save"
```
✅ **Free tier**: 15 requests/minute  
💰 **Cost**: ~$0.001 per FTA analysis after free tier

---

### 2️⃣ Anthropic Claude (Pay-as-you-go)
```
1. Go to: https://console.anthropic.com/
2. Sign up → Create API Key
3. Set up billing (credit card)
4. Copy your API key
5. Open FTA Editor → AI Settings (⚙)
6. Select "Anthropic Claude"
7. Paste API key
8. Click "Test & Save"
```
💰 **Cost**: ~$0.02-0.05 per FTA analysis  
✨ **Best for**: Complex reasoning

---

### 3️⃣ OpenAI GPT-4o (Pay-as-you-go)
```
1. Go to: https://platform.openai.com/
2. Sign up → Create API Key
3. Add billing (credit card)
4. Copy your API key
5. Open FTA Editor → AI Settings (⚙)
6. Select "OpenAI" → Paste key → Test & Save
```
💰 **Cost**: ~$0.01-0.02 per FTA analysis  
⚡ **Speed**: Fastest

---

### 4️⃣ GitHub Models (through the OpenAI provider)
```
1. On GitHub: Settings → Developer settings → Personal access tokens
   → Fine-grained tokens → Generate new token
2. Give it the "models: read" permission, then copy the token
3. Open FTA Editor → AI Settings (⚙)
4. Select "OpenAI"
5. API Endpoint (under Advanced): https://models.github.ai/inference
6. API Key: paste the token
7. Model: type publisher/model, e.g. openai/gpt-4.1
8. Click "Test & Save"
```
The model list cannot be loaded from this endpoint, so type the model name.

💰 **Cost and limits**: see [GitHub's documentation](https://docs.github.com/en/rest/models/inference)

---

## Provider Comparison at a Glance

| | **Gemini** | **Claude** | **GPT-4o** | **GitHub Models** |
|---|-----------|-----------|----------|-----------|
| **Free?** | ✅ | ❌ | ❌ | See GitHub |
| **Speed** | ⚡ Fast | 🐢 Medium | ⚡⚡ Fastest | Depends on the model |
| **Cost/Analysis** | $0.001 | $0.02-0.05 | $0.01-0.02 | See GitHub |
| **Best For** | Budget | Reasoning | General | GitHub users |
| **Setup** | 2 min | 5 min | 5 min | 5 min |

---

## Step-by-Step: Google Gemini (Recommended for Starting)

### Step 1: Get API Key
1. Visit [Google AI Studio](https://aistudio.google.com/apikey)
2. Click **"Create API Key"** button
3. Select your Google Cloud project (or create new)
4. You'll see your API key (looks like: `AIzaSy...`)
5. Copy it to clipboard

### Step 2: Add to FTA Editor
1. Launch FTA Editor
2. Look for the chat panel on the right side
3. Click the **⚙ (Settings)** button
4. In the dialog:
   - **Provider**: Select `"Google Gemini"` from the provider list
   - **API Key**: Paste your key from Step 1
   - **Endpoint**: Auto-filled (`https://generativelanguage.googleapis.com/v1beta`)
   - **Model**: Select `"gemini-2.5-pro"` (or `"gemini-2.5-flash"` for speed)
5. Click **"Test & Save"** button
6. You'll see: "Connected. The assistant is ready." (desktop app: ✓ "Configuration saved successfully!")

### Step 3: Start Using
- Now you can ask FTA questions!
- Click "Analyze FTA" for quick suggestions
- Type in the chat box to ask custom questions

**You're done! 🎉**

---

## Step-by-Step: Anthropic Claude

### Step 1: Get API Key
1. Visit [Anthropic Console](https://console.anthropic.com/)
2. Sign up or log in with your email
3. Click **"Create Key"** button in API Keys section
4. Copy your API key (starts with: `sk-ant-`)

### Step 2: Set Up Billing
1. In Anthropic Console, go to **"Settings"** → **"Billing"**
2. Add your credit card
3. Set spending limit (optional, recommended: $10-20/month)

### Step 3: Add to FTA Editor
1. Open FTA Editor AI Settings (⚙)
2. In the dialog:
   - **Provider**: Select `"Anthropic Claude"`
   - **API Key**: Paste your key
   - **Endpoint**: Auto-filled
   - **Model**: Keep the pre-selected `"claude-opus-5-5"`, or select `"claude-sonnet-5-5"` for faster, cheaper answers
3. Click **"Test & Save"**
4. From then on, **Reload** in the dialog lists the models your Anthropic account can use

**You're done! 🎉**

---

## Step-by-Step: OpenAI GPT-4o

### Step 1: Create Account & Get API Key
1. Visit [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in
3. Click **"API keys"** in left menu
4. Click **"Create new secret key"**
5. Copy the key (won't show again!)

### Step 2: Set Up Billing
1. Go to **"Settings"** → **"Billing"** → **"Overview"**
2. Click **"Add payment method"**
3. Add credit card
4. Go to **"Usage limits"** and set monthly limit (e.g., $25)

### Step 3: Add to FTA Editor
1. Open FTA Editor AI Settings (⚙)
2. In the dialog:
   - **Provider**: Select `"OpenAI"`
   - **API Key**: Paste your key
   - **Endpoint**: Auto-filled
   - **Model**: Select `"gpt-4o"` (reasoning models such as the o-series and GPT-5 work too)
3. Click **"Test & Save"**

**You're done! 🎉**

---

## Switching Providers Later

Anytime you want to switch:

1. Click AI Settings (⚙) again
2. Select a different provider from the provider list
3. Endpoint and model options update automatically
4. Enter API key for new provider
5. Click **"Test & Save"**

Only one provider's credentials are stored: saving a new provider replaces the old key, so keep the old key if you want to switch back later.

Saving a different provider, or a different endpoint, starts a new conversation: the new one is never sent your conversation with the old one.

---

## Troubleshooting

### "Connection failed" Error

**For Gemini:**
- Check API key format (should be: `AIzaSy...`)
- Verify API is enabled in Google Cloud Console
- Try a simpler model like `gemini-2.5-flash`

**For Claude:**
- Check API key starts with `sk-ant-`
- Verify billing is set up
- Check if your account is in good standing

**For OpenAI:**
- Check API key starts with `sk-`
- Verify billing and spending limits are set
- Check if you have remaining balance

### "Model not found" Error
- Your region might not have that model
- Try selecting a different model from the dropdown
- Check provider documentation for region availability

### "The AI provider did not respond within 120 seconds" (web app)
- A large tree can take a while: try again, or choose a faster model
- Check the endpoint and model in AI Settings
- A provider that has stopped answering keeps the assistant busy until its call gives up, at most about four minutes (two for Gemini); until then a new request says another AI request is still running

---





## Next Steps

1. **Pick your provider** from the options above
2. **Follow the 3-step setup** for your choice
3. **Click "Test & Save"** to verify connection
4. **Start analyzing FTAs!** 🚀

**Questions?** Check [MULTI_PROVIDER_SETUP.md](MULTI_PROVIDER_SETUP.md) for detailed documentation.

---

**Pro Tip:** Start with Gemini free tier to test everything out, then upgrade to your favorite paid provider for production use!
