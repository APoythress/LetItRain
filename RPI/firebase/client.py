# firebase/client.py
# Firebase Realtime Database REST client for CPython (Raspberry Pi 3 A+).
#
# Ported from the MicroPython/urequests version to httpx.AsyncClient so
# every call is a real `await` instead of a blocking request -- this is
# what lets Firebase sync run as its own independent asyncio task instead
# of stalling the scheduler/HTTP-server tasks sharing the same event loop.
#
# Authentication uses Firebase Email/Password sign-in to obtain
# a short-lived ID token (valid 3600s). The client re-authenticates
# automatically 5 minutes before expiry.
#
# The old MicroPython version manually closed every response and called
# gc.collect()/mem_diag.sample() after each request -- that was working
# around a small fixed lwIP socket pool and a tiny fragmentable heap on
# the Pico. httpx manages its own connection pool and CPython's GC is
# generational, so none of that bookkeeping applies here.

import time

import httpx

_SIGN_IN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
)
_REQUEST_TIMEOUT = 8  # seconds — all REST calls use this timeout


class FirebaseClient:
    """
    Lightweight async Firebase Realtime Database REST client.

    Usage:
        fb = FirebaseClient(api_key, email, password, db_url, device_id)
        await fb.authenticate()          # call once at boot; auto-refreshes later
        await fb.patch("status", {...})  # write
        data = await fb.get("overrides") # read
    """

    def __init__(self, api_key, email, password, db_url, device_id):
        self._api_key      = api_key
        self._email        = email
        self._password     = password
        self._db_url       = db_url.rstrip("/")
        self._device_id    = device_id
        self._id_token     = None
        self._uid          = None
        self._token_issued = 0   # time.time() when token was obtained
        self._last_auth_error = None  # last authenticate() failure message, for boot_log.json
        self._http = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

    @property
    def id_token(self):
        """Current Firebase Auth ID token, or None if not authenticated yet.
        Exposed for other Firebase REST APIs (e.g. Cloud Storage) that need
        the same token but aren't part of the Realtime Database surface."""
        return self._id_token

    @property
    def uid(self):
        """This account's Firebase Auth UID, or None if not authenticated
        yet. Used to self-claim device_owner_uid at boot and for the
        optional FIREBASE_EXPECTED_UID cross-check in secrets.py."""
        return self._uid

    @property
    def last_auth_error(self):
        """Human-readable reason the most recent authenticate() call failed,
        or None if it succeeded (or hasn't been tried). Surfaced in
        boot_log.json so an auth failure is diagnosable remotely via
        GET /boot-log, without needing a serial console."""
        return self._last_auth_error

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def authenticate(self):
        """
        Sign in with email/password and store the ID token.
        Returns True on success, False on any failure.
        Should be called once at boot and then automatically via
        _refresh_if_needed() before every request.
        """
        url  = _SIGN_IN_URL.format(api_key=self._api_key)
        body = {
            "email":             self._email,
            "password":          self._password,
            "returnSecureToken": True,
        }
        try:
            resp = await self._http.post(url, json=body)
            data = resp.json()

            if "idToken" in data:
                self._id_token     = data["idToken"]
                self._uid          = data.get("localId")
                self._token_issued = time.time()
                self._last_auth_error = None
                print("Firebase: authenticated OK")
                return True
            else:
                self._last_auth_error = data.get("error", {}).get("message", "unknown")
                print("Firebase: auth failed:", self._last_auth_error)
                return False

        except Exception as ex:
            self._last_auth_error = str(ex)
            print("Firebase: authenticate exception:", ex)
            return False

    async def _refresh_if_needed(self):
        """Re-authenticate if the token is within 5 minutes of expiry (3600s)."""
        if self._id_token is None or time.time() - self._token_issued > 3300:
            await self.authenticate()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path):
        """Build the REST URL for a given sub-path under this device's node."""
        return "{}/devices/{}/{}.json?auth={}".format(
            self._db_url, self._device_id, path, self._id_token or ""
        )

    # ------------------------------------------------------------------
    # Public read/write methods
    # ------------------------------------------------------------------

    async def get(self, path):
        """
        Read a value from the database.

        Args:
            path: sub-path under /devices/{device_id}/  e.g. "overrides"

        Returns:
            Parsed JSON value (dict, list, scalar) or None on any error.
            Fails silently — callers must handle None.
        """
        await self._refresh_if_needed()
        try:
            resp = await self._http.get(self._url(path))
            if resp.status_code != 200:
                print("Firebase: get({}) status {} body {}".format(
                    path, resp.status_code, resp.text))
                return None
            return resp.json()
        except Exception as ex:
            print("Firebase: get({}) exception: {}".format(path, ex))
            return None

    async def patch(self, path, data_dict):
        """
        Merge-update a node (PATCH — only supplied keys are changed).

        Args:
            path:      sub-path under /devices/{device_id}/
            data_dict: dict of key/value pairs to write

        Returns:
            True on HTTP 200, False on any error.
        """
        await self._refresh_if_needed()
        try:
            resp = await self._http.patch(self._url(path), json=data_dict)
            ok = resp.status_code == 200
            if not ok:
                print("Firebase: patch({}) status {} body {}".format(
                    path, resp.status_code, resp.text))
            return ok
        except Exception as ex:
            print("Firebase: patch({}) exception: {}".format(path, ex))
            return False

    async def put(self, path, value):
        """
        Overwrite a node completely (PUT).

        Args:
            path:  sub-path under /devices/{device_id}/
            value: any JSON-serialisable value

        Returns:
            True on HTTP 200, False on any error.
        """
        await self._refresh_if_needed()
        try:
            resp = await self._http.put(self._url(path), json=value)
            return resp.status_code == 200
        except Exception as ex:
            print("Firebase: put({}) exception: {}".format(path, ex))
            return False

    async def aclose(self):
        """Release the underlying HTTP connection pool. Call on shutdown."""
        await self._http.aclose()
