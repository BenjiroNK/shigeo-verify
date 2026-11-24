"""Public pages for Shigeo verification: what we check, privacy, help form.

Plain HTML, no trackers, no outside scripts. Served by Shigeo's own web server.
"""
import html

SOURCE_URL = "https://github.com/"     # replaced by verify.py with the real repo link (VERIFY_SOURCE_URL)

STYLE = """*{box-sizing:border-box}body{margin:0;background:#0b0b10;color:#e8e8ee;font-family:system-ui,-apple-system,Segoe UI,sans-serif;
line-height:1.6}.w{max-width:760px;margin:0 auto;padding:32px 18px 60px}h1{font-size:26px;letter-spacing:1px;margin:0 0 6px}
h2{font-size:18px;margin:28px 0 8px;border-bottom:1px solid #2a2a35;padding-bottom:6px}.sub{color:#9a9aab;margin:0 0 18px}
.card{background:#000;border:2px solid #fff;padding:18px 20px;margin:16px 0}.no li::marker{content:"✗  ";color:#ff6b6b}
.yes li::marker{content:"•  ";color:#7dd3fc}ul{padding-left:22px;margin:6px 0}li{margin:6px 0}a{color:#7dd3fc}
.ar{direction:rtl;text-align:right;font-family:Tahoma,system-ui,sans-serif}.ar ul{padding-left:0;padding-right:22px}
nav{display:flex;flex-wrap:wrap;gap:14px;margin:0 0 22px;font-size:14px}nav a{color:#bbb;text-decoration:none;border-bottom:1px dotted #555}
label{display:block;margin:14px 0 6px;font-weight:600}input,select,textarea{width:100%;padding:10px;background:#111;color:#eee;
border:1px solid #444;font:inherit}textarea{min-height:120px}button{margin-top:18px;padding:12px 28px;font-size:16px;background:#fff;
color:#000;border:0;cursor:pointer;font-weight:700}.hp{position:absolute;left:-9999px}.small{font-size:13px;color:#8a8a9a}"""


def nav():
    src = f"<a href='{html.escape(SOURCE_URL)}' rel='noopener'>Source code</a>" if SOURCE_URL else ""
    return ("<nav><a href='/'>Home</a><a href='/info'>What we check</a><a href='/privacy'>Privacy</a>"
            f"<a href='/help'>Need help?</a>{src}</nav>")


def page(title, body):
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)} - Gaster's Ship</title><style>{STYLE}</style></head>"
            f"<body><div class='w'>{nav()}{body}</div></body></html>")


def home():
    return page("Verification", """
<h1>GASTER'S SHIP · VERIFICATION</h1>
<p class='sub'>This is Shigeo, the Gaster's Ship server's own verify bot. It stops alt accounts, bots and VPN raiders.
It never asks for your password or Discord login.</p>
<div class='card'>To verify, go back to Discord and press <b>Verify (Shigeo)</b> in #verification. You'll get a personal link.</div>
<p><a href='/info'>What does it check?</a> · <a href='/privacy'>Privacy</a> · <a href='/help'>Verify not working?</a></p>""")


def info():
    src = (f"<p>Want proof? The full verify code is public: <a href='{html.escape(SOURCE_URL)}' rel='noopener'>"
           f"{html.escape(SOURCE_URL)}</a></p>") if SOURCE_URL else ""
    src_ar = (f"<p>الكود كامل منشور للجميع: <a href='{html.escape(SOURCE_URL)}' rel='noopener'>هنا</a></p>") if SOURCE_URL else ""
    return page("What we check", f"""
<h1>What Shigeo checks</h1>
<p class='sub'>Short version: it checks whether you're a real person on a real device without a VPN. That's it.</p>

<div class='card'><b>Shigeo NEVER:</b>
<ul class='no'>
<li>asks for your Discord password, email or login</li>
<li>gets your Discord token, DMs or account access</li>
<li>reads your files, camera, microphone or location</li>
<li>makes you download anything</li>
</ul></div>

<h2>What it does check, and why</h2>
<ul class='yes'>
<li><b>Your IP address:</b> to spot VPNs, proxies and servers. It's checked by ip-api.com, proxycheck.io and
IPQualityScore (they only see the IP, nothing else). <b>We never save your real IP</b>. We only keep a scrambled code
(a salted hash) that can't be turned back into the IP.</li>
<li><b>Basic device info:</b> graphics card name, screen size, timezone, language and number of CPU cores.
This catches virtual machines and one person making many accounts. It's also saved only as a scrambled code.</li>
<li><b>A random browser ID:</b> a random number saved in your browser, so one browser can't verify lots of accounts.</li>
<li><b>Your Discord account age and profile picture:</b> already public on Discord. Very new accounts get a quick staff check.</li>
</ul>

<h2>Who sees it</h2>
<p>Only Shigeo. If your verify needs a human look, staff see a short reason like "VPN detected" or "same device as @someone".
<b>Staff never see your IP</b> or your device details.</p>

<h2>How long it's kept, and deleting it</h2>
<p>The scrambled codes are kept so alts can still be caught later. Want yours deleted? Ask in <b>#support</b> and staff
will remove it with one command.</p>
{src}

<div class='ar'>
<h2>شيقيو يفحص إيش؟</h2>
<p>باختصار: يتأكد إنك شخص حقيقي على جهاز حقيقي وبدون VPN. بس كذا.</p>
<div class='card'><b>شيقيو أبداً ما:</b>
<ul class='no'>
<li>يطلب باسوورد ديسكورد أو إيميلك أو تسجيل دخول</li>
<li>ياخذ توكن حسابك أو رسائلك أو يدخل حسابك</li>
<li>يشوف ملفاتك أو الكاميرا أو المايك أو موقعك</li>
<li>يخليك تحمّل أي شي</li>
</ul></div>
<ul class='yes'>
<li><b>الـ IP حقك:</b> عشان نكشف الـ VPN والبروكسي. <b>ما نحفظ الـ IP الحقيقي أبداً</b>، بس رمز مشفّر ما ينرجع.</li>
<li><b>معلومات بسيطة عن الجهاز:</b> اسم كرت الشاشة، حجم الشاشة، المنطقة الزمنية واللغة، عشان نكشف الأجهزة الوهمية والحسابات الثانية. تنحفظ كرمز مشفّر بس.</li>
<li><b>رقم عشوائي للمتصفح:</b> عشان متصفح واحد ما يوثّق حسابات كثيرة.</li>
<li><b>عمر حسابك وصورتك في ديسكورد:</b> معلومات عامة أصلاً.</li>
</ul>
<p>الإدارة ما تشوف الـ IP أو معلومات جهازك، بس سبب قصير مثل "VPN detected". تبي نحذف بياناتك؟ اطلب في <b>#support</b>.</p>
{src_ar}
</div>""")


