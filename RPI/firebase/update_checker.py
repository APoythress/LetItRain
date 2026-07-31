# firebase/update_checker.py
# Git-tag-based update detection/application for the Pi build. Replaces
# the old Pico-era Storage-manifest downloader (update/updater.py) --
# that module is MicroPython-only (ujson/urequests) and existed only
# because the Pico had no filesystem-level git; the Pi is a normal git
# clone on real Linux, so "update" now just means "check out a newer tag."
#
# Versioning: releases are tagged "vX.Y.Z" (or "X.Y.Z") on the repo.
# "Available" means the highest such tag compares greater than main.py's
# FIRMWARE_VERSION. The leading "v" and any trailing "-suffix" (e.g.
# this alpha's "2.0.0-alpha") are both ignored for comparison -- this is
# a simple three-integer compare, not full semver precedence.

import os
import re
import subprocess

_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")

# main.py lives in RPI/, but the git repo root (monorepo: RPI/ + ios/ +
# cloud_functions/) is one level up -- git commands must run there.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_GIT_TIMEOUT = 30  # seconds -- network fetch, generous but bounded


def _parse_version(v):
    m = _TAG_RE.match(v.strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def _run(args):
    return subprocess.run(
        args, cwd=_REPO_ROOT, capture_output=True, text=True, timeout=_GIT_TIMEOUT
    )


def get_latest_tag():
    """
    Fetch tags from origin and return the highest-versioned tag name found
    (e.g. "v2.1.0"), or None if the fetch failed or no version-shaped tags
    exist yet.
    """
    try:
        fetch = _run(["git", "fetch", "--tags", "--quiet"])
        if fetch.returncode != 0:
            print("update_checker: git fetch failed:", fetch.stderr.strip())
            return None
        listing = _run(["git", "tag", "--list"])
        if listing.returncode != 0:
            return None
        versions = []
        for line in listing.stdout.splitlines():
            parsed = _parse_version(line)
            if parsed:
                versions.append((parsed, line.strip()))
        if not versions:
            return None
        versions.sort()
        return versions[-1][1]
    except Exception as ex:
        print("update_checker: get_latest_tag failed:", ex)
        return None


def is_newer(tag, current_version):
    tag_v = _parse_version(tag)
    cur_v = _parse_version(current_version)
    if tag_v is None or cur_v is None:
        return False
    return tag_v > cur_v


def apply_update(tag):
    """
    Check out the given tag in place. Caller is responsible for confirming
    it's safe to do so (no zone currently running) and for restarting the
    process afterward -- this only updates the working tree.

    Returns (ok: bool, error_message: str or None).
    """
    try:
        fetch = _run(["git", "fetch", "--tags", "--quiet"])
        if fetch.returncode != 0:
            return False, "git fetch failed: {}".format(fetch.stderr.strip())
        checkout = _run(["git", "checkout", tag, "--quiet"])
        if checkout.returncode != 0:
            return False, "git checkout failed: {}".format(checkout.stderr.strip())
        return True, None
    except Exception as ex:
        return False, str(ex)
