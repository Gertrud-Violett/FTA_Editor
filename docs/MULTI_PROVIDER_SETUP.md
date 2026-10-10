# Multi-Provider AI Setup Guide

FTA Editor supports **four AI providers**: OpenAI, Anthropic Claude, Google Gemini and Microsoft Copilot (Azure OpenAI, see [MICROSOFT_COPILOT_SETUP.md](MICROSOFT_COPILOT_SETUP.md)). This guide helps you choose and configure the first three.

## Quick Comparison

| Criteria | Google Gemini | Anthropic Claude | OpenAI (GPT-4o) |
|----------|--------------|------------------|-----------------|
| **Free Tier** | ✅ Yes (15 req/min) | ❌ No | ❌ No |
| **Cost/Token** | $0.075/1M input | $3/1M input | $5/1M input |
| **Best For** | Budget-conscious | Complex reasoning | General purpose |
| **Response Speed** | Fast ⚡ | Medium | Fast ⚡ |
| **Setup Time** | 2 min | 5 min | 5 min |
| **API Availability** | Excellent | Excellent | Excellent |

## Detailed Setup for Each Provider

### 1. Google Gemini (Recommended for Budget-Conscious Users)

**Pros:**
- Free tier available (15 requests per minute)
- Pay-as-you-go after free tier
- Fast responses
- Good quality for FTA analysis

**Cons:**
- Rate-limited on free tier
- Not suitable for high-volume automated analysis

**Setup Steps:**

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Click **Create API Key**
3. Select your Google Cloud project (or create new)
4. Copy the generated API key
5. In FTA Editor AI Settings:
   - **Provider**: Select "Google Gemini"
   - **API Key**: Paste your Gemini API key
   - **Endpoint**: Auto-filled as `https://generativelanguage.googleapis.com/v1beta`
   - **Model**: Choose `gemini-2.5-pro` (recommended) or `gemini-2.5-flash`
6. Click **Test & Save**

**Cost Estimate:**
- Free: 15 requests/minute, 2 RPD (requests per day) limits
- Paid: ~$0.075 per 1M input tokens (~$0.001 per FTA analysis)

**Documentation**: https://ai.google.dev/tutorials/python_quickstart

---

### 2. Anthropic Claude (Best for Complex Reasoning)

**Pros:**
- Excellent reasoning and analysis capabilities
- Great for complex FTA logic evaluation
- Transparent pricing
- Good documentation

**Cons:**
- No free tier
- Slightly slower than GPT-4o
- Higher per-token cost than Gemini

**Setup Steps:**

1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Sign up or log in to your account
3. Navigate to **API Keys** in the sidebar
4. Click **Create Key**
5. Copy the API key
6. Add billing (credit/debit card required)
7. In FTA Editor AI Settings:
   - **Provider**: Select "Anthropic Claude"
   - **API Key**: Paste your Claude API key
   - **Endpoint**: Auto-filled as `https://api.anthropic.com`
   - **Model**: Choose `claude-sonnet-5` (recommended) or `claude-opus-5`
8. Click **Test & Save**

**Model Options** (the built-in list; the Claude 3 models this guide used to name are retired):
- **Claude Sonnet** (`claude-sonnet-5`, recommended): Best balance of speed and capability
- **Claude Opus** (`claude-opus-5`): Most capable but slower
- **Claude Haiku** (`claude-haiku-4-5`): Fastest but less capable

