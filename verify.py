"""Shigeo verification - stronger backup for the Security bot.

Button (or /verify) -> personal one-time link -> Shigeo's own web page.
The page runs a small check in the browser, then Shigeo decides:

BLOCK (try again without it):
  * VPN / proxy / Tor / datacenter IP (proxycheck.io + IPQualityScore, ip-api.com only as backup)
  * automated / headless browser (webdriver, HeadlessChrome, fake clicks)
  * request didn't come from the real page (hidden proof-of-work failed)
  * virtual machine graphics (VMware, VirtualBox, QEMU, Parallels, Hyper-V, UTM...)
STAFF REVIEW (Approve / Ignore buttons in the staff channel):
  * same browser as another member (long-lived browser ID = alt sign)
  * browser looks headless, or says Windows/Mac but the device isn't
  * finished too fast for a human, or the IP changed mid-check
  * IP check failed or proxycheck risk score is high
  * Discord flagged the account as a likely spammer
  * software-only graphics (llvmpipe / SwiftShader / Basic Render) or hidden graphics
  * browser timezone doesn't match the IP's timezone (hidden VPN sign)
  * same device as another member (browser fingerprint)
  * same home internet as another member (not counted on mobile data)
  * Discord account younger than 7 days, or no avatar and younger than 30 days
  * JavaScript turned off (we can't check the device)
PASS -> Verified right away.

Privacy: nothing raw is stored, not even in memory. IPs and fingerprints are kept only as salted hashes.
Only the IP is sent to the VPN-check services. Codes of people who left 90+ days ago are deleted
automatically (banned people are kept). Pages load no outside scripts and send strict privacy headers.
Staff can also run /verify user:@someone to verify a person by hand.
"""
import asyncio
import datetime as dt
import hashlib
import html
import ipaddress
import json
import logging
import os
import re
import secrets
import time

import aiohttp
import discord
from aiohttp import web
from discord import app_commands

import verify_pages as vp

log = logging.getLogger("verify")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "verify.json")
PORT = int(os.getenv("SERVER_PORT", "15387"))
PUBLIC = os.getenv("VERIFY_URL", f"http://78.154.103.34:{PORT}")   # WispByte public address
vp.SOURCE_URL = os.getenv("VERIFY_SOURCE_URL", "https://github.com/BenjiroNK/shigeo-verify")
# Only trust Cloudflare's "real visitor IP" header when the request really comes from Cloudflare.
CF_NETS = [ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
    "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22", "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32",
    "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32")]


def client_ip(request):
    remote = request.remote or "?"
    try:
        addr = ipaddress.ip_address(remote)
        if getattr(addr, "ipv4_mapped", None):
            addr = addr.ipv4_mapped
        if any(addr in n for n in CF_NETS):
            return request.headers.get("CF-Connecting-IP") or remote
    except ValueError:
        pass
    return remote
REVIEW_CHANNEL = int(os.getenv("VERIFY_REVIEW_CHANNEL", "1536169178812260392"))  # staff verify-review channel
REVIEW_PING_ROLE = "Gaster Crew"
VERIFIED, UNVERIFIED = "Verified", "Unverified"
MIN_AGE_DAYS = 7
NO_AVATAR_AGE_DAYS = 30
TOKEN_TTL = 15 * 60
PRUNE_DAYS = 90         # codes of people who left are deleted after this (not banned people)
POW_BITS = 18            # hidden proof-of-work, ~0.2-1 s on a phone
MIN_SECONDS = 2.0        # faster than this from page open to submit = not a human
HEADLESS_UA = re.compile(r"headlesschrome|phantomjs|headless|puppeteer|playwright|selenium|electron/", re.I)
# Named virtual machine graphics = block. Software-only graphics = staff review
# (real PCs with broken / disabled GPU drivers can show these too).
VM_WORDS = re.compile(r"vmware|virtualbox|vbox|qemu|parallels|hyper-v|virgl|bochs|cirrus logic|red hat|qxl|"
                      r"citrix|\bxen\b|virtio|\butm\b|apple paravirtual", re.I)
SOFT_GL = re.compile(r"microsoft basic render|llvmpipe|swiftshader|mesa offscreen|softpipe", re.I)

STYLE = """body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0b0b10;color:#eee;
font-family:system-ui,sans-serif}.c{max-width:380px;margin:16px;padding:28px;border:2px solid #fff;background:#000;text-align:center}
h1{font-size:20px;letter-spacing:2px;margin:0 0 12px}p{color:#bbb;line-height:1.5}
button{margin-top:16px;padding:12px 28px;font-size:16px;background:#fff;color:#000;border:0;cursor:pointer;font-weight:700}
button:disabled{opacity:.5}a{color:#7dd3fc}.l{font-size:13px;margin-top:18px}"""

