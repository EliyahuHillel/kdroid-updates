#!/usr/bin/env python3
"""
Kiydroid installers mail. Runs on GitHub Actions (every few minutes).

The panel (owner only, by the database rules) puts each e-mail in the mailQueue collection. This reads the queue with
the project's service account, sends each one from the sending Gmail account with its app password (SMTP), and
removes it. Nothing about the e-mails is printed to the (public) logs: only counts.

Secrets (repository settings -> Secrets and variables -> Actions):
  MAIL_APP_PASSWORD         the sending account's Gmail app password (16 letters)
  FIREBASE_SERVICE_ACCOUNT  the project's service account key (the whole JSON file)
"""
import html, json, os, smtplib, ssl, sys, time
from email.mime.text import MIMEText
from email.utils import formataddr
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

FROM_ADDR = "hebrewbookssystem@gmail.com"
FROM_NAME = "קיידרואיד מתקינים"
PANEL = "https://eliyahuhillel.github.io/kdroid-updates/panel/"

sa = json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT"])
PROJECT = sa["project_id"]
cred = service_account.Credentials.from_service_account_info(sa, scopes=["https://www.googleapis.com/auth/datastore"])
cred.refresh(Request())
H = {"Authorization": "Bearer " + cred.token}
DB = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"


def val(f):
    if f is None: return None
    for k in ("stringValue", "integerValue", "booleanValue", "doubleValue"):
        if k in f: return f[k]
    return None


def body(m):
    e = lambda s: html.escape(str(s or ""))
    LTR = ' dir="ltr" style="text-align:right"'
    row = lambda k, v, ltr=False: ('<tr><td style="padding:6px 0 6px 18px;color:#5b6862;white-space:nowrap">' + k + '</td>'
                                   '<td' + (LTR if ltr else '') + '>' + v + '</td></tr>')
    pw = m.get("password") or ""
    return ('<div dir="rtl" style="font-family:Arial,sans-serif;font-size:15px;line-height:1.7;color:#191c1a;max-width:560px">'
            '<h2 style="margin:0 0 8px;font-size:20px;color:#006c51">ברוכים הבאים לקיידרואיד</h2>'
            f'<p>שלום {e(m.get("name"))},</p><p>נפתח לך חשבון מתקין במערכת הניהול של קיידרואיד. אלה פרטי הכניסה שלך:</p>'
            '<table style="border-collapse:collapse;margin:6px 0 16px">'
            + row("כניסה לפאנל", f'<a href="{PANEL}">{PANEL}</a>', True)
            + row("מייל", e(m.get("to")), True)
            + (row("סיסמה", f'<b style="letter-spacing:1px">{e(pw)}</b>', True) if pw else "")
            + (row("קוד מתקין", f'<b>{e(m.get("code"))}</b>') if m.get("code") else "")
            + '</table><p>בכניסה הראשונה עם הסיסמה הזמנית תתבקשו לבחור סיסמה משלכם. מדריך מלא נמצא בפאנל, בתפריט "מדריך".</p>'
            f'<p style="color:#5b6862;font-size:13px">{e(m.get("from") or "קיידרואיד")}</p></div>')


def main():
    r = requests.get(DB + "/mailQueue?pageSize=50", headers=H, timeout=30)
    r.raise_for_status()
    docs = r.json().get("documents", [])
    sent = failed = 0
    last_err = ""
    if docs:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=60) as s:
            s.login(FROM_ADDR, os.environ["MAIL_APP_PASSWORD"].replace(" ", ""))
            for d in docs:
                f = d.get("fields", {})
                m = {k: val(f.get(k)) for k in ("to", "name", "password", "code", "from", "kind", "attempts")}
                try:
                    msg = MIMEText(body(m), "html", "utf-8")
                    msg["Subject"] = "פרטי הכניסה שלך לקיידרואיד"
                    msg["From"] = formataddr((FROM_NAME, FROM_ADDR))
                    msg["To"] = m["to"]
                    s.sendmail(FROM_ADDR, [m["to"]], msg.as_string())
                    requests.delete("https://firestore.googleapis.com/v1/" + d["name"], headers=H, timeout=30).raise_for_status()
                    sent += 1
                except Exception as ex:
                    failed += 1
                    last_err = type(ex).__name__
                    n = int(m.get("attempts") or 0) + 1
                    if n >= 5:
                        requests.delete("https://firestore.googleapis.com/v1/" + d["name"], headers=H, timeout=30)
                    else:
                        requests.patch("https://firestore.googleapis.com/v1/" + d["name"] + "?updateMask.fieldPaths=attempts",
                                       headers=H, json={"fields": {"attempts": {"integerValue": str(n)}}}, timeout=30)
    # a heartbeat for the panel ("connected, last run ...")
    st = {"lastRunAt": {"integerValue": str(int(time.time() * 1000))}, "sent": {"integerValue": str(sent)},
          "failed": {"integerValue": str(failed)}, "lastError": {"stringValue": last_err}}
    requests.patch(DB + "/config/mailStatus", headers=H, json={"fields": st}, timeout=30)
    print(f"queue {len(docs)}, sent {sent}, failed {failed}")


if __name__ == "__main__":
    try:
        main()
    except smtplib.SMTPAuthenticationError:
        requests.patch(DB + "/config/mailStatus", headers=H, json={"fields": {"lastRunAt": {"integerValue": str(int(time.time() * 1000))},
                       "lastError": {"stringValue": "login"}}}, timeout=30)
        print("gmail login failed (app password?)"); sys.exit(1)
