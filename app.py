#!/usr/bin/env python3
"""
PostPilot Pro — Smart Content Hub
Write once → smart routing sends videos to video platforms,
text to text platforms, images to image platforms.
All from one page.
"""

import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv
from modules.post_generator import SocialMediaPostGenerator
from modules.post_scheduler import PostScheduler
from modules.analytics_client import Analytics
from modules.publisher import UniversalPublisher

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')

user_sessions = {}


# ── PAGES ───────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template('dashboard.html')

@app.route('/setup')
def setup():
    return render_template('setup.html')

@app.route('/generate')
def generate():
    return render_template('generate.html')

@app.route('/calendar')
def calendar():
    return render_template('calendar.html')

@app.route('/analytics')
def analytics_page():
    return render_template('analytics.html')

@app.route('/onboarding')
def onboarding():
    """First-run guided setup wizard (Phase 4 Session 6)."""
    return render_template('onboarding.html')


# ── CORE: UNIVERSAL PUSH ──────────────────────────────────────────────

@app.route('/api/push_all', methods=['POST'])
def api_push_all():
    data         = request.json
    uid          = data.get('user_id', 'default')
    tokens       = user_sessions.get(uid, {}).get('tokens', {})
    publisher    = UniversalPublisher(tokens)
    results      = publisher.push_all(
        caption      = data.get('caption', ''),
        content_type = data.get('content_type', 'text'),
        image_url    = data.get('image_url'),
        video_url    = data.get('video_url'),
        link_url     = data.get('link_url'),
        platforms    = data.get('platforms'),
        schedule_time= data.get('schedule_time'),
        web_data     = data.get('web_data'),
    )
    return jsonify({'success': True, 'results': results})


@app.route('/api/publish', methods=['POST'])
def api_publish():
    """
    Alias for /api/push_all used by the onboarding wizard first-post flow.
    Accepts: content_type, caption, platforms (list), image_url, video_url, link_url.
    """
    data      = request.json
    uid       = data.get('user_id', 'default')
    tokens    = user_sessions.get(uid, {}).get('tokens', {})
    publisher = UniversalPublisher(tokens)
    results   = publisher.push_all(
        caption      = data.get('caption', ''),
        content_type = data.get('content_type', 'text'),
        image_url    = data.get('image_url'),
        video_url    = data.get('video_url'),
        link_url     = data.get('link_url'),
        platforms    = data.get('platforms'),
    )
    return jsonify({'success': True, 'results': results})


# ── ONBOARDING SETUP ──────────────────────────────────────────────────

@app.route('/api/onboarding/setup', methods=['POST'])
def api_onboarding_setup():
    """
    Saves business info submitted at Step 1 of the onboarding wizard.
    Stores in user session and sets up the post generator with business context.

    Expected JSON:
        name         — Business name
        type         — Business type slug (food_truck, cafe, etc.)
        location     — City / location string
        hours        — Operating hours string
        prompt_time  — Morning prompt time (HH:MM, 24hr)
    """
    data = request.json or {}
    uid  = data.get('user_id', 'default')
    user_sessions.setdefault(uid, {})

    business_info = {
        'name':         data.get('name', ''),
        'type':         data.get('type', ''),
        'location':     data.get('location', ''),
        'hours':        data.get('hours', ''),
        'prompt_time':  data.get('prompt_time', '07:00'),
    }

    user_sessions[uid]['business'] = business_info

    # Wire up post generator with business context
    gen = user_sessions[uid].get('generator', SocialMediaPostGenerator())
    gen.setup_business(business_info)
    user_sessions[uid]['generator'] = gen

    # Persist to auth_manager DB for use across restarts
    try:
        from modules.auth_manager import save_token
        import json
        # Store business info as a pseudo-token so it survives restarts
        save_token(
            platform      = 'business_profile',
            access_token  = json.dumps(business_info),
            user_id       = uid,
        )
    except Exception:
        pass  # Non-fatal — session storage is the primary store

    return jsonify({'success': True, 'business': business_info})


# ── CONNECTION STATUS ───────────────────────────────────────────────

@app.route('/api/connection_status', methods=['POST'])
def api_connection_status():
    data   = request.json
    uid    = data.get('user_id', 'default')
    tokens = user_sessions.get(uid, {}).get('tokens', {})
    return jsonify({
        'success': True,
        'platforms': {
            'fb':  bool(tokens.get('facebook_token') and tokens.get('facebook_page_id')),
            'ig':  bool(tokens.get('instagram_token') and tokens.get('instagram_id')),
            'yt':  bool(tokens.get('youtube_token')),
            'tt':  True,  # script always works; full upload needs token
            'gb':  bool(tokens.get('google_token')),
            'web': True,  # always available via banner.json
        }
    })


