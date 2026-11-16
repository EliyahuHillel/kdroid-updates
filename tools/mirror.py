#!/usr/bin/env python3
"""
Keeps a verified copy of an app (all its split parts) for Kiydroid's store.

Runs on GitHub Actions every few hours. For each app in APPS:
  1. reads the version Google Play shows now (best effort),
  2. downloads the full package (XAPK: base + split parts) of the latest version,
  3. checks: every part is signed with the app's real certificate, the package and version are right,
     the version is the one Google Play has (never a beta / early build), and the parts the phone needs are there,
  4. only then publishes it as a release asset and updates apps/<package>.json, which the store reads.
Anything that does not pass leaves the last good version in place.
"""
import json, os, re, subprocess, sys, tempfile, zipfile, hashlib, shutil, urllib.request, glob, time

APPS = {
    "com.unicell.pangoandroid": {
        "title": "Pango",
        # SHA-1 of Pango's signing certificate (the same value Kiydroid's route check uses)
        "cert_sha1": "8e5a73f88599331ad34b99beaaf312179e29c7b",
        # newer versions carry Google Play's license check ("pairip"), which closes Pango on phones without the
        # Play Store; while the latest has it, the store gets this version, the newest without it (checked by
        # tools/probe.py). A newer version without the check is taken automatically.
        "fallback_code": 130607,
    },
}
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
REPO = os.environ.get("GITHUB_REPOSITORY", "EliyahuHillel/kdroid-updates")
BT = sorted(glob.glob(os.path.join(os.environ.get("ANDROID_HOME", "/usr/local/lib/android/sdk"), "build-tools", "*")))[-1]
APKSIGNER, AAPT2 = os.path.join(BT, "apksigner"), os.path.join(BT, "aapt2")


def log(*a):
    print(*a, flush=True)


def get(url, binary=False, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
                return data if binary else data.decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(5 * (i + 1))
    raise last


def play_page(pkg):
    try:
        return get(f"https://play.google.com/store/apps/details?id={pkg}&hl=en&gl=IL")
    except Exception as e:
        log("play: page failed", e)
        return None


def play_version(pkg):
    """The version Google Play shows (None when the page does not say)."""
    try:
        html = get(f"https://play.google.com/store/apps/details?id={pkg}&hl=en&gl=IL")
    except Exception as e:
        log("play: page failed", e)
        return None
    # the version sits in the page data as [[["13.2105"]],[[[33]],[[[23,"6.0"]]]] (min SDK follows it)
    m = re.search(r'\[\[\["([^"\]]{1,40})"\]\],\[\[\[\d+\]\],\[\[\[\d+,"', html)
    if m:
        return m.group(1)
    i = html.find("Version")
    log("play: version not found; page", len(html), "chars; title:", re.search(r"<title>([^<]*)", html).group(1) if "<title>" in html else "-",
        "| sample:", re.findall(r'\[\[\["[^"]{1,20}"\]\][^\n]{0,40}', html)[:5])
    return None


def cert_sha1(apk):
    out = subprocess.run([APKSIGNER, "verify", "--print-certs", apk], capture_output=True, text=True)
    if out.returncode != 0:
        raise ValueError("signature does not verify: " + (out.stderr or out.stdout)[-300:])
    # "Signer #1 certificate SHA-1 digest: ..." or, for apps with key rotation, "Signer (minSdkVersion=..) certificate ..."
    # Kiydroid writes each byte without its leading zero ("07" -> "7"), so compare in that form
    found = ["".join(format(int(d[i:i + 2], 16), "x") for i in range(0, len(d), 2))
             for d in re.findall(r"certificate SHA-1 digest: ([0-9a-f]+)", out.stdout)]
    if not found:
        raise ValueError("no signer in: " + out.stdout[:400])
    return found


def badging(apk):
    out = subprocess.run([AAPT2, "dump", "badging", apk], capture_output=True, text=True).stdout
    m = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'", out)
    if not m:
        raise ValueError("cannot read " + os.path.basename(apk))
    split = re.search(r"split='([^']+)'", out.splitlines()[0])
    return {"pkg": m.group(1), "code": int(m.group(2)), "name": m.group(3), "split": split.group(1) if split else None}


def has_pairip(apk):
    with zipfile.ZipFile(apk) as z:
        for n in z.namelist():
            if n.endswith(".dex") or n == "AndroidManifest.xml":
                d = z.read(n)
                if b"com/pairip" in d or b"com.pairip" in d or "com.pairip".encode("utf-16-le") in d:
                    return True
    return False


def pick(pkg, spec, latest, work):
    """the latest version, unless it carries the Play license check: then the fallback version"""
    if latest[:2] != b"PK" or not spec.get("fallback_code"):
        return latest, False
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(latest)) as z:
            apks = [n for n in z.namelist() if n.endswith(".apk")]
            b = next((n for n in apks if n in (pkg + ".apk", "base.apk")), None)
            if b:
                tmp = os.path.join(work, "latest_base.apk"); open(tmp, "wb").write(z.read(b))
                if not has_pairip(tmp):
                    log("latest has no Play license check: taking it")
                    return latest, False
    except Exception as e:
        log("latest check failed", e)
    log("latest carries the Play license check: taking", spec["fallback_code"])
    return get(f"https://d.apkpure.com/b/XAPK/{pkg}?versionCode={spec['fallback_code']}", binary=True), True


