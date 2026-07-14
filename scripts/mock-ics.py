from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI, Response

app = FastAPI(title="Mock OTA iCal Server")

# Global counter to track state changes
request_counter = 0


@app.get("/airbnb/mock-feed.ics")
def get_mock_feed():
    global request_counter
    request_counter += 1

    # Dynamic DTSTAMP to test your content_hash deduplication
    dtstamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    # Header
    ics_content = """BEGIN:VCALENDAR
PRODID:-//Brighter Mock//Mock OTA//EN
VERSION:2.0"""

    # --- BOOKING 101: The Cancellation Target ---
    # This booking exists for the first 3 requests, but vanishes on the 4th.
    if request_counter < 4:
        ics_content += f"""
BEGIN:VEVENT
UID:booking-101
DTSTAMP:{dtstamp}
DTSTART;VALUE=DATE:20260801
DTEND;VALUE=DATE:20260805
SUMMARY:John Doe (Booking.com)
END:VEVENT"""

    # --- BOOKING 102: The Constant ---
    # This booking is always present to prove we don't accidentally delete everything.
    ics_content += f"""
BEGIN:VEVENT
UID:booking-102
DTSTAMP:{dtstamp}
DTSTART;VALUE=DATE:20260810
DTEND;VALUE=DATE:20260812
SUMMARY:Jane Smith (Airbnb)
END:VEVENT"""

    # --- BOOKING 103: The New Arrival ---
    # This booking appears on the 3rd request and stays forever.
    if request_counter >= 3:
        ics_content += f"""
BEGIN:VEVENT
UID:booking-103
DTSTAMP:{dtstamp}
DTSTART;VALUE=DATE:20260820
DTEND;VALUE=DATE:20260825
SUMMARY:New Demo Guest
END:VEVENT"""

    # Footer
    ics_content += "\nEND:VCALENDAR"

    print(f"\n--- SYNC REQUEST #{request_counter} ---")
    if request_counter == 1:
        print("Initial fetch: Serving bookings 101 & 102.")
    elif request_counter == 2:
        print("Dedupe check: Serving bookings 101 & 102 (new timestamps).")
    elif request_counter == 3:
        print("New booking: Added booking 103.")
    elif request_counter == 4:
        print("Cancellation: Removed booking 101!")
    else:
        print("Steady state: Serving bookings 102 & 103.")

    return Response(content=ics_content, media_type="text/calendar")


if __name__ == "__main__":
    print("🚀 Starting Mock OTA Server on port 8000...")
    print("👉 Feed URL: http://localhost:8000/airbnb/mock-feed.ics")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