# ── GENERATE / SCHEDULE / ANALYTICS ────────────────────────────────

@app.route('/api/setup_business', methods=['POST'])
def api_setup_business():
    data = request.json
    uid  = data.get('user_id', 'default')
    user_sessions.setdefault(uid, {})
    gen  = SocialMediaPostGenerator()
    gen.setup_business(data.get('business_info', {}))
    user_sessions[uid]['generator'] = gen
    return jsonify({'success': True})


@app.route('/api/setup_tokens', methods=['POST'])
def api_setup_tokens():
    data = request.json
    uid  = data.get('user_id', 'default')
    user_sessions.setdefault(uid, {})
    user_sessions[uid]['tokens'] = data.get('tokens', {})
    gen = user_sessions[uid].get('generator', SocialMediaPostGenerator())
    gen.setup_api_tokens(data.get('tokens', {}))
    user_sessions[uid]['generator'] = gen
    return jsonify({'success': True})


@app.route('/api/generate_weekly', methods=['POST'])
def api_generate_weekly():
    data = request.json
    uid  = data.get('user_id', 'default')
    gen  = user_sessions.get(uid, {}).get('generator', SocialMediaPostGenerator())
    return jsonify({'success': True, 'schedule': gen.generate_weekly_schedule()})


@app.route('/api/generate_post', methods=['POST'])
def api_generate_post():
    data     = request.json
    uid      = data.get('user_id', 'default')
    template = data.get('template', 'instagram_location')
    gen      = user_sessions.get(uid, {}).get('generator', SocialMediaPostGenerator())
    try:
        return jsonify({'success': True, 'post': gen.generate_post(template)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/schedule_post', methods=['POST'])
def api_schedule_post():
    data = request.json
    return jsonify(PostScheduler().schedule(data))


@app.route('/api/analytics', methods=['POST'])
def api_analytics():
    data    = request.json
    uid     = data.get('user_id', 'default')
    tokens  = user_sessions.get(uid, {}).get('tokens', {})
    token   = tokens.get('facebook_token') or data.get('access_token')
    page_id = tokens.get('facebook_page_id') or data.get('page_id')
    if not token or not page_id:
        return jsonify({'success': False, 'error': 'Facebook not connected', 'posts': [], 'total_posts': 0})
    return jsonify(Analytics(token, page_id).get_weekly_summary())


# ── OAUTH: META (Facebook + Instagram) ────────────────────────────

@app.route('/auth/facebook')
def auth_facebook():
    app_id       = os.getenv('FACEBOOK_APP_ID')
    redirect_uri = os.getenv('REDIRECT_URI', 'http://localhost:5000/auth/facebook/callback')
    scopes       = 'pages_manage_posts,pages_read_engagement,instagram_content_publish,instagram_basic'
    # Pass next/step through state param for onboarding redirect
    next_url = request.args.get('next', '/')
    step     = request.args.get('step', '2')
    session['oauth_next'] = next_url
    session['oauth_step'] = step
    session['oauth_platform'] = 'facebook'
    return redirect(f'https://www.facebook.com/v19.0/dialog/oauth?client_id={app_id}&redirect_uri={redirect_uri}&scope={scopes}')


@app.route('/auth/facebook/callback')
def auth_facebook_callback():
    import requests as req
    code       = request.args.get('code')
    app_id     = os.getenv('FACEBOOK_APP_ID')
    app_secret = os.getenv('FACEBOOK_APP_SECRET')
    redir      = os.getenv('REDIRECT_URI', 'http://localhost:5000/auth/facebook/callback')
    token      = req.get('https://graph.facebook.com/v19.0/oauth/access_token',
                         params={'client_id':app_id,'client_secret':app_secret,'redirect_uri':redir,'code':code}).json().get('access_token')
    page       = req.get('https://graph.facebook.com/v19.0/me/accounts', params={'access_token':token}).json().get('data',[{}])[0]
    page_id    = page.get('id'); page_token = page.get('access_token', token)
    ig_id      = req.get(f'https://graph.facebook.com/v19.0/{page_id}',
                         params={'fields':'instagram_business_account','access_token':page_token}).json().get('instagram_business_account',{}).get('id')
    uid = 'default'
    user_sessions.setdefault(uid, {})
    user_sessions[uid].setdefault('tokens', {}).update(
        facebook_token=page_token, facebook_page_id=page_id, instagram_token=page_token, instagram_id=ig_id)

    # Redirect back to onboarding if that's where we came from
    next_url  = session.pop('oauth_next', '/')
    step      = session.pop('oauth_step', '2')
    platform  = session.pop('oauth_platform', 'facebook')
    if next_url == '/onboarding':
        return redirect(f'/onboarding?connected={platform}&step={step}')
    return redirect(url_for('home'))


# ── OAUTH: GOOGLE ─────────────────────────────────────────────────

@app.route('/auth/google')
def auth_google():
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    redir     = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/auth/google/callback')
    scope     = 'https://www.googleapis.com/auth/business.manage https://www.googleapis.com/auth/youtube.upload'
    next_url  = request.args.get('next', '/')
    step      = request.args.get('step', '3')
    session['oauth_next'] = next_url
    session['oauth_step'] = step
    session['oauth_platform'] = 'google'
    return redirect(f'https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={redir}&response_type=code&scope={scope}&access_type=offline')


@app.route('/auth/google/callback')
def auth_google_callback():
    import requests as req
    code    = request.args.get('code')
    cid     = os.getenv('GOOGLE_CLIENT_ID'); csec = os.getenv('GOOGLE_CLIENT_SECRET')
    redir   = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/auth/google/callback')
    tokens  = req.post('https://oauth2.googleapis.com/token',
                       data={'code':code,'client_id':cid,'client_secret':csec,'redirect_uri':redir,'grant_type':'authorization_code'}).json()
    gtoken  = tokens.get('access_token')
    accts   = req.get('https://mybusinessaccountmanagement.googleapis.com/v1/accounts',
                      headers={'Authorization':f'Bearer {gtoken}'}).json()
    acct    = (accts.get('accounts') or [{}])[0].get('name','')
    locs    = req.get(f'https://mybusinessbusinessinformation.googleapis.com/v1/{acct}/locations',
                      headers={'Authorization':f'Bearer {gtoken}'}).json()
    loc_id  = (locs.get('locations') or [{}])[0].get('name','')
    uid = 'default'
    user_sessions.setdefault(uid, {})
    user_sessions[uid].setdefault('tokens', {}).update(
        google_token=gtoken, google_location_id=loc_id, youtube_token=gtoken)

    next_url = session.pop('oauth_next', '/')
    step     = session.pop('oauth_step', '3')
    platform = session.pop('oauth_platform', 'google')
    if next_url == '/onboarding':
        return redirect(f'/onboarding?connected={platform}&step={step}')
    return redirect(url_for('home'))


# ── OAUTH: TIKTOK ──────────────────────────────────────────────────

@app.route('/auth/tiktok')
def auth_tiktok():
    client_key = os.getenv('TIKTOK_CLIENT_KEY')
    redir      = os.getenv('TIKTOK_REDIRECT_URI', 'http://localhost:5000/auth/tiktok/callback')
    scope      = 'user.info.basic,video.upload,video.publish'
    next_url   = request.args.get('next', '/')
    step       = request.args.get('step', '4')
    session['oauth_next'] = next_url
    session['oauth_step'] = step
    session['oauth_platform'] = 'tiktok'
    return redirect(f'https://www.tiktok.com/v2/auth/authorize?client_key={client_key}&redirect_uri={redir}&response_type=code&scope={scope}')


@app.route('/auth/tiktok/callback')
def auth_tiktok_callback():
    import requests as req
    code   = request.args.get('code')
    ckey   = os.getenv('TIKTOK_CLIENT_KEY'); csec = os.getenv('TIKTOK_CLIENT_SECRET')
    redir  = os.getenv('TIKTOK_REDIRECT_URI', 'http://localhost:5000/auth/tiktok/callback')
    tokens = req.post('https://open.tiktokapis.com/v2/oauth/token/',
                      data={'client_key':ckey,'client_secret':csec,'code':code,'grant_type':'authorization_code','redirect_uri':redir},
                      headers={'Content-Type':'application/x-www-form-urlencoded'}).json()
    tt_token = tokens.get('access_token')
    uid = 'default'
    user_sessions.setdefault(uid, {})
    user_sessions[uid].setdefault('tokens', {}).update(tiktok_token=tt_token)

    next_url = session.pop('oauth_next', '/')
    step     = session.pop('oauth_step', '4')
    platform = session.pop('oauth_platform', 'tiktok')
    if next_url == '/onboarding':
        return redirect(f'/onboarding?connected={platform}&step={step}')
    return redirect(url_for('home'))


if __name__ == '__main__':
    print('🚀 PostPilot Pro — Smart Content Hub')
    print('🌐 Open: http://localhost:5000')
    app.run(debug=True, port=5000)