**Cost Estimate** (Claude 3.x-era prices; check Anthropic's pricing page for current ones):
- Claude 3.5 Sonnet: ~$3/1M input, ~$15/1M output tokens (~$0.02-0.05 per FTA analysis)
- Claude 3 Haiku: ~$0.80/1M input, ~$4/1M output tokens

**Documentation**: https://docs.anthropic.com/

---

### 3. OpenAI (GPT-4o, Best for General Purpose)

**Pros:**
- Most reliable and widely used
- Excellent quality
- Good speed
- Well-documented

**Cons:**
- No free tier
- Higher cost than Gemini
- Requires active subscription

**Setup Steps:**

1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in
3. Go to **Dashboard** → **API keys**
4. Click **Create new secret key**
5. Copy the key (won't be shown again!)
6. Set up billing:
   - Go to **Settings** → **Billing**
   - Add payment method
   - Set usage limits if desired (recommended: $10-50/month)
7. In FTA Editor AI Settings:
   - **Provider**: Select "OpenAI"
   - **API Key**: Paste your OpenAI API key
   - **Endpoint**: Auto-filled as `https://api.openai.com/v1`
   - **Model**: Choose `gpt-4o` (recommended) or `gpt-4-turbo`
8. Click **Test & Save**

**Model Options:**
- **GPT-4o** (Recommended): Fastest, smartest, most cost-effective
- **GPT-4-turbo**: Capable, good for complex analysis
- **GPT-4**: Slower but very reliable
- **GPT-3.5-turbo**: Budget option, still good quality

**Cost Estimate:**
- GPT-4o: ~$5/1M input, ~$15/1M output tokens (~$0.01-0.02 per FTA analysis)
- GPT-4-turbo: ~$10/1M input, ~$30/1M output tokens
- GPT-3.5-turbo: ~$0.50/1M input, ~$1.50/1M output tokens

**Recommended Setup for Cost Control:**
```
1. Set usage limits in OpenAI Settings (e.g., $10/month)
2. Use gpt-4o model for best value
3. Monthly cost typically: $2-10 for regular FTA analysis
```

**Documentation**: https://platform.openai.com/docs/

---

### 4. GitHub Copilot (OpenAI-Compatible)

If you already have GitHub Copilot Pro subscription ($20/month), you get access to OpenAI models!

**Setup Steps:**

1. Get GitHub Personal Access Token:
   - Go to [github.com/settings/tokens](https://github.com/settings/tokens)
   - Click **Generate new token (classic)**
   - Check ✅ `read:user` scope
   - Copy the token

2. In FTA Editor AI Settings:
   - **Provider**: Select "OpenAI" (GitHub uses OpenAI-compatible API)
   - **API Key**: Paste your GitHub token
   - **Endpoint**: https://api.github.com/v1 or your GitHub Models endpoint
   - **Model**: Check available models in your GitHub account
   
3. Click **Test & Save**

**Cost**: Already covered by your GitHub Copilot subscription ($20/month)

---

## Switching Between Providers

You can switch providers at any time:

1. Click the **⚙ (Settings)** button in AI Assistant panel
2. Select a different provider from the provider list
3. Endpoint and model options update automatically
4. Enter API key for the new provider
5. Click **Test & Save**

Your credentials are stored on your computer only. One provider's credentials are kept at a time: saving a new provider replaces the previous key.

---

## Troubleshooting

### "Connection failed" message

**For Gemini:**
- Ensure you're using the correct API key format (looks like: `AIzaSy...`)
- Check that the API is enabled in your Google Cloud project
- Verify you have internet connectivity to generativelanguage.googleapis.com

**For Claude:**
- Ensure API key starts with `sk-ant-`
- Check that billing is set up and account is in good standing
- Verify you have internet connectivity to api.anthropic.com

**For OpenAI:**
- Ensure API key starts with `sk-`
- Check that you have active billing and usage limits
- Verify you have internet connectivity to api.openai.com

### Model not found error

- Some models may not be available in all regions
- Try a different model from the dropdown list
- Check provider documentation for available models in your region

### Rate limiting

If you hit rate limits:
- **Gemini**: Free tier limited to 15 requests/minute
- **Claude**: Check your account plan limits
- **OpenAI**: Check your usage dashboard

### API key exposed (Security)

If you accidentally shared your API key:

1. **Immediately revoke it** in your provider's console
2. Delete FTA Editor credentials: Click **Clear** in Settings
3. Generate a new API key
4. Reconfigure in FTA Editor

---

## Cost Optimization Tips

### 1. Start with Free Tier
- Use Gemini free tier first (15 req/min)
- Test your FTA workflows
- Upgrade to paid only if needed

### 2. Choose Right Model
- For simple analysis: Use cheaper models (GPT-3.5, Claude Haiku)
- For complex analysis: Use better models (GPT-4o, Claude Sonnet)
- Typical FTA analysis: GPT-3.5-turbo is usually sufficient

### 3. Set Usage Limits
- OpenAI: Set monthly budget limit in Settings
- Anthropic: Check billing settings for alerts
- Google: Free tier has built-in limits

### 4. Batch Your Analysis
- Combine multiple questions in one chat session
- Reduces overhead and tokens

### 5. Monitor Usage
- Check your provider's dashboard regularly
- OpenAI: Dashboard → Usage section
- Anthropic: Console → Usage section
- Google: Google Cloud Console → Billing

---

## Recommended Configurations

### Scenario 1: Budget-Conscious (Learning/Testing)
```
Provider: Google Gemini
Model: gemini-2.5-flash
Cost: Free (with limitations)
Best for: Learning, testing, simple analysis
```

### Scenario 2: Regular Use (Small Team)
```
Provider: Google Gemini (free) + OpenAI backup
Model: gemini-2.5-flash → gpt-3.5-turbo
Cost: ~$2-5/month
Best for: Regular FTA analysis, small engineering teams
```

### Scenario 3: Professional Use (Complex Analysis)
```
Provider: OpenAI or Claude
Model: gpt-4o or claude-sonnet-5
Cost: ~$10-30/month
Best for: Complex analyses, professional engineering work
```

### Scenario 4: High-Volume Analysis
```
Provider: Claude with volume discount
Model: claude-sonnet-5
Cost: Contact Anthropic for volume pricing
Best for: Enterprise, large teams, continuous analysis
```

---

## API Key Security Best Practices

1. **Never commit keys to repository**: Keys are stored in `~/.fta_editor/ai_credentials.json`
2. **Regenerate if exposed**: Delete old key, create new one in provider console
3. **Use minimal scopes**: Only grant necessary permissions (e.g., read:user for GitHub)
4. **Set usage limits**: Enable billing alerts and limits in provider dashboard
5. **Regular rotation**: Consider rotating keys every 6 months for security

---

## Additional Resources

- **Google Gemini**: https://ai.google.dev
- **Anthropic Claude**: https://www.anthropic.com/
- **OpenAI**: https://openai.com/
- **FTA Editor GitHub**: https://github.com/Gertrud-Violett/FTA_Editor
- **General Pricing Comparison**: https://www.artificial-intelligence.io/ai-pricing/

---

## Support

Having issues? 

1. Check this guide first (common solutions above)
2. Review your provider's documentation
3. Open an issue on GitHub: https://github.com/Gertrud-Violett/FTA_Editor/issues
4. Include:
   - Which provider you're using
   - Exact error message
   - What you were trying to do
