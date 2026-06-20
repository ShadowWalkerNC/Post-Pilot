// PostPilot Pro — Smart Content Hub JS

// Smart routing rules per content type
const ROUTING = {
    text:   { fb: true,  ig: false, yt: false, tt: false, gb: true,  web: true,  hint: '📝 Text post → Facebook, Google Business, Website' },
    image:  { fb: true,  ig: true,  yt: false, tt: false, gb: true,  web: true,  hint: '📸 Photo → Facebook, Instagram, Google Business, Website' },
    video:  { fb: true,  ig: true,  yt: true,  tt: true,  gb: false, web: true,  hint: '🎬 Video → YouTube, TikTok, Facebook, Instagram Reel, Website' },
    promo:  { fb: true,  ig: true,  yt: false, tt: true,  gb: true,  web: true,  hint: '🎉 Promo → All platforms' },
    update: { fb: true,  ig: false, yt: false, tt: false, gb: true,  web: true,  hint: '📊 Update → Facebook, Google Business, Website' },
};

const RTAG_LABELS = {
    text:   { fb: 'text post', ig: '—',        yt: '—',     tt: '—',      gb: 'short post', web: 'banner' },
    image:  { fb: 'photo',    ig: 'photo',     yt: '—',     tt: '—',      gb: 'photo post', web: 'banner+img' },
    video:  { fb: 'video',    ig: 'reel',      yt: 'upload', tt: 'script',  gb: '—',          web: 'video embed' },
    promo:  { fb: 'post',     ig: 'post',      yt: '—',     tt: 'script',  gb: 'offer',      web: 'banner' },
    update: { fb: 'post',     ig: '—',        yt: '—',     tt: '—',      gb: 'update',     web: 'banner' },
};

let currentType = 'text';
let postsThisWeek = 0;

document.addEventListener('DOMContentLoaded', () => {
    setContentType('text', document.getElementById('ctype-text'));
    bindPreviewUpdates();
    checkConnections();
    loadStats();
});

// ── Content Type ─────────────────────────────────────────────────
function setContentType(type, el) {
    currentType = type;
    document.querySelectorAll('.ctype').forEach(b => b.classList.remove('active'));
    el.classList.add('active');

    const routing = ROUTING[type];
    const tags    = RTAG_LABELS[type];

    // Update checkboxes + route tags
    ['fb','ig','yt','tt','gb','web'].forEach(p => {
        const tog  = document.getElementById('tog-' + p);
        const rtag = document.getElementById('rtag-' + p);
        const wrap = document.getElementById('tog-wrap-' + p);
        if (tog) {
            tog.checked = routing[p];
            wrap.style.opacity = routing[p] ? '1' : '0.4';
            rtag.textContent = tags[p] !== '—' ? tags[p] : '';
            rtag.style.display = tags[p] && tags[p] !== '—' ? 'inline' : 'none';
        }
    });

    // Routing hint
    document.getElementById('routingHint').innerHTML = routing.hint;

    // Show/hide media fields
    const isVideo = type === 'video';
    const isImage = type === 'image' || type === 'promo';
    document.getElementById('mediaGroup').style.display = (isVideo || isImage) ? 'block' : 'none';
    document.getElementById('videoGroup').style.display = isVideo ? 'block' : 'none';
    document.getElementById('mediaLabel').textContent   = isVideo ? '📸 Thumbnail URL' : '📸 Image URL';

    updatePreview();
}

// ── Live Preview ──────────────────────────────────────────────────
function bindPreviewUpdates() {
    ['mainCaption','mediaUrl','videoUrl','linkUrl','webSpecials','webHours','webLocation']
        .forEach(id => { const el = document.getElementById(id); if (el) el.addEventListener('input', updatePreview); });
}

