import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const client = await readFile(resolve(root, 'src/api/client.ts'), 'utf8');
const source = await readFile(resolve(root, 'src/api/dataExchange.ts'), 'utf8');
const dataExchangeScreen = await readFile(resolve(root, 'src/screens/more/DataExchangeScreen.tsx'), 'utf8');
const password = await readFile(resolve(root, 'src/screens/auth/PasswordChangeScreen.tsx'), 'utf8');
const workbench = await readFile(resolve(root, 'src/api/workbench.ts'), 'utf8');
const warehouse = await readFile(resolve(root, 'src/api/warehouse.ts'), 'utf8');
const pending = await readFile(resolve(root, 'src/screens/auth/PendingScreen.tsx'), 'utf8');
const navigation = await readFile(resolve(root, 'src/navigation/index.tsx'), 'utf8');
const apiModuleNames = [
  'auth.ts',
  'cost.ts',
  'dataExchange.ts',
  'feeding.ts',
  'masterData.ts',
  'ponds.ts',
  'production.ts',
  'purchase.ts',
  'sales.ts',
  'warehouse.ts',
  'workbench.ts',
];
const apiSource = (
  await Promise.all(apiModuleNames.map((name) => readFile(resolve(root, 'src/api', name), 'utf8')))
).join('\n');

assert.match(client, /process\.env\.EXPO_PUBLIC_API_BASE_URL/, 'API host must be configurable through Expo public env');
assert.doesNotMatch(client, /const BASE_URL = ['"]https:\/\/1\.14\.148\.15/, 'API host must not be hard-coded in the client');
assert.match(client, /await this\.ready/, 'requests must wait for persisted session state to load');

const contracts = [
  ['templates response reads data.items', /res\.data\.items/],
  ['template download uses /download', /templates\/\$\{templateCode\}\/download/],
  ['import preview uses /imports/preview', /\$\{BASE\}\/imports\/preview/],
  ['import preview includes organization_id', /organization_id/],
  ['import preview includes template_code', /template_code/],
  ['import preview includes file', /append\(['"]file['"]/],
  ['import confirm uses /imports/{id}/confirm', /\$\{BASE\}\/imports\/\$\{batchId\}\/confirm/],
  ['export uses POST /exports', /apiClient\.post[\s\S]*\$\{BASE\}\/exports/],
  ['export payload includes organization_id', /organization_id/],
  ['export payload includes resource', /resource/],
  ['export payload includes format', /format/],
  ['export payload includes filters', /filters/],
];

for (const [name, pattern] of contracts) {
  assert.match(source, pattern, name);
}

assert.match(password, /confirm_password/, 'password changes must use the backend confirmation field');
assert.doesNotMatch(password, /new_password_confirmation/, 'password changes must not use the obsolete confirmation field');
assert.match(workbench, /apiClient\.patch[\s\S]*work-items\/\$\{id\}/, 'work item transitions must use the backend patch route');
assert.match(workbench, /apiClient\.patch[\s\S]*notifications\/\$\{id\}/, 'notification updates must use the backend patch route');
assert.match(workbench, /const BASE = '\/api\/v1';/, 'work item routes must use the backend API prefix');
assert.match(workbench, /const SUMMARY_BASE = '\/api\/v1\/workbench';/, 'summary route must use the workbench prefix');
assert.match(warehouse, /res\.data\.items/, 'warehouse alerts must read data.items');
assert.match(warehouse, /alerts\/\$\{encodeURIComponent\(alertKey\)\}\/handle/, 'alert handling must include the alert key in the route');
assert.match(pending, /await refreshUser\(\)/, 'pending refresh must refresh the current user');
assert.match(navigation, /must_change_password/, 'forced password-change users must not enter business navigation');
assert.match(dataExchangeScreen, /expo-document-picker/, 'mobile data import must use the native document picker');
assert.match(dataExchangeScreen, /getDocumentAsync/, 'mobile data import must open a document picker');
assert.match(dataExchangeScreen, /previewImport/, 'mobile data import must preview through the API');
assert.match(dataExchangeScreen, /confirmImport/, 'mobile data import must confirm valid batches');
assert.match(dataExchangeScreen, /expo-file-system/, 'mobile exports must be persisted locally');
assert.match(dataExchangeScreen, /expo-sharing/, 'mobile exports must be shareable');
assert.match(dataExchangeScreen, /shareAsync/, 'mobile exports must invoke native sharing');
assert.match(dataExchangeScreen, /resource: template\.code/, 'mobile exports must use the backend template code as resource');

const requiredApiGroups = [
  '/api/v1/auth',
  '/api/v1/master-data',
  '/api/v1/production',
  '/api/v1/warehouse',
  '/api/v1/purchase',
  '/api/v1/sales',
  '/api/v1/cost',
  '/api/v1/data-exchange',
  '/api/v1/workbench',
];
for (const route of requiredApiGroups) {
  assert.ok(apiSource.includes(route), `current backend API group must remain covered: ${route}`);
}

console.log(`API contract checks passed (${contracts.length + 10 + requiredApiGroups.length})`);