SIMPLE = ("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
          "<title>Gaster's Ship - Verify</title><style>" + STYLE + "</style></head><body><div class='c'><h1>{t}</h1><p>{b}</p><p class='l'><a href='/info'>What we check</a> · <a href='/privacy'>Privacy</a> · "
          "<a href='/help'>Help</a></p></div></body></html>")

# The check page: collects device signals in the browser and posts them back.
CHECK = ("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         "<title>Gaster's Ship - Verify</title><style>" + STYLE + "</style></head><body><div class='c'>"
         "<h1 id='h'>GASTER'S SHIP</h1><p id='p'>Turn off any VPN or proxy, then press the button.</p>"
         "<button id='b'>I'm a real person - verify me</button>"
         "<p class='l'><a href='/info' target='_blank'>What does this check?</a> · <a href='/privacy' target='_blank'>Privacy</a>"
         " · <a href='/help' target='_blank'>Help</a></p>"
         "<noscript><p>JavaScript is off. <form method='post'><button>Verify without checks (staff will review)</button></form></p></noscript>"
         "</div><script>"
         "const N='{N}',D={D};let ptr='',t0=performance.now();"
         "addEventListener('pointerdown',e=>{ptr=e.pointerType||'?'},true);"
         "function h(s){let a=0xdeadbeef,b=0x41c6ce57;for(let i=0;i<s.length;i++){const c=s.charCodeAt(i);"
         "a=Math.imul(a^c,2654435761);b=Math.imul(b^c,1597334677);}a=Math.imul(a^(a>>>16),2246822507)^Math.imul(b^(b>>>13),3266489909);"
         "b=Math.imul(b^(b>>>16),2246822507)^Math.imul(a^(a>>>13),3266489909);return(4294967296*(2097151&b)+(a>>>0)).toString(16);}"
         "function sig(){const o={};try{o.tz=Intl.DateTimeFormat().resolvedOptions().timeZone||''}catch(e){o.tz=''}"
         "o.wd=!!navigator.webdriver;o.cores=navigator.hardwareConcurrency||0;o.mem=navigator.deviceMemory||0;"
         "o.plat=navigator.platform||'';o.langs=(navigator.languages||[]).join(',');o.touch=navigator.maxTouchPoints||0;"
         "o.scr=screen.width+'x'+screen.height+'x'+screen.colorDepth;o.gl='';"
         "try{const g=document.createElement('canvas').getContext('webgl');const d=g.getExtension('WEBGL_debug_renderer_info');"
         "o.gl=(d?g.getParameter(d.UNMASKED_VENDOR_WEBGL)+' | '+g.getParameter(d.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER))||''}catch(e){}"
         "let cv='';try{const c=document.createElement('canvas');c.width=240;c.height=60;const x=c.getContext('2d');"
         "x.textBaseline='top';x.font='16px Arial';x.fillStyle='#f60';x.fillRect(100,1,62,20);x.fillStyle='#069';"
         "x.fillText('Gaster ship \\u2615 10e5',2,15);x.fillStyle='rgba(102,204,0,0.7)';x.fillText('Gaster ship \\u2615 10e5',4,17);cv=c.toDataURL()}catch(e){}"
         "o.fp=h([cv,o.gl,o.scr,o.cores,o.mem,o.plat,o.tz,o.langs,o.touch].join('|'));"
         "o.ua=navigator.userAgent||'';o.pl=(navigator.plugins||[]).length;o.chr=!!window.chrome;"
         "o.ow=window.outerWidth||0;o.oh=window.outerHeight||0;o.bid=bid();return o}"
         "function bid(){let b='';try{b=localStorage.getItem('gs_bid')||''}catch(e){}"
         "if(!b){const m=document.cookie.match(/gs_bid=([a-f0-9]{32})/);if(m)b=m[1]}"
         "if(!b){const a=new Uint8Array(16);crypto.getRandomValues(a);b=Array.from(a,x=>x.toString(16).padStart(2,'0')).join('')}"
         "try{localStorage.setItem('gs_bid',b)}catch(e){}"
         "document.cookie='gs_bid='+b+';max-age=315360000;path=/;SameSite=Lax';return b}"
         "function pow(){const m=Math.pow(2,D);for(let i=0;;i++){if(parseInt(h(N+':'+i),16)%m===0)return i}}"
         "document.getElementById('b').onclick=async function(ev){this.disabled=true;document.getElementById('p').textContent='Checking...';"
         "try{const o=sig();o.tr=ev.isTrusted;o.ptr=ptr;o.dt=Math.round(performance.now()-t0);"
         "await new Promise(r=>setTimeout(r,30));o.pow=pow();"
         "const r=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)});"
         "const j=await r.json();document.getElementById('h').textContent=j.title;document.getElementById('p').innerHTML=j.body;"
         "this.style.display='none'}catch(e){document.getElementById('p').textContent='Something went wrong, try again from Discord.'}};"
         "</script></body></html>")

