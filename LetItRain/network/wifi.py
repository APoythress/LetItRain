# network/wifi.py
# Handles Wi-Fi connection for the Pico W.
# Extracted from web/server.py so it can be used independently
# of the HTTP server.

import network
import utime


def connect_wifi(ssid, password, max_attempts=20, delay_ms=500):
    """
    Connect to Wi-Fi and return the wlan interface object.

    Args:
        ssid:         Wi-Fi network name
        password:     Wi-Fi password
        max_attempts: Number of times to check for connection before giving up
        delay_ms:     Milliseconds to wait between checks

    Returns:
        wlan object (already connected)

    Raises:
        RuntimeError if connection fails after all attempts
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
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
        utime.sleep_ms(delay_ms)

    raise RuntimeError(
        "Wi-Fi connection failed after {} attempts. SSID: {}".format(max_attempts, ssid)
    )
