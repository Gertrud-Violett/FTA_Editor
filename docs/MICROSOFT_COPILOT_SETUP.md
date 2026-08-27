# Microsoft Copilot (Azure OpenAI) Setup Guide

**Version**: 1.5.0 | **Updated**: December 17, 2025

Complete guide for setting up Microsoft Copilot / Azure OpenAI with the FTA Editor.

## Overview

Microsoft Copilot for enterprises uses **Azure OpenAI Service**, which provides:
- GPT-4, GPT-4o, GPT-4-turbo, and GPT-3.5-turbo models
- Enterprise-grade security and compliance
- Data privacy (your data stays in your Azure subscription)
- OpenAI-compatible API that works with FTA Editor

## Prerequisites

1. **Microsoft Account** - Microsoft 365 or Azure subscription
2. **Azure OpenAI Access** - One of:
   - **Azure OpenAI Service** - For enterprises ($$$)
   - **Microsoft Copilot for Microsoft 365** - For individual/business users ($30/user/month)
3. **Azure Portal Access** - To create resources and get API keys
4. **Internet Connection** - Required to access Azure APIs

## Option 1: Azure OpenAI Service (Recommended for Enterprises)

### Step 1: Create Azure OpenAI Resource

1. **Go to Azure Portal**:
   - Navigate to [portal.azure.com](https://portal.azure.com/)
   - Sign in with your Microsoft account

2. **Create Azure OpenAI Resource**:
   - Click **"Create a resource"**
   - Search for **"Azure OpenAI"**
   - Click **"Create"**

3. **Configure Resource**:
   - **Subscription**: Select your Azure subscription
   - **Resource Group**: Create new or select existing
   - **Region**: Choose closest region (e.g., East US, West Europe)
   - **Name**: Give it a unique name (e.g., `my-fta-openai`)
   - **Pricing Tier**: Select Standard S0
   - Click **"Review + Create"** → **"Create"**

4. **Wait for Deployment**:
   - Takes 2-5 minutes
   - Click **"Go to resource"** when ready

### Step 2: Deploy a Model

1. **Navigate to Azure OpenAI Studio**:
   - In your resource, click **"Go to Azure OpenAI Studio"**
   - Or visit: https://oai.azure.com/

2. **Create Deployment**:
   - Click **"Deployments"** in left sidebar
   - Click **"Create new deployment"**
   - Configure:
     - **Model**: Select `gpt-4o` (recommended) or `gpt-4-turbo`
     - **Deployment name**: `gpt-4o-deployment` (remember this!)
     - **Deployment type**: Standard
   - Click **"Create"**

3. **Note Your Deployment Name**:
   - You'll need this for the FTA Editor configuration
   - Example: `gpt-4o-deployment`

### Step 3: Get API Key and Endpoint

1. **Go Back to Azure Portal**:
   - Navigate to your Azure OpenAI resource

2. **Find Keys and Endpoint**:
   - Click **"Keys and Endpoint"** in left sidebar
   - You'll see:
     - **KEY 1**: Your API key (click "Show" to reveal)
     - **Endpoint**: Your base URL (e.g., `https://my-fta-openai.openai.azure.com/`)

3. **Copy Credentials**:
   - **API Key**: Copy KEY 1 (or KEY 2)
   - **Endpoint**: Copy the full endpoint URL
   - **Deployment Name**: Your deployment name from Step 2

### Step 4: Configure FTA Editor

1. **Build Full Endpoint URL**:
   ```
   Format: https://{resource-name}.openai.azure.com/openai/deployments/{deployment-name}
   
   Example: https://my-fta-openai.openai.azure.com/openai/deployments/gpt-4o-deployment
   ```

2. **Launch FTA Editor**:
   ```bash
   python src/FTA_Editor_UI.py
   ```

3. **Open AI Settings**:
   - Click **⚙️ AI Settings** button in the AI Assistant panel

4. **Configure Provider**:
   - **Provider**: Select **"Microsoft Copilot"** from dropdown
   - **API Key**: Paste your Azure OpenAI API key
   - **API Endpoint**: Enter your full endpoint URL (with deployment name)
     - Example: `https://my-fta-openai.openai.azure.com/openai/deployments/gpt-4o-deployment`
   - **Model**: Enter your deployment name (e.g., `gpt-4o-deployment`)

5. **Test Connection**:
   - Click **"Test Connection"** button
   - Should see: ✅ "Microsoft Copilot (Azure OpenAI) connection successful!"

6. **Save Settings**:
   - Click **"Save"** button
   - Credentials stored locally at `~/.fta_editor/ai_credentials.json`

---

## Option 2: Microsoft Copilot for Microsoft 365

If you have **Microsoft Copilot for Microsoft 365**, you can access the API through your organization's Azure OpenAI endpoint.

### Steps:

1. **Contact Your IT Administrator**:
   - Request access to your organization's Azure OpenAI endpoint
   - Ask for:
     - API Key
     - Endpoint URL
     - Deployment name

2. **Use Provided Credentials**:
   - Follow Step 4 above with the credentials from your IT admin

---

## Configuration Examples

### Example 1: East US Region

```
Provider: Microsoft Copilot
API Key: 1234567890abcdef1234567890abcdef
API Endpoint: https://my-company-ai.openai.azure.com/openai/deployments/gpt-4o
Model: gpt-4o
```

### Example 2: Europe West Region

```
Provider: Microsoft Copilot
API Key: abcdef1234567890abcdef1234567890
API Endpoint: https://fta-editor-ai-eu.openai.azure.com/openai/deployments/gpt-4-turbo
Model: gpt-4-turbo
```

---

## Pricing

Azure OpenAI pricing is based on token usage:

| Model | Cost per 1K Input Tokens | Cost per 1K Output Tokens |
|-------|--------------------------|---------------------------|
| **GPT-4o** | $0.0025 | $0.010 |
| **GPT-4-turbo** | $0.010 | $0.030 |
| **GPT-4** | $0.030 | $0.060 |
| **GPT-3.5-turbo** | $0.0005 | $0.0015 |

**FTA Editor Usage Estimates**:
- Quick FTA analysis: ~1,000-2,000 tokens ≈ $0.01-0.03
- Root cause suggestions: ~800-1,500 tokens ≈ $0.005-0.02
- Monthly usage (heavy, 100 requests): ~$2-6

**Enterprise Benefits**:
- Data stays in your Azure subscription
- SOC 2, ISO 27001, HIPAA compliance
- No training on your data
- Advanced security features

---

## Troubleshooting

### "Deployment error: Check your deployment name"

**Problem**: Incorrect deployment name in endpoint URL

**Solution**:
1. Go to Azure OpenAI Studio → Deployments
2. Verify your deployment name (case-sensitive!)
3. Update endpoint URL: `https://{resource}.openai.azure.com/openai/deployments/{exact-deployment-name}`

### "Authentication failed: Check your API key"

**Problem**: Invalid or expired API key

**Solutions**:
1. Go to Azure Portal → Your resource → Keys and Endpoint
2. Copy KEY 1 or KEY 2 (click "Show")
3. If keys are regenerated, update FTA Editor settings

### "Endpoint not found: Verify your Azure resource URL"

**Problem**: Incorrect resource name in endpoint

**Solutions**:
1. Go to Azure Portal → Your OpenAI resource
2. Check the endpoint URL in "Keys and Endpoint"
3. Format should be: `https://{your-resource-name}.openai.azure.com/`
4. Ensure no typos in resource name

### "Rate limit exceeded"

**Problem**: Too many requests in short time

**Solutions**:
1. Azure OpenAI has rate limits per deployment
2. Wait a few minutes and try again
3. Upgrade to higher tier (Standard S0 → higher quota)
4. Contact Azure support to increase quota

### "Model not found" or "Invalid model"

**Problem**: Model name doesn't match deployment name

**Solution**:
- In FTA Editor, the **Model** field should match your **Deployment Name**, not the underlying model
- Example: If you named your deployment `my-gpt4`, use `my-gpt4` (not `gpt-4`)

---

## Security Best Practices

1. **Protect API Keys**:
   - Never commit keys to git repositories
   - Don't share keys in emails or messages
   - Rotate keys periodically (regenerate in Azure Portal)

2. **Use Azure RBAC**:
   - Assign minimal permissions (Cognitive Services OpenAI User)
   - Use service principals for production

3. **Monitor Usage**:
   - Check Azure Portal → Cost Management
   - Set up budget alerts
   - Review audit logs

4. **Network Security**:
   - Use Azure Private Link for production
   - Configure firewall rules
   - Enable managed identity

---

## Comparison: Microsoft Copilot vs Others

| Feature | Microsoft Copilot (Azure) | OpenAI Direct | Google Gemini |
|---------|---------------------------|---------------|---------------|
| **Data Privacy** | ✅ Stays in your Azure | ❌ Sent to OpenAI | ❌ Sent to Google |
| **Compliance** | ✅ SOC 2, HIPAA, ISO | ⚠️ Limited | ⚠️ Limited |
| **Cost** | $$$ Higher | $$ Moderate | $ Lower (free tier) |
| **Setup Complexity** | ⚠️ Moderate | ✅ Easy | ✅ Easy |
| **Enterprise Features** | ✅ Full | ❌ Limited | ❌ Limited |
| **Best For** | Enterprises, regulated industries | Individuals, startups | Testing, light use |

---

## Getting Help

**Azure OpenAI Issues**:
- [Azure OpenAI Documentation](https://learn.microsoft.com/azure/ai-services/openai/)
- [Azure Support Portal](https://portal.azure.com/#blade/Microsoft_Azure_Support/HelpAndSupportBlade)
- [Azure OpenAI Forum](https://learn.microsoft.com/answers/tags/387/azure-openai)

**FTA Editor Issues**:
- [GitHub Issues](https://github.com/Gertrud-Violett/FTA_editor/issues)
- Check README.md troubleshooting section

---

## Summary Checklist

- [ ] Create Azure OpenAI resource in Azure Portal
- [ ] Deploy GPT-4o or GPT-4-turbo model
- [ ] Get API key and endpoint from Azure Portal
- [ ] Build full endpoint URL with deployment name
- [ ] Configure FTA Editor with Microsoft Copilot provider
- [ ] Test connection successfully
- [ ] Start using AI assistant for FTA analysis!

**Estimated setup time**: 15-20 minutes

Once configured, Microsoft Copilot provides enterprise-grade AI analysis for your fault trees with full data privacy and compliance!
