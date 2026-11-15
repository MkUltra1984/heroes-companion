// A plain script (not a module) that runs before the application. If the application cannot start (a browser without
// modules, a script file that did not arrive, texts or data that did not load), the visitor sees a message and a
// "Try again" button instead of a page that says "Loading" for ever. The message itself is in index.html.
(function () {
  'use strict';
  var shown = false;
  function fail(detail) {
    if (shown) return;
    var view = document.getElementById('view'), card = document.getElementById('bootfail');
    if (!view || !card || view.getAttribute('data-ready')) return;
    shown = true;
    if (window.console) console.error('Heroes Companion could not start: ' + (detail || 'unknown reason'));
    var wait = document.getElementById('bootwait'); if (wait) wait.hidden = true;
    var more = document.getElementById('bootfail-detail'); if (more && detail) more.textContent = detail;
    card.hidden = false;
    var again = document.getElementById('bootfail-retry'); if (again) again.onclick = function () { location.reload(); };
  }
  window.hcBootFailed = fail;
  // a script file of the application that could not be fetched or parsed
  window.addEventListener('error', function (e) {
    var el = e.target;
    if (el && el.tagName === 'SCRIPT') fail('A part of the page did not arrive: ' + (el.getAttribute('src') || 'script'));
    else if (e.filename && /\/js\//.test(e.filename) && !document.getElementById('view').getAttribute('data-ready')) fail(String(e.message || ''));
  }, true);
  if (!('noModule' in HTMLScriptElement.prototype)) document.addEventListener('DOMContentLoaded', function () { fail('This browser is too old for this page.'); });
})();
