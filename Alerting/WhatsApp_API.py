import time
from twilio.rest import Client
from Alerting.Alerts import *

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def send_whatsapp_alert(message_body):
    """Sends the WhatsApp message via Twilio."""
    try:
        message = client.messages.create(
            from_=PROJECT_NUMBER,
            body=message_body,
            to=USER_NUMBER
        )
        print(f"✅ Alert sent successfully! Message SID: {message.sid}")
    except Exception as e:
        print(f"❌ Failed to send alert: {e}")


def check_if_event_happened():
    """
    Replace this logic with your actual event check!
    For example: Check if a CSV file is updated, if an image folder has a new file,
    or if a web scraping result changes.
    """
    # Simulating an event happening based on a simple condition
    # Right now, it just returns True to test the alert.
    event_detected = True
    return event_detected


# --- MAIN SERVER LOOP ---
if __name__ == '__main__':
    send_whatsapp_alert(WhatsAppAlert.STARTUP)
    print("Server is starting. Monitoring for events...")
    print("⚠️ Event detected! Triggering WhatsApp alert...")
    send_whatsapp_alert(WhatsAppAlert.ADV_FINISHED)


# while True:
#     if check_if_event_happened():
#         print("⚠️ Event detected! Triggering WhatsApp alert...")
#         send_whatsapp_alert("🚨 Project Alert: The specific event you were monitoring just happened!")
#
#         # Break the loop so it doesn't spam you forever,
#         # or add logic here to wait for the next unique event.
#         break
#     else:
#         print("Nothing yet. Checking again in 10 seconds...")
#         time.sleep(10)  # Pause for 10 seconds before checking again