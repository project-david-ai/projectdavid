// Execute the actual trusted inline workflow scripts against a fake GitHub API.
// Run with: node --test tests/workflows/auto-pr.test.cjs
const {readFileSync} = require('node:fs');
const {test} = require('node:test');
const assert = require('node:assert/strict');
const workflow = readFileSync('.github/workflows/auto-pr.yml', 'utf8');
const scripts = [...workflow.matchAll(/          script: \|\r?\n((?:            .*\r?\n|\r?\n)+)/g)]
  .map(match => match[1].split(/\r?\n/).map(line => line.slice(12)).join('\n'));
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;

async function execute({conclusion = 'success', event = 'push', branch = 'dev',
                        repository = 'project-david-ai/projectdavid', sha = 'tested',
                        current = 'tested', finalHead = current, ahead = 1,
                        finalAhead = ahead, existing = false, race = false,
                        createError = null, releaseParent = sha,
                        releaseAuthor = 'semantic-release-bot',
                        releaseMessage = 'chore(release): 1.115.0-dev.2 [skip ci]',
                        releaseFiles = null, releaseParents = null} = {}) {
  const calls = [], outputs = {};
  let phase = 0, listCalls = 0;
  const context = {repo: {owner: 'project-david-ai', repo: 'projectdavid'},
    payload: {workflow_run: {conclusion, event, head_branch: branch,
      head_repository: {full_name: repository}, head_sha: sha}}};
  const github = {rest: {
    git: {getRef: async args => {
      assert.equal(args.ref, 'heads/dev');
      return {data: {object: {sha: phase ? finalHead : current}}};
    }},
    repos: {
      getCommit: async args => {
        assert.equal(args.ref, current);
        return {data: {
          parents: releaseParents || [{sha: current === 'released' ? releaseParent : 'untested'}],
          author: {login: releaseAuthor},
          commit: {message: releaseMessage},
          files: releaseFiles || [
            {filename: 'CHANGELOG.md', status: 'modified', patch: '@@ -1,2 +1,3 @@\n+new release'},
            {filename: 'pyproject.toml', status: 'modified',
              patch: '@@ -5,7 +5,7 @@\n-version = "1.115.0-dev.1"\n+version = "1.115.0-dev.2"'}
          ]
        }};
      },
      compareCommitsWithBasehead: async args => {
        assert.equal(args.basehead, `main...${phase ? outputs.approved_head : current}`);
        return {data: {ahead_by: phase ? finalAhead : ahead}};
      }
    },
    pulls: {
      list: async args => {
        assert.equal(args.base, 'main');
        assert.equal(args.head, 'project-david-ai:dev');
        return {data: existing || (race && listCalls++ > 0) ? [{number: 7}] : []};
      },
      create: async args => {
        calls.push(args);
        if (race || createError) throw {status: createError || 422};
        return {data: {html_url: 'https://github.com/project-david-ai/projectdavid/pull/7'}};
      }
    }
  }};
  const core = {setOutput: (key, value) => outputs[key] = value, info: () => {}};
  await new AsyncFunction('github', 'context', 'core', scripts[0])(github, context, core);
  if (outputs.needed === 'true') {
    phase = 1;
    const process = {env: {APPROVED_HEAD: outputs.approved_head}};
    await new AsyncFunction('github', 'context', 'core', 'process', scripts[1])(
      github, context, core, process);
  }
  return calls;
}

test('workflow permissions, trigger, concurrency and App scope', () => {
  assert.equal(scripts.length, 2);
  assert.match(workflow, /workflows: \["Lint, Test, Tag, and Publish"\]/);
  assert.match(workflow, /branches: \[dev\]/);
  assert.match(workflow, /cancel-in-progress: false/);
  assert.match(workflow, /actions\/create-github-app-token@v3/);
  assert.match(workflow, /permission-contents: read/);
  assert.match(workflow, /permission-pull-requests: write/);
  assert.match(workflow, /vars.AUTO_PR_APP_CLIENT_ID/);
  assert.match(workflow, /secrets.AUTO_PR_APP_PRIVATE_KEY/);
  assert.doesNotMatch(workflow, /checkout@|contents: write|pulls\.merge|auto.merge|pypi-publish|\brun:/);
  for (const script of scripts) assert.doesNotMatch(script, /\$\{\{/);
});
test('current successful dev push creates one PR', async () => {
  const calls = await execute();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].base, 'main');
  assert.equal(calls[0].head, 'dev');
});
test('semantic-release child of tested SHA creates a PR', async () => {
  assert.equal((await execute({current: 'released'})).length, 1);
});
for (const [name, options] of Object.entries({
  'existing PR': {existing: true},
  'failed CI': {conclusion: 'failure'},
  'cancelled CI': {conclusion: 'cancelled'},
  'pull request CI': {event: 'pull_request'},
  'main CI': {branch: 'main'},
  'unrelated branch': {branch: 'feature'},
  'fork': {repository: 'attacker/projectdavid'},
  'stale CI': {current: 'newer'},
  'incorrect release parent': {current: 'released', releaseParent: 'other'},
  'release merge commit': {current: 'released', releaseParents: [{sha: 'tested'}, {sha: 'other'}]},
  'untrusted release author': {current: 'released', releaseAuthor: 'attacker'},
  'untrusted release message': {current: 'released', releaseMessage: 'feat(sdk): malicious'},
  'extra release file': {current: 'released', releaseFiles: [
    {filename: 'CHANGELOG.md', status: 'modified', patch: '+new'},
    {filename: 'pyproject.toml', status: 'modified', patch: '-version = "1.0"\n+version = "1.115.0-dev.2"'},
    {filename: 'src/projectdavid/entity.py', status: 'modified', patch: '+new'}
  ]},
  'release changes dependencies': {current: 'released', releaseFiles: [
    {filename: 'CHANGELOG.md', status: 'modified', patch: '+new'},
    {filename: 'pyproject.toml', status: 'modified',
      patch: '-version = "1.0"\n+version = "1.115.0-dev.2"\n+dependency = "evil"'}
  ]},
  'release deletes changelog content': {current: 'released', releaseFiles: [
    {filename: 'CHANGELOG.md', status: 'modified', patch: '-old content\n+new'},
    {filename: 'pyproject.toml', status: 'modified',
      patch: '-version = "1.0"\n+version = "1.115.0-dev.2"'}
  ]},
  'push during token creation': {finalHead: 'newer'},
  'release superseded during token creation': {current: 'released', finalHead: 'newer'},
  'no changes': {ahead: 0},
  'changes already promoted': {finalAhead: 0},
})) test(`${name} creates no PR`, async () => assert.equal((await execute(options)).length, 0));
test('duplicate race reuses PR after 422', async () => assert.equal((await execute({race: true})).length, 1));
test('unexpected errors propagate', async () => {
  await assert.rejects(execute({createError: 403}));
  await assert.rejects(execute({createError: 422}));
});
