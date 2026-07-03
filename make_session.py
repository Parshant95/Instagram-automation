"""
Build a fresh session.json WITHOUT hitting Instagram's login API
(which is currently blocked by a challenge_required checkpoint).

Usage:
    1. Log into https://www.instagram.com in your browser.
    2. F12 -> Application -> Cookies -> copy the `sessionid` value.
    3. Run:  python make_session.py
       and paste the sessionid when prompted.
"""
from pathlib import Path
from instagrapi import Client

SESSION_FILE = Path("session.json")


def main():
    sessionid = input("Paste your Instagram sessionid cookie: ").strip().strip('"')
    if not sessionid:
        print("[!] No sessionid given. Aborting.")
        return

    cl = Client()

    # Reuse the existing device fingerprint if we still have one, so the
    # session matches the device Instagram already knows.
    if SESSION_FILE.exists():
        try:
            cl.load_settings(SESSION_FILE)
            print("[*] Reusing device fingerprint from existing session.json")
        except Exception as e:
            print(f"[!] Could not load existing settings ({e}) — using a new device.")

    # login_by_sessionid validates the cookie with a real authenticated
    # request, so a bad/expired cookie fails here immediately.
    cl.login_by_sessionid(sessionid)

    me = cl.account_info()
    print(f"[*] Authenticated as @{me.username}")

    cl.dump_settings(SESSION_FILE)
    print(f"[*] Wrote fresh {SESSION_FILE.resolve()}")


if __name__ == "__main__":
    main()