def mirror(pkg, spec):
    meta_path = os.path.join("apps", pkg + ".json")
    current = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    page = play_page(pkg)
    log(pkg, "| ours:", current.get("versionName"))

    work = tempfile.mkdtemp()
    xapk = os.path.join(work, "app.xapk")
    older = False
    data = get(f"https://d.apkpure.com/b/XAPK/{pkg}?version=latest", binary=True)
    data, older = pick(pkg, spec, data, work)
    if data[:2] != b"PK":
        raise ValueError("download is not a package (blocked or error page)")
    open(xapk, "wb").write(data)
    parts = os.path.join(work, "parts")
    with zipfile.ZipFile(xapk) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".apk") and "/" not in n.strip("/")]
        if not names:
            raise ValueError("no apk inside")
        for n in names:
            z.extract(n, parts)
        manifest = json.loads(z.read("manifest.json")) if "manifest.json" in z.namelist() else {}

    apks = sorted(glob.glob(os.path.join(parts, "*.apk")))
    base, splits = None, []
    for a in apks:
        certs = cert_sha1(a)
        if spec["cert_sha1"] not in certs:
            raise ValueError(os.path.basename(a) + ": not signed with the app's certificate (found " + ",".join(certs) + ")")
        b = badging(a)
        if b["pkg"] != pkg:
            raise ValueError(os.path.basename(a) + ": wrong package " + b["pkg"])
        if b["split"]:
            splits.append(b["split"])
        else:
            base = (a, b)
    if not base:
        raise ValueError("no base apk")
    b = base[1]
    log("downloaded", b["name"], b["code"], "parts:", splits)

    # the parts every phone needs: a processor part (when the app has them), screen and Hebrew/English
    listed = [s.get("id") or s.get("file") for s in manifest.get("split_apks", [])] if manifest else []
    abis = [s for s in splits if re.search(r"(arm64_v8a|armeabi_v7a|x86_64|x86)$", s)]
    if any(re.search(r"(arm64_v8a|armeabi_v7a)", str(x)) for x in listed) and not any("arm64_v8a" in s for s in abis):
        raise ValueError("arm64 part missing")
    if listed and len(splits) + 1 < len([x for x in listed if x]):
        raise ValueError(f"parts missing: listed {listed}, got base + {splits}")

    if has_pairip(base[0]):
        raise ValueError(f"{b['name']} carries the Play license check")
    if older and b["code"] != spec.get("fallback_code"):
        raise ValueError(f"asked for {spec.get('fallback_code')}, got {b['code']}")
    if re.search(r"(beta|alpha|rc|preview)", b["name"], re.I):
        raise ValueError("beta build " + b["name"])
    # the same version Google Play offers now: its page data carries the version string
    if not older and page is not None and f'"{b["name"]}"' not in page:
        log(f"skip: {b['name']} is not the version on Google Play right now (beta, or Play not updated yet); waiting")
        return False
    play = b["name"] if page is not None and not older else None
    if current.get("versionCode", 0) == b["code"] or (not older and current.get("versionCode", 0) > b["code"] and not current.get("older")):
        log("already published")
        return False

    # publish: one .apks with all parts; the store installs the ones that fit each phone
    out = os.path.join(work, f"{pkg.split('.')[-1]}-{b['code']}.apks")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        z.write(base[0], "base.apk")
        for a in apks:
            if a != base[0]:
                z.write(a, os.path.basename(a))
    sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
    tag = f"app-{pkg}-{b['code']}"
    subprocess.run(["gh", "release", "create", tag, out, "--repo", REPO, "--title", f"{spec['title']} {b['name']}",
                    "--notes", f"Verified copy of {pkg} {b['name']} ({b['code']}), all parts: {', '.join(splits)}. Same version as Google Play: {play or 'unknown'}."],
                   check=True)
    meta = {"package": pkg, "title": spec["title"], "versionName": b["name"], "versionCode": b["code"],
            "url": f"https://github.com/{REPO}/releases/download/{tag}/{os.path.basename(out)}",
            "size": os.path.getsize(out), "sha256": sha, "parts": ["base"] + splits, "playVersion": play,
            "publishedAt": int(time.time() * 1000), "older": older}
    os.makedirs("apps", exist_ok=True)
    json.dump(meta, open(meta_path, "w"), indent=1)
    log("published", meta["url"])
    # keep the last three releases of this app
    rel = subprocess.run(["gh", "release", "list", "--repo", REPO, "--limit", "100"], capture_output=True, text=True).stdout
    tags = sorted([l.split("\t")[2] for l in rel.splitlines() if f"\tapp-{pkg}-" in l], key=lambda t: int(t.rsplit("-", 1)[1]))
    for t in [t for t in tags[:-3] if t != tag]:
        subprocess.run(["gh", "release", "delete", t, "--repo", REPO, "--yes", "--cleanup-tag"])
    shutil.rmtree(work, ignore_errors=True)
    return True


def main():
    os.makedirs("apps", exist_ok=True)
    changed, failed = False, False
    for pkg, spec in APPS.items():
        try:
            changed |= bool(mirror(pkg, spec))
        except Exception as e:
            failed = True
            log(f"{pkg}: not published ({e}); the last good version stays")
    # the status file changes only when the result changes (no commit every run)
    sp = os.path.join("apps", "_status.json")
    old = json.load(open(sp)) if os.path.exists(sp) else {}
    if changed or old.get("ok") != (not failed):
        json.dump({"ok": not failed, "at": int(time.time() * 1000)}, open(sp, "w"))
    print("changed" if changed else "no change")


if __name__ == "__main__":
    main()
