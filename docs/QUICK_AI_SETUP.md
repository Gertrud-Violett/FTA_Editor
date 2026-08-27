# Quick AI Provider Setup Guide

**Choose your AI provider and get started in 5 minutes!**

## How Model Selection Works

When you enter your API key in the FTA Editor, it automatically fetches the **available models** for your chosen provider. This ensures you always have the latest models that are actually available for your account.

- **Enter API Key** → Models automatically populate
- **Click Refresh Button** (↻) → Manually refresh the model list anytime
- Can't connect? Falls back to **default models** with a notification

## TL;DR - Quick Start

### 1️⃣ Google Gemini (Free + Pay-as-you-go)
```
1. Go to: https://aistudio.google.com/apikey
2. Click "Create API Key"
3. Copy your API key
4. Open FTA Editor → AI Settings (⚙)
5. Select "Google Gemini"
6. Paste API key → Models auto-populate
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
7. Paste API key → Models auto-populate
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

### 4️⃣ GitHub Copilot (With $20/month subscription)
```
1. You already have access via subscription!
2. Go to: https://github.com/settings/tokens
3. Generate personal access token (read:user scope)
4. Open FTA Editor → AI Settings (⚙)
5. Select "OpenAI" (GitHub uses OpenAI API)
6. Paste token → Test & Save
```
💰 **Cost**: Already included with GitHub Copilot Pro ($20/month)

---

## Provider Comparison at a Glance

| | **Gemini** | **Claude** | **GPT-4o** | **Copilot** |
|---|-----------|-----------|----------|-----------|
| **Free?** | ✅ | ❌ | ❌ | ❌ |
| **Speed** | ⚡ Fast | 🐢 Medium | ⚡⚡ Fastest | ⚡⚡ |
| **Cost/Analysis** | $0.001 | $0.02-0.05 | $0.01-0.02 | Included |
| **Best For** | Budget | Reasoning | General | Devs |
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
   - **Provider**: Select `"Google Gemini"` from dropdown
   - **API Key**: Paste your key from Step 1
   - **Endpoint**: Auto-filled (`https://generativelanguage.googleapis.com/v1beta`)
   - **Model**: Select `"gemini-1.5-pro"`
5. Click **"Test & Save"** button
6. You'll see: ✓ "Configuration saved successfully!"

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
   - **Model**: Select `"claude-3-5-sonnet-20241022"`
3. Click **"Test & Save"**

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
   - **Model**: Select `"gpt-4o"`
3. Click **"Test & Save"**

**You're done! 🎉**

---

## Switching Providers Later

Anytime you want to switch:

1. Click AI Settings (⚙) again
2. Select a different provider from dropdown
3. Endpoint and model options update automatically
4. Enter API key for new provider
5. Click **"Test & Save"**

Your old credentials are saved - you can always switch back!

---

## Troubleshooting

### "Connection failed" Error

**For Gemini:**
- Check API key format (should be: `AIzaSy...`)
- Verify API is enabled in Google Cloud Console
- Try a simpler model like `gemini-1.5-flash`

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

---





## Next Steps

1. **Pick your provider** from the options above
2. **Follow the 3-step setup** for your choice
3. **Click "Test & Save"** to verify connection
4. **Start analyzing FTAs!** 🚀

**Questions?** Check [MULTI_PROVIDER_SETUP.md](MULTI_PROVIDER_SETUP.md) for detailed documentation.

---

**Pro Tip:** Start with Gemini free tier to test everything out, then upgrade to your favorite paid provider for production use!
