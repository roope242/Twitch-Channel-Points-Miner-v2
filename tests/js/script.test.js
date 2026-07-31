// Regression suite for TwitchChannelPointsMiner/assets/script.js, run against a real
// jQuery in jsdom. Ported 1:1 from the throwaway harness used while fixing #12 and #21
// (see ISSUES.md and CLAUDE.md for the history and the traps below).
//
// Run with: node --test tests/js/script.test.js
'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const SCRIPT_PATH = path.join(
  __dirname,
  '..',
  '..',
  'TwitchChannelPointsMiner',
  'assets',
  'script.js'
);

const HTML = `<!doctype html><html><body>
  <div id="header"></div>
  <div id="chart"></div>
  <input type="checkbox" id="log" checked>
  <input type="checkbox" id="toggle-header" checked>
  <input type="checkbox" id="annotations" checked>
  <input type="checkbox" id="dark-mode" checked>
  <button id="auto-update-log"></button>
  <button id="refresh-followers"></button>
  <div id="log-content"></div>
  <ul id="streamers-list"></ul>
  <span id="sorting-by"></span>
  <input id="startDate"><input id="endDate">
  <div class="dropdown"></div>
</body></html>`;

test('dashboard script.js (jsdom)', async (t) => {
  const jquerySource = fs.readFileSync(
    require.resolve('jquery/dist/jquery.js'),
    'utf8'
  );
  const appSource = fs.readFileSync(SCRIPT_PATH, 'utf8');

  const dom = new JSDOM(HTML, { runScripts: 'outside-only', url: 'http://localhost/' });
  const w = dom.window;

  // jsdom implements neither of these; script.js calls both during renderStreamers.
  w.Element.prototype.scrollIntoView = function () {};
  w.alert = function () {};

  // --- stubs for what charts.html supplies, so script.js can load ---
  w.eval(`
    var daysAgo = 7;
    var __chartCalls = [];
    function ApexCharts() {
      var rec = function (n) { return function () { __chartCalls.push(n); }; };
      this.render = rec('render');
      this.updateOptions = rec('updateOptions');
      this.updateSeries = rec('updateSeries');
      this.appendSeries = rec('appendSeries');
      this.addXaxisAnnotation = rec('addXaxisAnnotation');
      this.removeAnnotation = rec('removeAnnotation');
      this.clearAnnotations = rec('clearAnnotations');
    }
    var __darkModeCalls = 0;
    function toggleDarkMode() { __darkModeCalls++; }
  `);

  // Controllable AJAX: every call returns a Deferred we resolve or reject by hand.
  const requests = [];
  function fakeAjax(url) {
    const d = w.jQuery.Deferred();
    // The pre-change code passes its success handler as an argument
    // ($.get(url, cb) / $.getJSON(url, data, cb)); honour it, or "before" would
    // fail for the wrong reason.
    for (const arg of Array.prototype.slice.call(arguments, 1)) {
      if (typeof arg === 'function') d.done(arg);
    }
    requests.push({ url, deferred: d });
    return d.promise();
  }

  // TRAP: install any setTimeout stub *after* this eval. jQuery schedules its own
  // ready callback through setTimeout, so stubbing it earlier silently stops every
  // $(document).ready handler from running while unrelated assertions still pass.
  w.eval(jquerySource);
  w.jQuery.get = fakeAjax;
  w.jQuery.getJSON = fakeAjax;
  w.jQuery.post = fakeAjax;
  w.$ = w.jQuery;

  w.eval(appSource);
  await new Promise((resolve) => setTimeout(resolve, 50)); // let jQuery fire ready

  await t.test('$(document).ready handlers ran', () => {
    assert.equal(
      w.eval('typeof __chartCalls') === 'object' &&
        w.eval('__chartCalls.indexOf("render")') >= 0,
      true
    );
  });

  const timers = [];
  function captureTimers() {
    w.setTimeout = function (fn, delay) {
      timers.push({ fn, delay });
      return timers.length;
    };
  }
  captureTimers();

  // -------------------------------------------------------------------------
  // 1. getLog(): a FAILED request must still re-schedule the poll.
  // -------------------------------------------------------------------------
  requests.length = 0;
  timers.length = 0;
  // #auto-update-log toggles autoUpdateLog; two clicks leaves it true and calls getLog().
  w.$('#auto-update-log').trigger('click');
  w.$('#auto-update-log').trigger('click');
  let logReq = requests.filter((r) => String(r.url).includes('/log?'));

  await t.test('getLog issued a request', () => {
    assert.equal(logReq.length > 0, true);
  });

  logReq[logReq.length - 1].deferred.reject({ status: 500 });

  await t.test('FAILED getLog re-schedules the 1s poll', () => {
    assert.equal(timers.filter((tm) => tm.delay === 1000).length, 1);
  });

  // -------------------------------------------------------------------------
  // 2. getLog(): the success path still works, and #12's text node survives.
  // -------------------------------------------------------------------------
  requests.length = 0;
  timers.length = 0;
  w.$('#auto-update-log').trigger('click');
  w.$('#auto-update-log').trigger('click');
  const okReq = requests.filter((r) => String(r.url).includes('/log?')).pop();

  await t.test('getLog re-issued after the failure', () => {
    assert.equal(!!okReq, true);
  });

  okReq.deferred.resolve('line one <img src=x onerror="window.PWNED=1">\n');

  await t.test('SUCCESSFUL getLog re-schedules the 1s poll', () => {
    assert.equal(timers.filter((tm) => tm.delay === 1000).length, 1);
  });

  await t.test('no <img> element created from log text (#12 intact)', () => {
    assert.equal(w.document.querySelectorAll('#log-content img').length, 0);
  });

  await t.test('log text rendered verbatim (#12 intact)', () => {
    assert.equal(
      w.document.getElementById('log-content').textContent.includes('<img src=x onerror='),
      true
    );
  });

  // -------------------------------------------------------------------------
  // 3. getStreamerData(): a FAILED request must still re-schedule the refresh.
  // -------------------------------------------------------------------------
  requests.length = 0;
  timers.length = 0;
  w.eval('currentStreamer = "foo.json";');
  w.eval('getStreamerData("foo.json");');
  const sdReq = requests.filter((r) => String(r.url).includes('./json/')).pop();

  await t.test('getStreamerData issued a request', () => {
    assert.equal(!!sdReq, true);
  });

  sdReq.deferred.reject({ status: 500 });

  await t.test('FAILED getStreamerData re-schedules the 5min refresh', () => {
    assert.equal(timers.filter((tm) => tm.delay === 300000).length, 1);
  });

  // -------------------------------------------------------------------------
  // 4. getStreamers(): a FAILED request must not leave the list silently empty.
  // -------------------------------------------------------------------------
  requests.length = 0;
  w.eval('getStreamers();');
  const strReq = requests.filter((r) => String(r.url).includes('streamers')).pop();

  await t.test('getStreamers issued a request', () => {
    assert.equal(!!strReq, true);
  });

  strReq.deferred.reject({ status: 500 });

  await t.test('FAILED getStreamers shows a message instead of an empty list', () => {
    assert.equal(
      w.document.getElementById('streamers-list').textContent.trim(),
      'Failed to load streamers.'
    );
  });

  // -------------------------------------------------------------------------
  // 5. #annotations / #dark-mode must be bound exactly once.
  // -------------------------------------------------------------------------
  w.eval('__chartCalls.length = 0; __darkModeCalls = 0;');
  w.$('#annotations').trigger('click');

  await t.test('one #annotations click -> updateAnnotations once', () => {
    assert.equal(
      w.eval(
        '__chartCalls.filter(function (c) { return c === "clearAnnotations"; }).length'
      ),
      1
    );
  });

  w.eval('__darkModeCalls = 0;');
  w.$('#dark-mode').trigger('click');

  await t.test('one #dark-mode click -> toggleDarkMode once', () => {
    assert.equal(w.eval('__darkModeCalls'), 1);
  });

  // -------------------------------------------------------------------------
  // 6. displayname must not leak to window.
  // -------------------------------------------------------------------------
  w.eval(
    'streamersList = [{name: "abc.json", points: 1, last_activity: 0}]; sortField = "name";'
  );
  w.eval('delete window.displayname; renderStreamers();');

  await t.test('displayname is not an implicit global', () => {
    assert.equal(w.eval('typeof window.displayname'), 'undefined');
  });

  // TRAP: renderStreamers' changeStreamer call runs in a Promise .then; let it land
  // here rather than bleeding a stray request into the next test case.
  await new Promise((resolve) => setTimeout(resolve, 20));

  // -------------------------------------------------------------------------
  // 7. A localStorage entry naming a streamer that no longer exists must not be
  //    polled forever (CodeRabbit's finding on PR #25).
  // -------------------------------------------------------------------------
  requests.length = 0;
  timers.length = 0;
  w.localStorage.setItem('selectedStreamer', 'ghost.json');
  w.eval('currentStreamer = null; streamersList = [];');
  w.eval('getStreamers();');
  const listReq = requests.filter((r) => String(r.url).includes('streamers')).pop();
  listReq.deferred.resolve([{ name: 'real.json', points: 1, last_activity: 0 }]);
  await new Promise((resolve) => setTimeout(resolve, 20)); // renderStreamers resolves a Promise

  const ghostReqs = requests.filter((r) => String(r.url).includes('./json/ghost.json'));

  await t.test('no request is issued for the missing streamer', () => {
    assert.equal(ghostReqs.length, 0);
  });

  await t.test('the stale localStorage entry is cleared', () => {
    assert.equal(w.localStorage.getItem('selectedStreamer'), 'real.json');
  });

  await t.test('selection falls back to the first live streamer', () => {
    assert.equal(w.eval('currentStreamer'), 'real.json');
  });

  // The pre-fix failure mode: the 404 for the missing streamer re-schedules itself
  // every five minutes for the life of the page.
  for (const r of requests.filter((r) => String(r.url).includes('./json/'))) {
    r.deferred.reject({ status: 404 });
  }
  const refresh = timers.filter((tm) => tm.delay === 300000);

  await t.test('exactly one 5min refresh timer is pending', () => {
    assert.equal(refresh.length, 1);
  });

  // Fire it and see which streamer the retry loop is actually pinned to. Guard the
  // access: on regressed code there may be no timer at all, and indexing into an
  // empty array throws, aborting every remaining case instead of failing them.
  requests.length = 0;
  if (refresh.length > 0) refresh[refresh.length - 1].fn();

  await t.test('the retry loop polls the live streamer, not the missing one', () => {
    assert.deepEqual(
      requests.map((r) => String(r.url)),
      ['./json/real.json']
    );
  });

  // -------------------------------------------------------------------------
  // 8. A successful-but-EMPTY /streamers must not wipe the saved selection.
  //    analytics_path is cwd-relative, so [] is a legitimate first-start answer.
  // -------------------------------------------------------------------------
  requests.length = 0;
  timers.length = 0;
  w.localStorage.setItem('selectedStreamer', 'alice.json');
  w.eval('currentStreamer = null; streamersList = [];');
  w.eval('getStreamers();');
  const emptyReq = requests.filter((r) => String(r.url).includes('streamers')).pop();
  emptyReq.deferred.resolve([]);
  await new Promise((resolve) => setTimeout(resolve, 20));

  await t.test('an empty streamer list preserves the saved selection', () => {
    assert.equal(w.localStorage.getItem('selectedStreamer'), 'alice.json');
  });
});