EXPIRED = ("Link expired", "Go back to Discord and press <b>Verify (Shigeo)</b> again for a new link.")


def cyrb53(s):
    """Same 53-bit hash as h() in the page, used to check the proof-of-work."""
    m = 0xFFFFFFFF
    imul = lambda x, y: (x * y) & m
    a, b = 0xDEADBEEF, 0x41C6CE57
    for ch in s:
        c = ord(ch)
        a, b = imul(a ^ c, 2654435761), imul(b ^ c, 1597334677)
    a = imul(a ^ (a >> 16), 2246822507) ^ imul(b ^ (b >> 13), 3266489909)
    b = imul(b ^ (b >> 16), 2246822507) ^ imul(a ^ (a >> 13), 3266489909)
    return 4294967296 * (2097151 & b) + a


def pow_ok(nonce, answer):
    try:
        n = int(answer)
    except (TypeError, ValueError):
        return False
    return 0 <= n < 2 ** 32 and cyrb53(f"{nonce}:{n}") % (2 ** POW_BITS) == 0


def platform_mismatch(ua, plat):
    ua, plat = ua.lower(), plat.lower()
    if "windows nt" in ua and plat and not plat.startswith("win"):
        return True
    if "macintosh" in ua and "iphone" not in ua and plat and not (plat.startswith("mac") or plat.startswith("ip")):
        return True
    return False


def html_page(t, b):
    return web.Response(text=SIMPLE.replace("{t}", t).replace("{b}", b), content_type="text/html")


