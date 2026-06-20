// PostPilot Pro — Website Embed
// Add ONE line to your site's <head>:
// <script src="https://YOUR-APP-URL/static/embed.js"></script>
//
// This automatically shows:
//   • Announcement banner (top of page)
//   • Today's specials (inject into #postpilot-specials)
//   • Hours (inject into #postpilot-hours)
//   • Location (inject into #postpilot-location)
//
// Optional HTML hooks on your website:
//   <div id="postpilot-specials"></div>
//   <div id="postpilot-hours"></div>
//   <div id="postpilot-location"></div>

(function() {
    var BASE = document.currentScript ? document.currentScript.src.replace('/static/embed.js','') : '';

    fetch(BASE + '/static/banner.json?t=' + Date.now())
        .then(function(r) { return r.json(); })
        .then(function(b) {
            if (!b || !b.active) return;

            // ─ Announcement Banner
            if (b.message) {
                var bar = document.createElement('div');
                bar.id  = 'postpilot-bar';
                bar.style.cssText = [
                    'position:fixed','top:0','left:0','right:0',
                    'background:linear-gradient(90deg,#0f4c81,#1a73e8)',
                    'color:#fff','padding:10px 20px',
                    'display:flex','justify-content:space-between','align-items:center',
                    'z-index:99999','font-family:sans-serif','font-size:14px','font-weight:600',
                    'box-shadow:0 2px 8px rgba(0,0,0,.2)'
                ].join(';');

                var msg  = document.createElement('span');
                msg.textContent = '📣 ' + b.message;

                var right = document.createElement('div');
                right.style.cssText = 'display:flex;align-items:center;gap:10px;';

                if (b.link) {
                    var cta = document.createElement('a');
                    cta.href = b.link; cta.target = '_blank';
                    cta.style.cssText = 'background:#fff;color:#1a73e8;padding:5px 12px;border-radius:6px;text-decoration:none;font-size:12px;font-weight:700;';
                    cta.textContent = 'View Details →';
                    right.appendChild(cta);
                }

                var close = document.createElement('button');
                close.textContent = '✕';
                close.style.cssText = 'background:none;border:none;color:#fff;cursor:pointer;font-size:16px;padding:0 4px;';
                close.onclick = function() { bar.style.display='none'; };
                right.appendChild(close);

                bar.appendChild(msg);
                bar.appendChild(right);
                document.body.prepend(bar);
                document.body.style.paddingTop = '48px';
            }

            // ─ Inject into optional HTML hooks
            function inject(id, val) {
                if (!val) return;
                var el = document.getElementById(id);
                if (el) el.innerHTML = val.replace(/\n/g, '<br>');
            }

            inject('postpilot-specials', b.specials);
            inject('postpilot-hours',    b.hours);
            inject('postpilot-location', b.location);
        })
        .catch(function() {}); // silent fail
})();
