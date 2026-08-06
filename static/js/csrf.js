/**
 * Post-Pilot CSRF helper
 *
 * Reads <meta name="csrf-token"> and attaches X-CSRFToken to same-origin
 * mutating fetch() calls (POST/PUT/PATCH/DELETE). Include this script on
 * every authenticated page that calls session-backed APIs.
 */
(function () {
  'use strict';

  function getToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  var originalFetch = window.fetch;
  if (!originalFetch) return;

  window.fetch = function (input, init) {
    init = init || {};
    var method = (init.method || 'GET').toUpperCase();
    if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') {
      return originalFetch.call(this, input, init);
    }

    var url;
    try {
      url = typeof input === 'string' ? new URL(input, window.location.origin)
                                      : new URL(input.url, window.location.origin);
    } catch (e) {
      return originalFetch.call(this, input, init);
    }

    if (url.origin !== window.location.origin) {
      return originalFetch.call(this, input, init);
    }

    var token = getToken();
    if (!token) {
      return originalFetch.call(this, input, init);
    }

    var headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined) || {});
    if (!headers.has('X-CSRFToken') && !headers.has('X-CSRF-Token')) {
      headers.set('X-CSRFToken', token);
    }
    init.headers = headers;
    return originalFetch.call(this, input, init);
  };
})();
