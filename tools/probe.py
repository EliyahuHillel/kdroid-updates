#!/usr/bin/env python3
"""
One-off check of Pango's earlier versions: which ones do NOT carry Google Play's license protection ("pairip"),
which makes Pango close on phones where the Play Store is blocked. Writes apps/_probe.json; publishes nothing.
For each version: Pango's real signature, version, and whether the protection is inside.
"""
import json, os, re, sys, tempfile, zipfile, io, importlib.util
spec = importlib.util.spec_from_file_location("m", os.path.join(os.path.dirname(__file__), "mirror.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
PKG = "com.unicell.pangoandroid"
CERT = m.APPS[PKG]["cert_sha1"]

def versions():
    found = {}
    for url in [f"https://apkpure.com/pango/{PKG}/versions", f"https://apkpure.net/pango/{PKG}/versions"]:
        try:
            html = m.get(url)
        except Exception as e:
            m.log("versions page failed", url, e); continue
        for code in re.findall(r'versionCode=(\d{4,})', html) + re.findall(r'data-dt-version-?code="(\d{4,})"', html, re.I):
            found[int(code)] = True
        m.log(url, len(html), "chars,", len(found), "codes")
        if found: break
    return sorted(found, reverse=True)

def check(code):
    r = {"code": code}
    data = None
    for kind in ("XAPK", "APK"):
        try:
            data = m.get(f"https://d.apkpure.com/b/{kind}/{PKG}?versionCode={code}", binary=True)
            if data[:2] == b"PK": r["kind"] = kind; break
        except Exception as e:
            r["err"] = str(e)[:120]
    if not data or data[:2] != b"PK":
        r["err"] = r.get("err", "no download"); return r
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    work = tempfile.mkdtemp()
    if "AndroidManifest.xml" in names:          # a plain APK
        base = os.path.join(work, "base.apk"); open(base, "wb").write(data); parts = ["base"]
    else:                                         # XAPK: base + split parts
        apks = [n for n in names if n.endswith(".apk")]
        b = next((n for n in apks if os.path.basename(n) in (PKG + ".apk", "base.apk")), apks[0] if apks else None)
        if not b: r["err"] = "no apk inside"; return r
        base = os.path.join(work, "base.apk"); open(base, "wb").write(z.read(b)); parts = [os.path.basename(n) for n in apks]
    r["parts"] = parts
    try:
        bd = m.badging(base); r["name"] = bd["name"]; r["vcode"] = bd["code"]; r["pkg"] = bd["pkg"]
    except Exception as e:
        r["err"] = "badging " + str(e)[:80]
    try:
        r["signed_ok"] = CERT in m.cert_sha1(base)
    except Exception as e:
        r["signed_ok"] = False; r["sig_err"] = str(e)[:120]
    bz = zipfile.ZipFile(base)
    pair = False
    for n in bz.namelist():
        if n.endswith(".dex") or n == "AndroidManifest.xml":
            d = bz.read(n)
            if b"com/pairip" in d or "com.pairip".encode("utf-16-le") in d or b"com.pairip" in d:
                pair = True; break
    r["pairip"] = pair
    r["needs_splits"] = b"requiredSplitTypes" in bz.read("AndroidManifest.xml") or "r".encode() and ("requiredSplitTypes".encode("utf-16-le") in bz.read("AndroidManifest.xml"))
    return r

def main():
    vs = versions()
    m.log("versions:", vs[:40])
    out = {"checkedAt": __import__("time").time(), "versions": []}
    for code in vs[:30]:
        r = check(code); m.log(r); out["versions"].append(r)
        # stop once we have two clean, Pango-signed versions
        if sum(1 for x in out["versions"] if x.get("signed_ok") and x.get("pairip") is False) >= 2: break
    os.makedirs("apps", exist_ok=True)
    json.dump(out, open("apps/_probe.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
