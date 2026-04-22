// Bicep IaC for the macro oil terminal stack.
//
// Captures the full live topology so the whole thing can be reproduced
// from scratch in one command. Existing resources (created via earlier
// `az` commands) are referenced by name with `existing:` where possible
// so a deploy against the same RG is idempotent.
//
// Deploy:
//   bash infra/deploy.sh
// or
//   az deployment group create \
//     -g oil-price-tracker -f infra/main.bicep \
//     -p appServicePlanName=oil-tracker-plan-westus2 \
//        webAppName=oil-tracker-app-4281 \
//        aoaiAccountName=oil-tracker-aoai \
//        aiComponentName=oil-tracker-ai \
//        actionGroupName=oil-tracker-alerts \
//        alertEmail=aidan.marshall@Youbiquity.com
//
// NOTE: This file is intentionally non-destructive. It does not delete
// anything that's already there. Review `what-if` output before running.

@description('Azure region for the App Service plan + Web App.')
param planLocation string = 'westus2'

@description('Region for Azure OpenAI (gpt-4o-mini GlobalStandard availability).')
param openAiLocation string = 'eastus'

@description('App Service plan name.')
param appServicePlanName string = 'oil-tracker-plan-westus2'

@description('Web App name (globally unique).')
param webAppName string = 'oil-tracker-app-4281'

@description('Azure OpenAI account name.')
param aoaiAccountName string = 'oil-tracker-aoai'

@description('Azure OpenAI custom subdomain (defaults to account name).')
param aoaiCustomDomain string = 'oil-tracker-aoai'

@description('Application Insights component name.')
param aiComponentName string = 'oil-tracker-ai'

@description('Name of the action group that fans out alerts.')
param actionGroupName string = 'oil-tracker-alerts'

@description('Destination email address for alerts.')
param alertEmail string

@description('Python runtime for the web app.')
param pythonRuntime string = 'PYTHON|3.11'

@description('Streamlit startup command.')
param startupCommand string = 'python -m streamlit run app.py --server.port 8000 --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false'


// -------- App Service plan (Linux F1) --------
resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: appServicePlanName
  location: planLocation
  sku: {
    name: 'F1'
    tier: 'Free'
    capacity: 1
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}


// -------- Application Insights (workspace-less classic) --------
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: aiComponentName
  location: planLocation
  kind: 'web'
  properties: {
    Application_Type: 'web'
    IngestionMode: 'ApplicationInsights'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}


// -------- Azure OpenAI account --------
resource aoai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: aoaiAccountName
  location: openAiLocation
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: aoaiCustomDomain
    publicNetworkAccess: 'Enabled'
  }
}

// gpt-4o-mini deployment (GlobalStandard, capacity 10)
resource gpt4oMini 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aoai
  name: 'gpt-4o-mini'
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini'
      version: '2024-07-18'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}


// -------- Web App (Linux, Python 3.11, Streamlit) --------
resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: webAppName
  location: planLocation
  kind: 'app,linux'
  properties: {
    serverFarmId: plan.id
    siteConfig: {
      linuxFxVersion: pythonRuntime
      appCommandLine: startupCommand
      webSocketsEnabled: true
      alwaysOn: false  // F1 doesn't support always-on
      ftpsState: 'Disabled'
      http20Enabled: true
      minTlsVersion: '1.2'
    }
    httpsOnly: true
  }
}

resource webAppAppSettings 'Microsoft.Web/sites/config@2023-12-01' = {
  parent: webApp
  name: 'appsettings'
  properties: {
    SCM_DO_BUILD_DURING_DEPLOYMENT: 'true'
    ENABLE_ORYX_BUILD: 'true'
    WEBSITES_PORT: '8000'
    APPLICATIONINSIGHTS_CONNECTION_STRING: appInsights.properties.ConnectionString
    AZURE_OPENAI_ENDPOINT: 'https://${aoaiCustomDomain}.openai.azure.com/'
    AZURE_OPENAI_KEY: aoai.listKeys().key1
    AZURE_OPENAI_API_VERSION: '2024-10-21'
    AZURE_OPENAI_DEPLOYMENT: 'gpt-4o-mini'
  }
}


// -------- Action group (email fan-out) --------
resource actionGroup 'Microsoft.Insights/actionGroups@2023-09-01-preview' = {
  name: actionGroupName
  location: 'Global'
  properties: {
    groupShortName: 'oilalrt'
    enabled: true
    emailReceivers: [
      {
        name: 'aidan-alert'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}


// -------- Alert rule: HTTP 5xx > 5 in 5m --------
resource alertHttp5xx 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'oil-tracker-http5xx'
  location: 'global'
  properties: {
    description: 'HTTP 5xx responses > 5 in any 5-minute window'
    severity: 2
    enabled: true
    scopes: [ webApp.id ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'Http5xx'
          metricName: 'Http5xx'
          metricNamespace: 'Microsoft.Web/sites'
          operator: 'GreaterThan'
          threshold: 5
          timeAggregation: 'Total'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}


// -------- Alert rule: slow response avg > 5s --------
resource alertSlow 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'oil-tracker-slow-response'
  location: 'global'
  properties: {
    description: 'Average HTTP response time > 5s over 5 minutes'
    severity: 3
    enabled: true
    scopes: [ webApp.id ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'HttpResponseTime'
          metricName: 'HttpResponseTime'
          metricNamespace: 'Microsoft.Web/sites'
          operator: 'GreaterThan'
          threshold: 5
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}


output webAppHost string = webApp.properties.defaultHostName
output aoaiEndpoint string = 'https://${aoaiCustomDomain}.openai.azure.com/'
output aiConnectionString string = appInsights.properties.ConnectionString
