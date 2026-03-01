targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment (e.g., dev, staging, prod)')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Cloud environment: commercial, gcc, or gcchigh')
@allowed(['commercial', 'gcc', 'gcchigh'])
param cloudEnvironment string = 'commercial'

@description('Power BI tenant ID')
param tenantId string = ''

@description('Power BI service principal client ID')
param clientId string = ''

@secure()
@description('Power BI service principal client secret')
param clientSecret string = ''

@description('Azure OpenAI model deployment name')
param openaiDeploymentName string = 'gpt-4o'

@description('Azure OpenAI model name')
param openaiModelName string = 'gpt-4o'

@description('Azure OpenAI model version')
param openaiModelVersion string = '2024-11-20'

// --- Resource Group ---
var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// --- Log Analytics ---
module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'log-analytics'
  scope: rg
  params: {
    name: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    location: location
    tags: tags
  }
}

// --- Container Registry ---
module containerRegistry 'modules/container-registry.bicep' = {
  name: 'container-registry'
  scope: rg
  params: {
    name: '${abbrs.containerRegistryRegistries}${resourceToken}'
    location: location
    tags: tags
  }
}

// --- Azure OpenAI ---
module openai 'modules/openai.bicep' = {
  name: 'openai'
  scope: rg
  params: {
    name: '${abbrs.cognitiveServicesAccounts}${resourceToken}'
    location: location
    tags: tags
    deploymentName: openaiDeploymentName
    modelName: openaiModelName
    modelVersion: openaiModelVersion
  }
}

// --- Key Vault ---
module keyVault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  scope: rg
  params: {
    name: '${abbrs.keyVaultVaults}${resourceToken}'
    location: location
    tags: tags
    secrets: [
      { name: 'powerbi-client-secret', value: clientSecret }
      { name: 'openai-key', value: openai.outputs.key }
    ]
  }
}

// --- Container Apps Environment ---
module containerAppsEnv 'modules/container-apps-env.bicep' = {
  name: 'container-apps-env'
  scope: rg
  params: {
    name: '${abbrs.appManagedEnvironments}${resourceToken}'
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logAnalytics.outputs.id
  }
}

// --- Backend Container App ---
module backend 'modules/container-app.bicep' = {
  name: 'backend'
  scope: rg
  params: {
    name: '${abbrs.appContainerApps}backend-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'backend' })
    containerAppsEnvironmentId: containerAppsEnv.outputs.id
    containerRegistryName: containerRegistry.outputs.name
    imageName: 'backend'
    targetPort: 8000
    env: [
      { name: 'CLOUD_ENVIRONMENT', value: cloudEnvironment }
      { name: 'TENANT_ID', value: tenantId }
      { name: 'CLIENT_ID', value: clientId }
      { name: 'CLIENT_SECRET', secretRef: 'powerbi-client-secret' }
      { name: 'AZURE_OPENAI_ENDPOINT', value: openai.outputs.endpoint }
      { name: 'AZURE_OPENAI_KEY', secretRef: 'openai-key' }
      { name: 'AZURE_OPENAI_DEPLOYMENT', value: openaiDeploymentName }
      { name: 'ENABLE_PII_DETECTION', value: 'true' }
      { name: 'ENABLE_AUDIT', value: 'true' }
      { name: 'LOG_LEVEL', value: 'INFO' }
    ]
    secrets: [
      { name: 'powerbi-client-secret', value: clientSecret }
      { name: 'openai-key', value: openai.outputs.key }
    ]
  }
}

// --- Frontend Container App ---
module frontend 'modules/container-app.bicep' = {
  name: 'frontend'
  scope: rg
  params: {
    name: '${abbrs.appContainerApps}frontend-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'frontend' })
    containerAppsEnvironmentId: containerAppsEnv.outputs.id
    containerRegistryName: containerRegistry.outputs.name
    imageName: 'frontend'
    targetPort: 80
    env: []
    secrets: []
  }
}

// --- Outputs ---
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer
output AZURE_OPENAI_ENDPOINT string = openai.outputs.endpoint
output BACKEND_URL string = backend.outputs.fqdn
output FRONTEND_URL string = frontend.outputs.fqdn
output RESOURCE_GROUP string = rg.name