function updatePreview() {
    const caption  = document.getElementById('mainCaption').value  || 'Your post will preview here…';
    const mediaUrl = document.getElementById('mediaUrl')?.value    || '';
    const videoUrl = document.getElementById('videoUrl')?.value    || '';
    const linkUrl  = document.getElementById('linkUrl').value      || '#';
    const type     = currentType;

    // — Facebook
    document.getElementById('prev-fb-text').textContent = caption;
    const fbMedia = document.getElementById('prev-fb-media');
    if (videoUrl) fbMedia.innerHTML = `<div class="mock-video-thumb"><div class="play-btn">▶</div></div>`;
    else if (mediaUrl) fbMedia.innerHTML = `<img src="${mediaUrl}" style="width:100%;max-height:260px;object-fit:cover">`;
    else fbMedia.innerHTML = '';

    // — Instagram
    document.getElementById('prev-ig-text').textContent = caption;
    const igMedia = document.getElementById('prev-ig-media');
    if (videoUrl) igMedia.innerHTML = `<div class="mock-img-placeholder mock-video-thumb"><div class="play-btn">▶</div><span>Reel</span></div>`;
    else if (mediaUrl) igMedia.innerHTML = `<img src="${mediaUrl}" style="width:100%;max-height:280px;object-fit:cover">`;
    else igMedia.innerHTML = `<div class="mock-img-placeholder">📷 Photo / Video Preview</div>`;

    // — YouTube
    const ytEmbed = document.getElementById('prev-yt-embed');
    if (videoUrl && videoUrl.includes('youtube.com')) {
        const vid = videoUrl.split('v=')[1]?.split('&')[0];
        if (vid) ytEmbed.innerHTML = `<iframe width="100%" height="200" src="https://www.youtube.com/embed/${vid}" frameborder="0" allowfullscreen></iframe>`;
    } else if (videoUrl) {
        ytEmbed.innerHTML = `<video src="${videoUrl}" controls style="width:100%;border-radius:8px"></video>`;
    } else {
        ytEmbed.innerHTML = `<div class="mock-img-placeholder">🎬 Add a YouTube or MP4 URL to preview</div>`;
    }
    document.getElementById('prev-yt-title').textContent = caption.split('\n')[0].substring(0, 80);
    document.getElementById('prev-yt-desc').textContent  = caption.substring(0, 200);

    // — TikTok script
    document.getElementById('prev-tt-text').textContent = toTikTokScript(caption);

    // — Google Business
    document.getElementById('prev-gb-text').textContent = toGBPost(caption);
    document.getElementById('prev-gb-link').href = linkUrl;
    const gbMedia = document.getElementById('prev-gb-media');
    if (mediaUrl) gbMedia.innerHTML = `<img src="${mediaUrl}" style="width:100%;height:120px;object-fit:cover;border-radius:6px">`;
    else gbMedia.innerHTML = '📷 Photo';

    // — Website banner
    document.getElementById('prev-web-text').textContent = '📣 ' + caption.split('\n')[0].substring(0, 100);
    document.getElementById('prev-web-link').href = linkUrl;
}

function switchPreview(name, el) {
    document.querySelectorAll('.preview-frame').forEach(f => f.style.display = 'none');
    document.querySelectorAll('.ptab').forEach(t => t.classList.remove('active'));
    document.getElementById('preview-' + name).style.display = 'block';
    if (el) el.classList.add('active');
}

// ── Push to All ──────────────────────────────────────────────────
async function pushToAll() {
    const caption    = document.getElementById('mainCaption').value.trim();
    const mediaUrl   = document.getElementById('mediaUrl')?.value.trim()   || null;
    const videoUrl   = document.getElementById('videoUrl')?.value.trim()   || null;
    const linkUrl    = document.getElementById('linkUrl').value.trim()     || null;
    const schedTime  = document.getElementById('scheduleTime').value       || null;

    const webData = {
        specials:  document.getElementById('webSpecials')?.value  || '',
        hours:     document.getElementById('webHours')?.value     || '',
        location:  document.getElementById('webLocation')?.value  || ''
    };

    if (!caption) { toast('Write something first!', 'warn'); return; }

    const platforms = {
        fb:  document.getElementById('tog-fb').checked,
        ig:  document.getElementById('tog-ig').checked,
        yt:  document.getElementById('tog-yt').checked,
        tt:  document.getElementById('tog-tt').checked,
        gb:  document.getElementById('tog-gb').checked,
        web: document.getElementById('tog-web').checked,
    };

    if (!Object.values(platforms).some(Boolean)) { toast('Select at least one platform!', 'warn'); return; }

    addFeed('🚀 Pushing to selected platforms…', 'info');

    try {
        const res  = await fetch('/api/push_all', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                user_id: 'default', content_type: currentType,
                caption, image_url: mediaUrl, video_url: videoUrl,
                link_url: linkUrl, platforms, schedule_time: schedTime,
                web_data: webData
            })
        });
        const data = await res.json();

        const names = { fb:'Facebook', ig:'Instagram', yt:'YouTube', tt:'TikTok', gb:'Google Business', web:'Website' };
        Object.entries(data.results || {}).forEach(([p, r]) => {
            if (r.skipped) return;
            if (r.success) { addFeed(`✅ ${names[p]}: ${r.message || 'Done'}`, 'success'); toast(`✅ ${names[p]}`, 'success'); }
            else { addFeed(`❌ ${names[p]}: ${r.error}`, 'error'); toast(`❌ ${names[p]}`, 'error'); }
        });

        postsThisWeek++;
        document.getElementById('stat-posts').textContent = postsThisWeek;
    } catch (e) {
        addFeed('❌ Network error — is the app running?', 'error');
        toast('Network error', 'error');
    }
}

