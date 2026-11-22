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
                        createError = null} = {}) {
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
    repos: {compareCommitsWithBasehead: async args => {
      assert.equal(args.basehead, `main...${sha}`);
      return {data: {ahead_by: phase ? finalAhead : ahead}};
    }},
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
    await new AsyncFunction('github', 'context', 'core', scripts[1])(github, context, core);
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
for (const [name, options] of Object.entries({
  'existing PR': {existing: true},
  'failed CI': {conclusion: 'failure'},
  'cancelled CI': {conclusion: 'cancelled'},
  'pull request CI': {event: 'pull_request'},
  'main CI': {branch: 'main'},
  'unrelated branch': {branch: 'feature'},
  'fork': {repository: 'attacker/projectdavid'},
  'stale CI': {current: 'newer'},
  'push during token creation': {finalHead: 'newer'},
  'no changes': {ahead: 0},
  'changes already promoted': {finalAhead: 0},
})) test(`${name} creates no PR`, async () => assert.equal((await execute(options)).length, 0));
test('duplicate race reuses PR after 422', async () => assert.equal((await execute({race: true})).length, 1));
test('unexpected errors propagate', async () => {
  await assert.rejects(execute({createError: 403}));
  await assert.rejects(execute({createError: 422}));
});
