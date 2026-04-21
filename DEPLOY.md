# Deployment — GitHub & Azure

The autonomous build session could not complete Phase 6 end-to-end: the
agent sandbox does not have the `gh` or `az` CLIs installed, and by
design we do not install host-level CLIs or prompt for credentials
silently. This file captures the exact commands you need to run on your
Mac.

Project directory on disk:
```
/Users/aidanbothost/Documents/macro_oil_terminal
```

### One-time cleanup before the first `git init` on your Mac

During the autonomous build the sandbox tried to run `git init` against
the mounted `Documents` folder and Apple sandboxing blocked subsequent
writes to some `.git` internal files. The result is a half-initialised
`.git/` directory that needs to be removed on the **host** (your Mac —
Finder or Terminal have full permission):

```bash
cd /Users/aidanbothost/Documents/macro_oil_terminal
rm -rf .git __pycache__ .venv
```

Then one of the following:

**Option A — start fresh (recommended):**
```bash
git init -b main
git add -A
git commit -m "Initial commit: Inventory-Adjusted Spread Arbitrage & AIS Fleet Analytics"
```

**Option B — restore from the pre-built bundle the agent produced:**
The agent wrote a git bundle containing the exact commit it tried to
make in-session. Find it at the outputs link in the chat (file name
`macro-oil-terminal.bundle`). Then:
```bash
cd /Users/aidanbothost/Documents
mv macro_oil_terminal macro_oil_terminal.backup
git clone /path/to/macro-oil-terminal.bundle macro_oil_terminal
cd macro_oil_terminal
```


---

## 1. GitHub

### Preflight
```bash
gh --version
gh auth status
```

If `gh` is not installed:
```bash
brew install gh
gh auth login   # pick GitHub.com -> HTTPS -> browser
```

### Create the remote and push
```bash
cd /Users/aidanbothost/Documents/macro_oil_terminal

# Create a new PUBLIC repo under your account and push main in one go
gh repo create macro-oil-terminal \
  --public \
  --source=. \
  --remote=origin \
  --push \
  --description "Inventory-Adjusted Spread Arbitrage & AIS Fleet Analytics — Streamlit + Plotly + Three.js WebGPU"
```

If you prefer a private repo, swap `--public` for `--private`.

### Manual fallback (no gh)
```bash
# From github.com, click "New repo", name it macro-oil-terminal, no README.
cd /Users/aidanbothost/Documents/macro_oil_terminal
git branch -M main
git remote add origin https://github.com/<your-username>/macro-oil-terminal.git
git push -u origin main
```

---

## 2. Azure

Tenant target: **youbiquity**. Resource group name: **oil-price-tracker**.
Region suggestion: `eastus` (change if you have a preferred region).

### Preflight
```bash
az --version
az account show
```

If `az` is not installed:
```bash
brew install azure-cli
az login --tenant youbiquity   # or the tenant GUID
az account set --subscription "<SUBSCRIPTION_ID_IN_YOUBIQUITY>"
```

### Resource group
```bash
az group create \
  --name oil-price-tracker \
  --location eastus
```

### App Service plan + Web App (Linux, Python 3.11)
```bash
# Plan — B1 is fine for dev; scale up later
az appservice plan create \
  --name oil-price-tracker-plan \
  --resource-group oil-price-tracker \
  --sku B1 \
  --is-linux

# Web App (give it a globally unique name)
APP_NAME="oil-price-tracker-$RANDOM"
az webapp create \
  --resource-group oil-price-tracker \
  --plan oil-price-tracker-plan \
  --name "$APP_NAME" \
  --runtime "PYTHON|3.11"

# Tell App Service to start Streamlit on $PORT
az webapp config set \
  --resource-group oil-price-tracker \
  --name "$APP_NAME" \
  --startup-file "python -m streamlit run app.py --server.port=\$PORT --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"

# Enable build on deploy so requirements.txt gets installed
az webapp config appsettings set \
  --resource-group oil-price-tracker \
  --name "$APP_NAME" \
  --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true ENABLE_ORYX_BUILD=true

echo "App URL: https://$APP_NAME.azurewebsites.net"
```

