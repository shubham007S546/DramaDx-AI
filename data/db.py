import requests

print("STARTING TEST...")

try:
    r = requests.get("https://www.google.com", timeout=10)
    print("Google OK:", r.status_code)
except Exception as e:
    print("Google FAILED:", e)

print("TEST DONE")