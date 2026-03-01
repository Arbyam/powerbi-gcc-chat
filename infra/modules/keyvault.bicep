param name string
param location string
param tags object = {}
param secrets array = []

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

resource kvSecrets 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = [
  for secret in secrets: {
    parent: keyVault
    name: secret.name
    properties: { value: secret.value }
  }
]

output name string = keyVault.name
output uri string = keyVault.properties.vaultUri