class ShigeoVerify:
    def __init__(self, bot, guild_id):
        self.bot = bot
        self.guild_id = guild_id
        self.tokens = {}
        self.help_hits = {}
        self.runner = None
        try:
            with open(DATA) as f:
                self.data = json.load(f)
        except Exception:
            self.data = {}
        self.data.setdefault("salt", secrets.token_hex(16))
        self.data.setdefault("ips", {})
        self.data.setdefault("fps", {})
        self.data.setdefault("bids", {})
        self.data.setdefault("seen", {})
        self._save()

    # ------------------------------------------------------------ helpers
    def guild(self):
        gid = self.guild_id() if callable(self.guild_id) else self.guild_id
        return self.bot.get_guild(gid)

    def _save(self):
        try:
            os.makedirs(os.path.dirname(DATA), exist_ok=True)
            with open(DATA, "w") as f:
                json.dump(self.data, f)
        except Exception as exc:
            log.warning("verify save failed: %s", exc)

    def _hash(self, value):
        return hashlib.sha256((self.data["salt"] + str(value)).encode()).hexdigest()[:24]

    def _remember(self, table, key, uid):
        ids = self.data[table].setdefault(key, [])
        if str(uid) not in ids:
            ids.append(str(uid))

    def _others(self, g, table, key, uid):
        ids = [int(u) for u in self.data[table].get(key, []) if int(u) != uid]
        return [m for m in (g.get_member(u) for u in ids) if m]

    def link_for(self, member, test=False):
        now = time.time()
        self.tokens = {t: v for t, v in self.tokens.items() if v["exp"] > now}
        tok = secrets.token_urlsafe(16)
        self.tokens[tok] = {"uid": member.id, "exp": now + TOKEN_TTL, "test": test,
                            "nonce": secrets.token_urlsafe(12), "served": None, "sip": None}
        return f"{PUBLIC}/v/{tok}"

    async def give(self, member, reason):
        g = member.guild
        ver, unv = discord.utils.get(g.roles, name=VERIFIED), discord.utils.get(g.roles, name=UNVERIFIED)
        if ver and ver not in member.roles:
            await member.add_roles(ver, reason=reason)
        if unv and unv in member.roles:
            await member.remove_roles(unv, reason=reason)

    async def ip_info(self, ip):
        """Ask VPN-check services about the IP. Only the IP is sent, always over HTTPS when possible.

        proxycheck.io (HTTPS) is the main check, IPQualityScore (HTTPS) is added when IPQS_KEY is set,
        and ip-api.com (plain HTTP, free tier) is only used as a backup if proxycheck can't answer.
        Never raises, and never logs the IP or API keys.
        """
        info = {"vpn": False, "country": "?", "tz": "", "mobile": False, "why": [], "failed": False, "risk": 0}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as s:
                got_geo = False
                key = os.getenv("PROXYCHECK_KEY", "")   # set in .env for 1,000 checks a day (works without, 100/day)
                q = f"key={key}&" if key else ""
                try:
                    async with s.get(f"https://proxycheck.io/v2/{ip}?{q}vpn=1&asn=1&risk=1") as r:
                        pj = await r.json(content_type=None)
                    p = pj.get(ip, {})
                    if p:
                        typ = str(p.get("type", ""))
                        if p.get("proxy") == "yes":
                            info["why"].append(f"proxycheck: {typ or 'proxy'}")
                        elif "hosting" in typ.lower():
                            info["why"].append("datacenter / server IP")
                        info["risk"] = int(p.get("risk", 0) or 0)
                        info["mobile"] = typ.lower() == "wireless"
                        if p.get("isocode"):
                            info.update(country=p["isocode"], tz=p.get("timezone", ""))
                            got_geo = True
                except Exception as exc:
                    log.warning("proxycheck failed: %s", type(exc).__name__)
                if not got_geo:                           # backup only
                    try:
                        async with s.get(f"http://ip-api.com/json/{ip}?fields=status,proxy,hosting,mobile,countryCode,timezone") as r:
                            j = await r.json(content_type=None)
                        if j.get("status") != "success":
                            info["failed"] = True
                        if j.get("proxy"):
                            info["why"].append("proxy/VPN IP")
                        if j.get("hosting"):
                            info["why"].append("datacenter / server IP")
                        info.update(country=j.get("countryCode", "?"), tz=j.get("timezone", ""), mobile=bool(j.get("mobile")))
                    except Exception as exc:
                        info["failed"] = True
                        log.warning("backup IP check failed: %s", type(exc).__name__)
                ipqs = os.getenv("IPQS_KEY", "")         # IPQualityScore, 1,000 free checks a month
                if ipqs:
                    try:
                        params = {"strictness": "1", "allow_public_access_points": "true"}
                        async with s.get(f"https://ipqualityscore.com/api/json/ip/{ipqs}/{ip}", params=params) as r:
                            q = await r.json(content_type=None)
                        if q.get("success"):
                            if q.get("tor") or q.get("active_tor"):
                                info["why"].append("IPQS: Tor")
                            elif q.get("vpn") or q.get("active_vpn"):
                                info["why"].append("IPQS: VPN")
                            elif q.get("proxy") and int(q.get("fraud_score", 0) or 0) >= 75:
                                info["why"].append("IPQS: proxy")
                            info["ipqs_proxy"] = bool(q.get("proxy"))
                            info["ipqs_score"] = int(q.get("fraud_score", 0) or 0)
                            info["ipqs_bot"] = bool(q.get("bot_status"))
                            info["mobile"] = info["mobile"] or bool(q.get("mobile"))
                        else:
                            log.warning("IPQS said no (out of credits?)")
                    except Exception as exc:
                        log.warning("IPQS failed: %s", type(exc).__name__)
        except Exception as exc:
            info["failed"] = True
            log.warning("IP checks failed: %s", type(exc).__name__)
        info["vpn"] = bool(info["why"])
        return info

    # ------------------------------------------------------------ web
    async def start(self):
        @web.middleware
        async def privacy_headers(request, handler):
            resp = await handler(request)
            resp.headers["Referrer-Policy"] = "no-referrer"
            resp.headers["X-Frame-Options"] = "DENY"
            resp.headers["X-Content-Type-Options"] = "nosniff"
            resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
            resp.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                                       "style-src 'unsafe-inline'; img-src 'self' data:; "
                                                       "connect-src 'self'; form-action 'self'; frame-ancestors 'none'")
            return resp

        app = web.Application(client_max_size=64 * 1024, middlewares=[privacy_headers])
        page = lambda fn: (lambda r: web.Response(text=fn(), content_type="text/html"))
        app.router.add_get("/", page(vp.home))
        app.router.add_get("/info", page(vp.info))
        app.router.add_get("/privacy", page(vp.privacy))
        app.router.add_get("/help", page(vp.help_form))
        app.router.add_post("/help", self.post_help)
        app.router.add_get("/v/{tok}", self.get_page)
        app.router.add_post("/v/{tok}", self.post_page)
        self.runner = web.AppRunner(app, access_log=None)        # no request log = no IPs in the console
        await self.runner.setup()
        await web.TCPSite(self.runner, "0.0.0.0", PORT).start()
        log.info("Verify page running on port %s (%s)", PORT, PUBLIC)
        asyncio.create_task(self.prune_loop())

    async def get_page(self, request):
        tok = request.match_info["tok"]
        e = self.tokens.get(tok)
        if not e or e["exp"] < time.time():
            return html_page(*EXPIRED)
        e["served"] = e["served"] or time.time()
        e["sip"] = e["sip"] or self._hash("s:" + client_ip(request))
        page = CHECK.replace("{N}", e["nonce"]).replace("{D}", str(POW_BITS))
        return web.Response(text=page, content_type="text/html", headers={"Cache-Control": "no-store"})

    async def post_page(self, request):
        is_json = request.content_type == "application/json"

        def reply(t, b):
            return web.json_response({"title": t, "body": b}) if is_json else html_page(t, b)

        tok = request.match_info["tok"]
        entry = self.tokens.pop(tok, None)
        if not entry or entry["exp"] < time.time():
            return reply(*EXPIRED)
        test = entry["test"]
        g = self.guild()
        member = g.get_member(entry["uid"]) if g else None
        if member is None:
            return reply("Not found", "You need to be in Gaster's Ship first.")
        if not test and any(r.name == VERIFIED for r in member.roles):
            return reply("Already verified", "You're already verified. Enjoy the ship!")

        sig = {}
        if is_json:
            try:
                sig = await request.json()
            except Exception:
                sig = {}
            if not isinstance(sig, dict):
                sig = {}
        ip = client_ip(request)
        ua = str(sig.get("ua", ""))[:300]
        info = await self.ip_info(ip)

        # ---- hard blocks
        block = None
        if is_json and not pow_ok(entry["nonce"], sig.get("pow")):
            block = ("Blocked", "Your browser didn't finish the check. Open the link in your normal browser and press the button.",
                     "proof-of-work missing/wrong (forged request)")
        elif sig.get("wd") or HEADLESS_UA.search(ua):
            block = ("Blocked", "Automated browsers can't verify. Use your normal browser.", "automated / headless browser")
        elif VM_WORDS.search(str(sig.get("gl", ""))[:200]):
            block = ("Virtual machine detected", "Verification doesn't work from a virtual machine. "
                     "Open the link on your real phone or PC.", f"virtual machine graphics: {str(sig.get('gl'))[:80]}")
        elif is_json and sig.get("tr") is not True:
            block = ("Blocked", "Please press the button yourself.", "fake (script) click")
        elif info["vpn"]:
            block = ("VPN detected", "Turn off your VPN / proxy (and any private relay), then press "
                                     "<b>Verify (Shigeo)</b> in Discord again for a new link.", ", ".join(info["why"]))

        # ---- things that need a human look
        reasons = []
        gl = str(sig.get("gl", ""))[:200]
        if not is_json:
            reasons.append("verified with JavaScript off (device not checked)")
        if info["failed"]:
            reasons.append("couldn't check the IP (lookup failed) - treat with care")
        if info["risk"] >= 66:
            reasons.append(f"proxycheck risk score {info['risk']}/100")
        if info.get("ipqs_score", 0) >= 85:
            reasons.append(f"IPQS fraud score {info['ipqs_score']}/100")
        if info.get("ipqs_proxy") and not info["vpn"]:
            reasons.append("IPQS thinks this might be a proxy (low score, so not blocked)")
        if info.get("ipqs_bot"):
            reasons.append("IPQS: this IP was recently used by bots")
        if gl and SOFT_GL.search(gl):
            reasons.append(f"software-only graphics (VM or no GPU driver): `{gl[:80]}`")
        if is_json and not gl:
            reasons.append("graphics info hidden (WebGL blocked - VM / privacy browser sign)")
        tz = str(sig.get("tz", ""))[:60]
        if tz and info["tz"] and tz != info["tz"]:
            reasons.append(f"timezone mismatch: browser `{tz}` vs IP `{info['tz']}` (VPN sign)")
        if is_json:
            desktop_chrome = "chrome/" in ua.lower() and "mobile" not in ua.lower() and not sig.get("touch")
            if desktop_chrome and (not sig.get("chr") or sig.get("pl") == 0):
                reasons.append("browser looks headless (Chrome with no plugins / no chrome object)")
            if sig.get("ow") == 0 or sig.get("oh") == 0:
                reasons.append("browser window has no size (headless sign)")
            if platform_mismatch(ua, str(sig.get("plat", ""))):
                reasons.append(f"browser says one system but device is `{str(sig.get('plat'))[:30]}` (spoofed browser)")
        took = time.time() - (entry["served"] or time.time())
        if is_json and took < MIN_SECONDS:
            reasons.append(f"finished in {took:.1f}s (too fast for a human)")
        if entry["sip"] and entry["sip"] != self._hash("s:" + ip):
            reasons.append("IP changed between opening the page and pressing the button")
        if getattr(member.public_flags, "spammer", False):
            reasons.append("Discord flagged this account as a likely spammer")

        ip_key = self._hash(ip)
        fp = str(sig.get("fp", ""))[:40]
        fp_key = self._hash(fp) if fp else None
        bid = str(sig.get("bid", ""))
        bid_key = self._hash("b:" + bid) if re.fullmatch(r"[a-f0-9]{32}", bid) else None
        same_browser = self._others(g, "bids", bid_key, member.id) if bid_key else []
        same_device = self._others(g, "fps", fp_key, member.id) if fp_key else []
        same_net = [] if info["mobile"] else self._others(g, "ips", ip_key, member.id)
        if same_browser:
            reasons.append("SAME BROWSER as " + ", ".join(m.mention for m in same_browser[:5]))
        if same_device:
            reasons.append("SAME DEVICE as " + ", ".join(m.mention for m in same_device[:5]))
        if same_net:
            reasons.append("same home internet as " + ", ".join(m.mention for m in same_net[:5]))

        age = (dt.datetime.now(dt.timezone.utc) - member.created_at).days
        if age < MIN_AGE_DAYS:
            reasons.append(f"Discord account is only {age} day(s) old")
        elif member.avatar is None and age < NO_AVATAR_AGE_DAYS:
            reasons.append(f"no profile picture and account is {age} days old")

        # ---- staff test: show what would happen, change nothing
        if test:
            if block:
                verdict = f"⛔ WOULD BLOCK: {block[2]}"
            elif reasons:
                verdict = "🛂 WOULD GO TO STAFF REVIEW"
            else:
                verdict = "✅ WOULD PASS"
            extra = "<br>".join("• " + html.escape(r) for r in reasons) or "no flags"
            log.info("Verify TEST by %s: %s | %s", member, verdict, "; ".join(reasons))
            return reply("Test result", f"<b>{verdict}</b><br><br>{extra}<br><br>Country {info['country']}"
                                        f"{' · mobile' if info['mobile'] else ''} · risk {info['risk']}"
                                        f" · IPQS {info.get('ipqs_score', 'off')} · {took:.1f}s"
                                        "<br><small>Test only: nothing was saved or changed.</small>")

        if block:
            log.info("Verify blocked for %s: %s", member, block[2])
            return reply(block[0], block[1])

        self._remember("ips", ip_key, member.id)
        if fp_key:
            self._remember("fps", fp_key, member.id)
        if bid_key:
            self._remember("bids", bid_key, member.id)
        self.data["seen"][str(member.id)] = int(time.time())
        self._save()

        if reasons:
            await self.send_review(member, reasons, info)
            return reply("Almost there", "Your account needs a quick check by staff. "
                                         "You'll get access as soon as a mod approves you.")
        try:
            await self.give(member, "Shigeo verification passed")
        except discord.HTTPException as exc:
            log.warning("verify give failed: %s", exc)
            return reply("Something went wrong", "Couldn't give you the role. Ask a mod in #support.")
        log.info("Verified %s via Shigeo", member)
        return reply("Verified!", "Welcome aboard Gaster's Ship. Go back to Discord, you have access now.")

    async def post_help(self, request):
        def answer(msg):
            return web.Response(text=vp.help_form(msg), content_type="text/html")
        ip = self._hash("h:" + client_ip(request))      # rate limit by scrambled IP, kept in memory only
        now = time.time()
        hits = [t for t in self.help_hits.get(ip, []) if t > now - 3600]
        if len(hits) >= 3:
            return answer("You already sent a few. Staff will get to you soon. Please wait.")
        try:
            form = await request.post()
        except Exception:
            return answer("Something went wrong. Try again.")
        if form.get("website"):                       # hidden field only bots fill in
            return answer("✅ Sent! A staff member will help you soon. Check #support in Discord.")
        user = str(form.get("user", "")).strip()[:40]
        problem = vp.PROBLEMS.get(str(form.get("problem", "")), "Something else")
        msg = str(form.get("msg", "")).strip()[:500]
        if not user:
            return answer("Please put your Discord username.")
        hits.append(now)
        self.help_hits[ip] = hits
        ch = self.bot.get_channel(REVIEW_CHANNEL)
        g = self.guild()
        if ch is None or g is None:
            return answer("Staff channel not found. Ask in #support instead.")
        found = discord.utils.find(lambda m: m.name.lower() == user.lower().lstrip("@") or
                                   (m.global_name or "").lower() == user.lower(), g.members)
        e = discord.Embed(title="🆘 Verify help request", color=0x5865F2)
        e.add_field(name="User", value=(f"{found.mention} (`{found.name}`)" if found else f"`{discord.utils.escape_markdown(user)}` (not found in server)"), inline=False)
        e.add_field(name="Problem", value=problem, inline=False)
        if msg:
            e.add_field(name="Message", value=discord.utils.escape_mentions(msg)[:1000], inline=False)
        if found and any(r.name == VERIFIED for r in found.roles):
            e.set_footer(text="They already have Verified")
        crew = discord.utils.get(g.roles, name=REVIEW_PING_ROLE)
        await ch.send(content=crew.mention if crew else None, embed=e,
                      allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=[crew] if crew else False))
        return answer("✅ Sent! A staff member will help you soon. Check #support in Discord.")

    def forget(self, uid):
        n = 0
        for table in ("ips", "fps", "bids"):
            for key in list(self.data[table]):
                ids = self.data[table][key]
                if str(uid) in ids:
                    ids.remove(str(uid))
                    n += 1
                    if not ids:
                        del self.data[table][key]
        self.data["seen"].pop(str(uid), None)
        self._save()
        return n

    async def prune_loop(self):
        """Once a day: delete the saved codes of people who left the server 90+ days ago.
        Banned people are kept, so they can't come back on an alt."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                g = self.guild()
                if g:
                    try:
                        banned = {str(b.user.id) async for b in g.bans(limit=None)}
                    except discord.HTTPException:
                        banned = None
                    now = time.time()
                    users = {u for t in ("ips", "fps", "bids") for ids in self.data[t].values() for u in ids}
                    gone = 0
                    for uid in users:
                        if g.get_member(int(uid)):
                            self.data["seen"][uid] = int(now)          # still here: clock restarts
                            continue
                        if banned is None or uid in banned:
                            continue
                        seen = self.data["seen"].setdefault(uid, int(now))   # start the 90 days for old entries
                        if now - seen > PRUNE_DAYS * 86400:
                            self.forget(uid)
                            gone += 1
                    self._save()
                    if gone:
                        log.info("Verify privacy cleanup: deleted saved codes for %s people who left", gone)
            except Exception as exc:
                log.warning("verify cleanup failed: %s", type(exc).__name__)
            await asyncio.sleep(86400)

    async def send_review(self, member, reasons, info):
        ch = self.bot.get_channel(REVIEW_CHANNEL)
        if ch is None:
            return
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="Approve", style=discord.ButtonStyle.success, custom_id=f"sv_ok:{member.id}"))
        view.add_item(discord.ui.Button(label="Ignore", style=discord.ButtonStyle.secondary, custom_id=f"sv_no:{member.id}"))
        e = discord.Embed(title="🛂 Verify check needed", color=0xF0B232,
                          description=f"{member.mention} (`{member}`, {member.id}) tried to verify.\n"
                                      + "\n".join(f"• {r}" for r in reasons)
                                      + f"\nCountry: {info['country']}{' · mobile data' if info['mobile'] else ''}"
                                      + f" · Account made <t:{int(member.created_at.timestamp())}:R>")
        crew = discord.utils.get(member.guild.roles, name=REVIEW_PING_ROLE)
        await ch.send(content=crew.mention if crew else None, embed=e, view=view,
                      allowed_mentions=discord.AllowedMentions(everyone=False, users=False,
                                                               roles=[crew] if crew else False))

    # ------------------------------------------------------------ discord buttons
    async def on_interaction(self, inter: discord.Interaction):
        if inter.type != discord.InteractionType.component:
            return
        cid = (inter.data or {}).get("custom_id", "")
        if cid == "sv_start":
            if any(r.name == VERIFIED for r in getattr(inter.user, "roles", [])):
                return await inter.response.send_message("You're already verified!", ephemeral=True)
            url = self.link_for(inter.user)
            v = discord.ui.View()
            v.add_item(discord.ui.Button(label="Open verify page", url=url))
            return await inter.response.send_message(
                "Here's your personal link (works once, for 15 minutes). Turn off any VPN first.", view=v, ephemeral=True)
        if cid.startswith(("sv_ok:", "sv_no:")):
            if not inter.user.guild_permissions.manage_roles:
                return await inter.response.send_message("Only staff can do this.", ephemeral=True)
            uid = int(cid.split(":")[1])
            member = inter.guild.get_member(uid)
            if cid.startswith("sv_ok:") and member:
                await self.give(member, f"Verify approved by {inter.user}")
                note = f"✅ Approved by {inter.user.mention}"
            else:
                note = f"➖ Ignored by {inter.user.mention}" if member else "Member left the server."
            e = inter.message.embeds[0] if inter.message.embeds else discord.Embed()
            e.add_field(name="Result", value=note, inline=False)
            await inter.response.edit_message(embed=e, view=None)


def build_commands(sv: ShigeoVerify):
    @app_commands.command(name="verify", description="Verify yourself (or staff: verify someone by hand)")
    @app_commands.describe(user="Staff only: verify this person right away")
    @app_commands.guild_only()
    async def verify_cmd(inter: discord.Interaction, user: discord.Member = None):
        if user is not None:
            if not inter.user.guild_permissions.manage_roles:
                return await inter.response.send_message("Only staff can verify other people.", ephemeral=True)
            await sv.give(user, f"Verified by hand by {inter.user}")
            return await inter.response.send_message(f"✅ {user.mention} is verified.", ephemeral=True)
        if any(r.name == VERIFIED for r in inter.user.roles):
            return await inter.response.send_message("You're already verified!", ephemeral=True)
        v = discord.ui.View()
        v.add_item(discord.ui.Button(label="Open verify page", url=sv.link_for(inter.user)))
        await inter.response.send_message("Here's your personal link (works once, for 15 minutes). Turn off any VPN first.",
                                          view=v, ephemeral=True)

    @app_commands.command(name="verify-panel", description="Post the Shigeo verify button in this channel")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def panel_cmd(inter: discord.Interaction):
        v = discord.ui.View(timeout=None)
        v.add_item(discord.ui.Button(label="Verify (Shigeo)", emoji="🛡️", style=discord.ButtonStyle.primary, custom_id="sv_start"))
        e = discord.Embed(title="🛡️ Gaster's Ship Verification", color=0xFFFFFF,
                          description="**1.** Press **Verify (Shigeo)** below\n"
                                      "**2.** Open your link and tap the button (takes 2 seconds)\n"
                                      "**3.** Done - you get access right away\n\n"
                                      "⚠️ Turn off any **VPN / proxy** first\n"
                                      "🚫 VPNs, proxies, bots and virtual machines are blocked\n"
                                      "🕵️ Alt accounts get caught and checked by staff\n"
                                      "🔒 Your IP is never saved, only a scrambled code\n"
                                      f"🔍 What we check: [{PUBLIC.split('://')[-1]}/info]({PUBLIC}/info)\n"
                                      f"❓ Stuck? [Help form]({PUBLIC}/help) or ask in #support\n\n"
                                      "اضغط **Verify** ↓ ، افتح الرابط واضغط الزر. أطفئ الـ VPN أول.\n"
                                      "الـ VPN والبوتات والأجهزة الوهمية ممنوعة.")
        e.set_footer(text="Shigeo · Gaster Ship security")
        await inter.channel.send(embed=e, view=v)
        await inter.response.send_message("Panel posted.", ephemeral=True)

    @app_commands.command(name="verify-test", description="Staff: run the full verify check on yourself without changing anything")
    @app_commands.guild_only()
    async def test_cmd(inter: discord.Interaction):
        if not inter.user.guild_permissions.manage_roles:
            return await inter.response.send_message("Only staff can do this.", ephemeral=True)
        v = discord.ui.View()
        v.add_item(discord.ui.Button(label="Open test page", url=sv.link_for(inter.user, test=True)))
        await inter.response.send_message("Test link (works once, 15 min). It shows PASS / REVIEW / BLOCK and saves nothing.",
                                          view=v, ephemeral=True)

    @app_commands.command(name="verify-forget", description="Staff: delete someone's saved verify data (scrambled IP/device codes)")
    @app_commands.describe(user="Whose data to delete", user_id="Or their user ID if they left")
    @app_commands.guild_only()
    async def forget_cmd(inter: discord.Interaction, user: discord.User = None, user_id: str = None):
        if not inter.user.guild_permissions.manage_roles:
            return await inter.response.send_message("Only staff can do this.", ephemeral=True)
        uid = user.id if user else (int(user_id) if user_id and user_id.isdigit() else None)
        if uid is None:
            return await inter.response.send_message("Pick a user or give a user ID.", ephemeral=True)
        n = sv.forget(uid)
        await inter.response.send_message(f"🗑️ Deleted {n} saved code(s) for <@{uid}>. They'll be checked fresh next time.",
                                          ephemeral=True)

    return [verify_cmd, panel_cmd, test_cmd, forget_cmd]
