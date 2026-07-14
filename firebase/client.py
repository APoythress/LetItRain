# firebase/client.py
# Firebase Realtime Database REST client for MicroPython (Pico W).
#
# The Pico W has no Firebase SDK. All communication uses the
# Firebase REST API over HTTPS via urequests.
#
# Authentication uses Firebase Email/Password sign-in to obtain
# a short-lived ID token (valid 3600s). The client re-authenticates
# automatically 5 minutes before expiry.

import ujson
import utime

try:
    import urequests as requests
except ImportError:
    import requests  # fallback for local testing


# Firebase REST endpoints
_SIGN_IN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
)
_REQUEST_TIMEOUT = 8  # seconds — all REST calls use this timeout


class FirebaseClient:
    """
    Lightweight Firebase Realtime Database REST client.

    Usage:
        fb = FirebaseClient(api_key, email, password, db_url, device_id)
        fb.authenticate()          # call once at boot; auto-refreshes later
        fb.patch("status", {...})  # write
        data = fb.get("overrides") # read
    """

    def __init__(self, api_key, email, password, db_url, device_id):
        self._api_key      = api_key
        self._email        = email
        self._password     = password
        self._db_url       = db_url.rstrip("/")
        self._device_id    = device_id
        self._id_token     = None
        self._token_issued = 0   # utime.time() when token was obtained

    @property
    def id_token(self):
        """Current Firebase Auth ID token, or None if not authenticated yet.
        Exposed for other Firebase REST APIs (e.g. Cloud Storage) that need
        the same token but aren't part of the Realtime Database surface."""
        return self._id_token

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self):
        """
        Sign in with email/password and store the ID token.
        Returns True on success, False on any failure.
        Should be called once at boot and then automatically via
        _refresh_if_needed() before every request.
        """
        url  = _SIGN_IN_URL.format(api_key=self._api_key)
        body = ujson.dumps({
            "email":             self._email,
            "password":          self._password,
            "returnSecureToken": True,
        })
        try:
            resp = requests.post(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=_REQUEST_TIMEOUT,
            )
            data = resp.json()
            resp.close()

            if "idToken" in data:
                self._id_token     = data["idToken"]
                self._token_issued = utime.time()
                print("Firebase: authenticated OK")
                return True
            else:
                print("Firebase: auth failed:", data.get("error", {}).get("message", "unknown"))
                return False

        except Exception as ex:
            print("Firebase: authenticate exception:", ex)
            return False

    def _refresh_if_needed(self):
        """Re-authenticate if the token is within 5 minutes of expiry (3600s)."""
        if self._id_token is None or utime.time() - self._token_issued > 3300:
            self.authenticate()

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

    def get(self, path):
        """
        Read a value from the database.

        Args:
            path: sub-path under /devices/{device_id}/  e.g. "overrides"

        Returns:
            Parsed JSON value (dict, list, scalar) or None on any error.
            Fails silently — callers must handle None.
        """
        self._refresh_if_needed()
        try:
            resp = requests.get(self._url(path), timeout=_REQUEST_TIMEOUT)
            if resp.status_code != 200:
                print("Firebase: get({}) status {} body {}".format(
                    path, resp.status_code, resp.text))
                resp.close()
                return None
            data = resp.json()
            resp.close()
            return data
        except Exception as ex:
            print("Firebase: get({}) exception: {}".format(path, ex))
            return None

    def patch(self, path, data_dict):
        """
        Merge-update a node (PATCH — only supplied keys are changed).

        Args:
            path:      sub-path under /devices/{device_id}/
            data_dict: dict of key/value pairs to write

        Returns:
            True on HTTP 200, False on any error.
        """
        self._refresh_if_needed()
        try:
            resp = requests.patch(
                self._url(path),
                data=ujson.dumps(data_dict),
                headers={"Content-Type": "application/json"},
                timeout=_REQUEST_TIMEOUT,
            )
            ok = resp.status_code == 200
            if not ok:
                print("Firebase: patch({}) status {} body {}".format(
                    path, resp.status_code, resp.text))
            resp.close()
            return ok
        except Exception as ex:
            print("Firebase: patch({}) exception: {}".format(path, ex))
            return False

    def put(self, path, value):
        """
        Overwrite a node completely (PUT).

        Args:
            path:  sub-path under /devices/{device_id}/
            value: any JSON-serialisable value

        Returns:
            True on HTTP 200, False on any error.
        """
        self._refresh_if_needed()
        try:
            resp = requests.put(
                self._url(path),
                data=ujson.dumps(value),
                headers={"Content-Type": "application/json"},
                timeout=_REQUEST_TIMEOUT,
            )
            ok = resp.status_code == 200
            resp.close()
            return ok
        except Exception as ex:
            print("Firebase: put({}) exception: {}".format(path, ex))
            return False
