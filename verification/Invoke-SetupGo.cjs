'use strict';

if (process.env.GITHUB_ACTIONS !== 'true' ||
    process.env.RUNNER_ENVIRONMENT !== 'github-hosted' ||
    process.platform !== 'win32' ||
    !/^[CD]:\\setup-go-probe\\[0-9a-f]{32}\\toolcache$/i.test(process.env.PROBE_TOOL_CACHE || '')) {
  throw new Error('Expected the hosted Windows probe and its isolated tool-cache path');
}

// Runner-owned RUNNER_* values override step env; set this inside the action process.
process.env.RUNNER_TOOL_CACHE = process.env.PROBE_TOOL_CACHE;
console.log(`Probe process: ${process.version} ${process.arch}; RUNNER_TOOL_CACHE=${process.env.RUNNER_TOOL_CACHE}`);
require('./dist/setup/index.js');
