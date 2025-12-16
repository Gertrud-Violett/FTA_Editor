# GitHub Copilot / GitHub Models Setup Guide for FTA Editor

**Version**: 1.5.0 | **Updated**: December 16, 2025

Complete guide for setting up GitHub Copilot (GitHub Models API) with the FTA Editor.

## What is GitHub Models?

GitHub Models is an AI inference service that comes with your **GitHub Copilot subscription**. It provides:
- Access to GPT-4o, GPT-4o-mini, and other AI models
- OpenAI-compatible API that works with the FTA Editor
- Included with your Copilot subscription (no extra cost)
- Text generation, analysis, and problem-solving

The FTA Editor uses GitHub Models to analyze fault trees and suggest improvements.

## Prerequisites

1. **GitHub Account** - Free account at [github.com](https://github.com)
2. **GitHub Copilot Subscription** - One of:
   - **Copilot Free** - Limited monthly usage (requires waitlist)
   - **GitHub Copilot Pro** - $20/month, unlimited usage
   - **GitHub Copilot for Individuals** - As part of GitHub Pro ($4/month)
   - **GitHub Copilot for Business/Enterprise** - Through your organization

3. **Internet Connection** - Required to access Copilot API

## Step-by-Step Setup

### 1. Verify GitHub Copilot Subscription

First, check if you have Copilot access:

1. Go to [github.com](https://github.com)
2. Click your **profile icon** (top right)
3. Select **Settings**
4. Click **Billing and plans** (left sidebar)
5. Look for **Copilot** section
6. Verify it shows "Active" or "Enabled"

If you don't have Copilot:
- Click **"Enable Copilot"** or **"Upgrade"**
- Choose your plan and complete the payment
- Wait for activation (usually instant, up to 24 hours)

### 2. Create GitHub Personal Access Token

The FTA Editor needs a Personal Access Token to authenticate with GitHub's API.

**Steps**:

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
   - Or: Settings → Developer settings → Personal access tokens → Tokens (classic)

2. Click **"Generate new token (classic)"** button

3. Fill in the token details:
   - **Token name**: `FTA Editor` (or any descriptive name)
   - **Expiration**: Set to **90 days** (or longer if preferred)
   - **Scopes**: Select at minimum:
     - ✅ `read:user` - To read your profile
     - ✅ `user:email` - To verify your email (optional)
     - Optionally: `repo` - For full repository access

4. Scroll down and click **"Generate token"**

5. **IMPORTANT**: Copy the token immediately and save it somewhere secure
   - GitHub will never show it again
   - You'll need this for the FTA Editor

**Token Format**: Your token should look like: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### 3. Configure FTA Editor

Now configure the FTA Editor to use GitHub Models:

1. **Launch FTA Editor**:
   ```bash
   python src/FTA_Editor_UI.py
   ```

2. **Open AI Settings**:
   - Look at the right panel (AI Assistant)
   - Click **⚙️ AI Settings** button

3. **Enter Credentials**:
   - **API Key**: Paste your Personal Access Token from Step 2
     - Example: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   
   - **API Endpoint**: Enter this exactly:
     ```
     https://models.github.ai
     ```
   
   - **Model**: Choose one of:
     - `gpt-4o` (recommended - best quality)
     - `gpt-4o-mini` (faster, lower cost)
     - `gpt-4` (alternative)

4. **Test Connection**:
   - Click **Test Connection** button
   - You should see: ✅ "Connection successful!"
   - If you see an error, verify your token and endpoint

5. **Save Settings**:
   - Click **Save** to store your credentials
   - Credentials are saved locally to: `~/.fta_editor/ai_credentials.json`
   - This file is outside your repository and won't be committed
### 4. Test the Connection

Once configured, test that everything works:

1. Click **"Analyze FTA"** button in the AI Assistant panel
2. Watch the chat display for the AI response
3. The AI should provide an analysis of your current FTA

## Using GitHub Copilot with FTA Editor

### Quick Actions

**Analyze FTA**:
- Provides comprehensive analysis of your fault tree
- Suggests missing elements
- Identifies potential improvements
- Click anywhere to start using it

**Suggest Root Causes**:
- Select a node in the tree
- Click "Suggest Root Causes"
- AI suggests additional failure modes for that node

**Free Chat**:
- Type any question in the chat input box
- Press `Enter` to send
- Great for detailed questions about your analysis

### Example Prompts

**Analysis questions**:
- "What root causes are missing from this pump failure?"
- "Can you review the probabilities in this tree?"
- "What safety factors should I consider?"

**Improvement suggestions**:
- "Are there any common failure modes I've missed?"
- "How could I improve this analysis?"
- "What are industry best practices for this system?"

**Technical questions**:
- "How should I calculate probabilities for this component?"
- "What's the difference between AND and OR gates here?"
- "How reliable is this design?"

## Cost Considerations

### GitHub Copilot / GitHub Models Pricing

GitHub Models is **included** with your GitHub Copilot subscription at no extra cost!

| Plan | Cost | Usage Limits | Best For |
|------|------|--------------|----------|
| **Copilot Free** | Free | Rate limited | Testing, light use |
| **Copilot Individual** | $10/month | Higher limits | Personal projects |
| **Copilot Business** | $19/user/month | Highest limits | Teams and organizations |

**FTA Editor Usage Estimates**:
- Quick FTA analysis: ~1,000-2,000 tokens per request
- Root cause suggestions: ~800-1,500 tokens per request
- Average user: ~50-200 requests/month
- All included in your Copilot subscription!

### Usage Estimation

For FTA Editor:
- **Quick analysis**: ~1,000 tokens
- **Suggest root causes**: ~800 tokens
- **Free chat questions**: ~500-2,000 tokens depending on detail

A GitHub Copilot Pro subscription ($20/month) provides essentially unlimited usage.

## Troubleshooting

### "Connection failed" Error

**Problem**: Test & Save fails

**Solutions**:
1. **Verify token is active**:
   - Go to [github.com/settings/tokens](https://github.com/settings/tokens)
   - Check that your token hasn't expired
   - If expired, regenerate a new one

2. **Check internet connection**:
   - Test: `ping github.com`
   - If fails, check your network

3. **Verify Copilot is active**:
   - Go to Settings → Billing and plans
   - Confirm Copilot shows "Active"

4. **Check endpoint and token format**:
   - Endpoint should be: `https://api.github.com` (exactly)
   - Token should start with: `ghp_`

### "API Key is invalid" Error

**Problem**: Credentials are rejected

**Solutions**:
1. **Regenerate your token**:
   - Go to [github.com/settings/tokens](https://github.com/settings/tokens)
   - Delete the old token
   - Click "Generate new token (classic)"
   - Copy the new token immediately
   - Update the FTA Editor settings

2. **Verify scopes**:
   - Token must have at least `read:user` scope
   - Check the token's permissions

### "Slow responses" Issue

**Problem**: AI takes a long time to respond

**Solutions**:
1. **Use a faster model**:
   - Try `gpt-4o-mini` instead of `gpt-4-turbo`
   - Less capable but faster

2. **Check network**:
   - Test: `ping github.com`
   - Look for high latency

3. **Retry the request**:
   - Sometimes API is busy
   - Try again after a few seconds

### "Rate limit exceeded" Error

**Problem**: Too many API calls in short time

**Solutions**:
1. **Wait a few minutes** - Rate limits reset automatically
2. **Upgrade to GitHub Copilot Pro** - Higher rate limits
3. **Use smaller/faster models** - `gpt-4o-mini` has higher limits

## Security Best Practices

1. **Keep Token Secret**:
   - Don't share your token in emails or messages
   - Don't commit it to repositories
   - Treat it like a password

2. **Token Expiration**:
   - Set tokens to expire in 90 days
   - Regenerate periodically

3. **Revoke When Done**:
   - If you stop using FTA Editor with Copilot
   - Go to tokens page and click "Delete"

4. **Monitor Usage**:
   - GitHub emails you token activity
   - Report suspicious activity immediately

## Alternatives to GitHub Copilot

If GitHub Copilot isn't right for you, the FTA Editor supports:

### OpenAI API
- Direct access to GPT-4o, GPT-4-turbo
- $0.005-0.030 per 1K tokens (pay-as-you-go)
- No subscription required, just add credits
- Setup: [openai.com/api](https://platform.openai.com/)

### Azure OpenAI
- Same models as OpenAI
- Integrated with Microsoft Azure ecosystem
- For enterprise customers
- Setup: [azure.microsoft.com/openai](https://azure.microsoft.com/services/cognitive-services/openai-service/)

### Local LLM Servers
- Use open-source models (Llama, Mistral, etc.)
- Free, runs on your computer
- No API costs
- Lower performance than commercial APIs
- Tools: Ollama, LLaMA.cpp, LocalAI

## Getting Help

**Issues with GitHub Copilot**:
- [GitHub Copilot Support](https://support.github.com/contact/copilot)
- [GitHub Community Discussions](https://github.com/orgs/community/discussions)

**Issues with FTA Editor**:
- [FTA Editor GitHub Issues](https://github.com/Gertrud-Violett/FTA_editor/issues)
- Check README.md for troubleshooting

**GitHub Status**:
- Check [githubstatus.com](https://www.githubstatus.com/) if services are down

## Summary

| Step | Action | Time |
|------|--------|------|
| 1 | Verify Copilot subscription | 2 min |
| 2 | Create Personal Access Token | 3 min |
| 3 | Configure FTA Editor | 2 min |
| 4 | Test connection | 1 min |
| **Total** | **Setup complete** | **~8 minutes** |

### Quick Reference Card

```
API Endpoint: https://models.github.ai
API Key: Your GitHub Personal Access Token (ghp_...)
Model: gpt-4o (recommended) or gpt-4o-mini
```

Once set up, you can use GitHub Models (powered by your Copilot subscription) to enhance your fault tree analyses!
