import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const readJson = async (path) => JSON.parse(await readFile(path, 'utf8'));
const app = await readJson(join(root, 'app.json'));
const project = await readJson(join(root, 'project.config.json'));
const appSource = await readFile(join(root, 'app.js'), 'utf8');

assert.equal(project.miniprogramRoot, './', 'project.config.json must identify the source root');
assert.ok(project.appid, 'project.config.json must include an appid');
assert.match(project.libVersion, /^(?:trial|\d+\.\d+\.\d+)$/, 'project.config.json must use a valid base-library selector');
assert.match(appSource, /X-ADP-Client['"]?: ['"]mobile/, 'requests must ask the backend for a mobile session token');
assert.match(appSource, /res\.cookies/, 'the mini-program must capture response cookies for CSRF continuity');
assert.match(appSource, /Set-Cookie/i, 'the mini-program must support the Set-Cookie response header');

for (const page of app.pages) {
  for (const suffix of ['.js', '.json', '.wxml', '.wxss']) {
    await readFile(join(root, `${page}${suffix}`));
  }
}
for (const tab of app.tabBar?.list ?? []) {
  if (tab.iconPath) await readFile(join(root, tab.iconPath));
  if (tab.selectedIconPath) await readFile(join(root, tab.selectedIconPath));
}

const sourceFiles = [];
async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await walk(path);
    else if (extname(path) === '.js' && !path.includes(`${join(root, 'scripts')}`)) sourceFiles.push(path);
  }
}
await walk(root);
const source = (await Promise.all(sourceFiles.map((path) => readFile(path, 'utf8')))).join('\n');
assert.doesNotMatch(source, /['"`]\/(?:messages(?:\/|['"`])|profile\/(?:stats|history)|system\/version)/, 'obsolete backend routes must not remain');
assert.match(source, /['"`]\/notifications/, 'notification center must use the current notifications API');
assert.match(source, /['"`]\/work-items/, 'task history must use the current work-items API');
assert.doesNotMatch(source, /TODO|FIXME/, 'unfinished TODO/FIXME markers must not remain');

const requiredRoutePrefixes = [
  '/auth/me',
  '/auth/csrf',
  '/auth/login',
  '/auth/password/change',
  '/workbench/summary',
  '/notifications',
  '/work-items',
  '/master-data/ponds',
  '/master-data/pond-groups',
  '/master-data/materials',
  '/production/batches',
  '/production/feed-plans',
  '/production/feed-logs',
  '/production/feed-tasks',
  '/production/daily-operations',
  '/warehouse/warehouses',
  '/warehouse/issue-requests',
  '/health',
];
for (const route of requiredRoutePrefixes) {
  assert.ok(source.includes(route), `current backend route must remain covered: ${route}`);
}

console.log(`Mini-program project checks passed (${app.pages.length} pages, ${sourceFiles.length} JavaScript files, ${requiredRoutePrefixes.length} API route groups)`);