def privacy():
    src = f"<a href='{html.escape(SOURCE_URL)}' rel='noopener'>public source code</a>" if SOURCE_URL else "source code"
    return page("Privacy", f"""
<h1>Privacy: Shigeo verification</h1>
<p class='sub'>For the Gaster's Ship Discord server (discord.gg/gstr). Run by the Gaster's Ship staff team.
The Benjiro bot has its own policy at <a href='https://benjironk.com/privacy'>benjironk.com/privacy</a>.</p>

<h2>What we collect</h2>
<ul class='yes'>
<li>Your Discord user ID (to give you the Verified role)</li>
<li>A salted hash of your IP address, of a device fingerprint, and of a random browser ID</li>
<li>Your Discord account creation date and whether you have a profile picture (public)</li>
</ul>

<h2>What we don't collect</h2>
<ul class='no'>
<li>Raw IP addresses (only kept in memory for a few seconds while the check runs)</li>
<li>Passwords, Discord tokens, emails, messages, files, location, camera or microphone</li>
<li>Any tracking or ads. This site loads no outside scripts.</li>
</ul>

<h2>Why</h2>
<p>To stop alt accounts, bots, raids and ban evasion in the server. Nothing is sold or shared for marketing.</p>

<h2>Who else sees data</h2>
<p>To check for VPNs, your IP (only the IP) is sent to <b>ip-api.com</b>, <b>proxycheck.io</b> and <b>IPQualityScore</b>
each time you verify. The site is served through <b>Cloudflare</b>. Discord staff with the Gaster Crew role see a short
reason when a verify needs review, never your IP or device details.</p>

<h2>Keeping and deleting</h2>
<p>Hashes are kept while the server exists so returning alts can be caught. Ask in <b>#support</b> (or use the
<a href='/help'>help form</a>) and staff will delete yours. One-time verify links expire after 15 minutes.</p>

<h2>Check it yourself</h2>
<p>Everything above can be checked in the {src}.</p>
<p class='small'>Last updated November 2026.</p>""")


def help_form(msg=""):
    note = f"<div class='card'>{msg}</div>" if msg else ""
    return page("Need help?", f"""
<h1>Verify not working?</h1>
<p class='sub'>Send this and a staff member will help you. Don't put passwords or personal info here.</p>
{note}
<form method='post' action='/help'>
<label for='u'>Your Discord username</label>
<input id='u' name='user' maxlength='40' required placeholder='e.g. gaster_fan'>
<label for='p'>What happened?</label>
<select id='p' name='problem' required>
<option value='link'>The link says expired / doesn't open</option>
<option value='vpn'>It says VPN detected but I don't use one</option>
<option value='blocked'>It says blocked</option>
<option value='review'>It says "Almost there" and I'm still waiting</option>
<option value='scared'>I'm not sure it's safe</option>
<option value='other'>Something else</option>
</select>
<label for='m'>Anything else? (optional)</label>
<textarea id='m' name='msg' maxlength='500' placeholder='What do you see on screen?'></textarea>
<input class='hp' name='website' tabindex='-1' autocomplete='off' aria-hidden='true'>
<button type='submit'>Send to staff</button>
</form>
<div class='ar'><p class='small'>التوثيق ما يشتغل؟ اكتب يوزرك واختر المشكلة واضغط Send، والإدارة بتساعدك.</p></div>""")


PROBLEMS = {"link": "Link expired / won't open", "vpn": "Says VPN but no VPN", "blocked": "Says blocked",
            "review": "Waiting on staff review", "scared": "Not sure it's safe", "other": "Something else"}