### Deploy the code (after the GitHub push)

Cleanest path — connect the GitHub repo:
```bash
az webapp deployment source config \
  --name "$APP_NAME" \
  --resource-group oil-price-tracker \
  --repo-url "https://github.com/<your-username>/macro-oil-terminal" \
  --branch main \
  --manual-integration
```

Or push a zip directly:
```bash
cd /Users/aidanbothost/Documents/macro_oil_terminal
zip -r /tmp/macro-oil-terminal.zip . -x "*.venv*" "*.git*" "__pycache__/*"
az webapp deploy \
  --resource-group oil-price-tracker \
  --name "$APP_NAME" \
  --src-path /tmp/macro-oil-terminal.zip \
  --type zip
```

> **Note:** Streamlit long-lived websockets need the App Service "Always On"
> setting and Web Sockets enabled. The B1 plan supports Always On:
> ```bash
> az webapp config set --resource-group oil-price-tracker --name "$APP_NAME" --always-on true --web-sockets-enabled true
> ```

### LLM backend — Azure OpenAI (preferred) or Cognitive Services

#### Attempt Azure OpenAI first
```bash
az cognitiveservices account create \
  --name oil-price-tracker-aoai \
  --resource-group oil-price-tracker \
  --kind OpenAI \
  --sku S0 \
  --location eastus \
  --yes

# If the command fails with a quota / policy error, the subscription
# most likely does not have Azure OpenAI approved.
```

#### Fallback — Azure AI Foundry / Cognitive Services multi-service
```bash
az cognitiveservices account create \
  --name oil-price-tracker-ai \
  --resource-group oil-price-tracker \
  --kind CognitiveServices \
  --sku S0 \
  --location eastus \
  --yes
```

#### Get the endpoint & key (do NOT commit the key)
```bash
az cognitiveservices account show \
  --name oil-price-tracker-aoai \
  --resource-group oil-price-tracker \
  --query properties.endpoint -o tsv

# Key lives in the "keys" endpoint — fetch on demand, don't paste into files
az cognitiveservices account keys list \
  --name oil-price-tracker-aoai \
  --resource-group oil-price-tracker \
  --query key1 -o tsv
```

Wire the key into the Web App as an app setting (not the repo):
```bash
ENDPOINT=$(az cognitiveservices account show --name oil-price-tracker-aoai --resource-group oil-price-tracker --query properties.endpoint -o tsv)
KEY=$(az cognitiveservices account keys list --name oil-price-tracker-aoai --resource-group oil-price-tracker --query key1 -o tsv)

az webapp config appsettings set \
  --resource-group oil-price-tracker \
  --name "$APP_NAME" \
  --settings AZURE_OPENAI_ENDPOINT="$ENDPOINT" AZURE_OPENAI_KEY="$KEY"
```

### Deploy a GPT model (if Azure OpenAI succeeded)
```bash
az cognitiveservices account deployment create \
  --name oil-price-tracker-aoai \
  --resource-group oil-price-tracker \
  --deployment-name gpt-4o-mini \
  --model-name gpt-4o-mini \
  --model-version "2024-07-18" \
  --model-format OpenAI \
  --sku-capacity 10 \
  --sku-name "Standard"
```

---

## Cleanup (if you decide not to ship)
```bash
az group delete --name oil-price-tracker --yes --no-wait
```

---

## TL;DR for Aidan

1. `cd /Users/aidanbothost/Documents/macro_oil_terminal`
2. `gh repo create macro-oil-terminal --public --source=. --remote=origin --push`
3. `az login --tenant youbiquity`
4. Paste the Azure block above, replacing `<SUBSCRIPTION_ID>` where needed.