// ── Auto Generate ────────────────────────────────────────────────
async function autoGenerate() {
    const templateMap = { text: 'instagram_engagement', image: 'instagram_menu', video: 'instagram_location', promo: 'facebook_giveaway', update: 'instagram_location' };
    try {
        const res  = await fetch('/api/generate_post', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ user_id: 'default', template: templateMap[currentType] || 'instagram_location' })
        });
        const data = await res.json();
        if (data.success) {
            document.getElementById('mainCaption').value = data.post.caption;
            updatePreview();
            toast('✨ Caption generated!', 'success');
        }
    } catch (e) { toast('Set up your business first (/setup)', 'warn'); }
}

// ── Connection Status ─────────────────────────────────────────────
function checkConnections() {
    fetch('/api/connection_status', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({user_id:'default'}) })
        .then(r => r.json())
        .then(data => {
            let live = 0;
            Object.entries(data.platforms || {}).forEach(([k, v]) => {
                const pill = document.getElementById('pill-' + k);
                if (pill) pill.classList.toggle('connected', v);
                if (v) live++;
            });
            document.getElementById('stat-platforms').textContent = live + '/6';
        })
        .catch(() => {});
}

function loadStats() {
    fetch('/api/analytics', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({user_id:'default'}) })
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            const reach = data.posts.reduce((s,p) => s+(p.reach||0), 0);
            const likes = data.posts.reduce((s,p) => s+(p.likes||0), 0);
            document.getElementById('stat-posts').textContent = data.total_posts || 0;
            document.getElementById('stat-reach').textContent = reach > 999 ? (reach/1000).toFixed(1)+'k' : reach;
            document.getElementById('stat-likes').textContent = likes;
        })
        .catch(() => {});
}

// ── Helpers ────────────────────────────────────────────────────────
function toTikTokScript(caption) {
    const first = caption.split('\n')[0];
    return `🎵 TIKTOK SCRIPT\n\n[HOOK — first 3 sec]\n"${first}"\n\n[BODY — read naturally]\n${caption.substring(0,300)}\n\n[CTA]\n"Follow for daily updates — link in bio!"\n\n#foodtok #fyp #viral #foodie`;
}

function toGBPost(caption) {
    return caption.replace(/[#\ud800-\udfff]|[\u2000-\u3300]/gu, '').trim().substring(0, 300);
}

function copyEmbed() {
    const code = document.getElementById('embedCode').textContent;
    navigator.clipboard.writeText(code).then(() => toast('🔗 Embed code copied!', 'success'));
}

function addFeed(msg, type='info') {
    const feed = document.getElementById('activityFeed');
    const el   = document.createElement('div');
    el.className = 'feed-item feed-' + type;
    el.textContent = new Date().toLocaleTimeString() + ' — ' + msg;
    feed.insertBefore(el, feed.firstChild);
    if (feed.children.length > 60) feed.removeChild(feed.lastChild);
}

function toast(msg, type='info') {
    const c  = document.getElementById('toastContainer');
    const el = document.createElement('div');
    el.className   = 'toast toast-' + type;
    el.textContent = msg;
    c.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}
