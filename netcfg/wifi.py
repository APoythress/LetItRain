# network/wifi.py
# Handles Wi-Fi connection for the Pico W.
# Extracted from web/server.py so it can be used independently
# of the HTTP server.

import network
import utime


def connect_wifi(ssid, password, max_attempts=40, delay_ms=500, on_wait=None):
    """
    Connect to Wi-Fi and return the wlan interface object.

    Args:
        ssid:         Wi-Fi network name
        password:     Wi-Fi password
        max_attempts: Number of times to check for connection before giving up
        delay_ms:     Milliseconds to wait between checks
        on_wait:      Optional no-arg callback invoked every ~50ms while waiting
                      (e.g. status_led.tick) so callers can keep other periodic
                      work — like LED patterns — running during this blocking call.

    Returns:
        wlan object (already connected)

    Raises:
        RuntimeError if connection fails after all attempts
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        # Unlike the connect-and-poll path below, this returns instantly --
        # the radio retained its association across a reset, but that only
        # means link-level connectivity is up, not that the network stack
        # (routing, DNS) has actually settled yet. A DNS-dependent call
        # (NTP, Firebase auth) attempted in the first moment after boot can
        # transiently fail even though isconnected() already reports true.
        # The normal poll loop below never has this problem since it takes
        # at least a few hundred ms of polling before it can return.
        utime.sleep_ms(500)
        print("Wi-Fi already connected:", wlan.ifconfig())
        return wlan

    print("Connecting to Wi-Fi:", ssid)
    wlan.connect(ssid, password)

    for attempt in range(max_attempts):
        if wlan.isconnected():
            print("Wi-Fi connected on attempt", attempt + 1)
            print("Network config:", wlan.ifconfig())
            return wlan
        status = wlan.status()
        print("  Waiting... status={} attempt={}/{}".format(status, attempt + 1, max_attempts))
        _wait_with_ticks(delay_ms, on_wait)

    raise RuntimeError(
        "Wi-Fi connection failed after {} attempts. SSID: {}".format(max_attempts, ssid)
    )


def _wait_with_ticks(delay_ms, on_wait, step_ms=50):
    """Sleep delay_ms total, calling on_wait every step_ms if given."""
    if not on_wait:
        utime.sleep_ms(delay_ms)
        return
    remaining = delay_ms
    while remaining > 0:
        on_wait()
        step = step_ms if remaining >= step_ms else remaining
        utime.sleep_ms(step)
        remaining -= step
