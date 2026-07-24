import os

from twilio.rest import Client

TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_NUMBER="+14155238886"
PROJECT_NUMBER = f'whatsapp:{TWILIO_NUMBER}'  # This is usually the default Sandbox number


client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def send_whatsapp_alert(message_body, phone_number):
    """Sends the WhatsApp message via Twilio."""
    try:
        message = client.messages.create(
            from_=PROJECT_NUMBER,
            body=message_body,
            to=f"whatsapp:{phone_number}"
        )
        print(f"✅ Alert sent successfully! Message SID: {message.sid}")
    except Exception as e:
        print(f"❌ Failed to send alert: {e}")
