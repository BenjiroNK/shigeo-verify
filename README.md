# Shigeo Verify

The verification system used by the **Gaster's Ship** Discord server (discord.gg/gstr).

It's public so anyone can check exactly what it does. **This is the real code that runs.** Nothing is hidden.

## In one sentence

It checks that you're a real person on a real device without a VPN, so alt accounts, bots and raiders can't get in.

## What it NEVER does

- ❌ Ask for your Discord password, email or login
- ❌ Get your Discord token, DMs or access to your account
- ❌ Read your files, camera, microphone or location
- ❌ Make you download anything
- ❌ Use trackers, ads or outside scripts on the page

## What it checks

| What | Why | What gets saved |
|---|---|---|
| Your IP address | Spot VPNs, proxies, Tor and servers | Only a **salted hash** (a scrambled code that can't be turned back into the IP) |
| Graphics card name, screen size, timezone, language, CPU cores | Catch virtual machines and one person with many accounts | Only a salted hash |
| A random browser ID (saved in your browser) | Stop one browser verifying lots of accounts | Only a salted hash |
| Discord account age and profile picture | Very new accounts get a quick staff check | Nothing new (already public on Discord) |
| That you pressed the button yourself, plus a tiny hidden puzzle your browser solves (~1 second) | Stop scripts and bots | Nothing |

To check for VPNs, the IP (only the IP) is sent to **ip-api.com**, **proxycheck.io** and **IPQualityScore**.

## What staff see

If a verify needs a human look, staff get a short reason, like `VPN detected` or `same device as @someone`.
**Staff never see your IP or your device details.**

## Deleting your data

Ask in **#support**. Staff run `/verify-forget` and your saved codes are deleted.

## Files

- `verify.py`: the checks, the verify page and the Discord buttons and commands
- `verify_pages.py`: the "What we check", Privacy and Help pages

API keys and the hash salt live in the bot's private `.env` and data files. They are **not** in this repo.

---

### بالعربي

نظام التوثيق حق سيرفر **Gaster's Ship**، والكود منشور كامل عشان أي أحد يتأكد بنفسه.

- ما يطلب باسوورد ولا تسجيل دخول ديسكورد ولا توكن.
- ما يشوف ملفاتك ولا الكاميرا ولا موقعك.
- الـ IP **ما ينحفظ أبداً**، بس رمز مشفّر ما ينرجع.
- يفحص: الـ VPN، والأجهزة الوهمية، والحسابات الثانية.
- تبي نحذف بياناتك؟ اطلب في **#support**.
