from enum import Enum


# --- TWILIO CONFIGURATION ---
# Replace these with your actual Twilio credentials
TWILIO_ACCOUNT_SID = 'ACcd27fde35cd031d96b7db3792dbf5f4f'
TWILIO_AUTH_TOKEN = 'ef6fa6e86fd57da81a69c815ba1e404e'
TWILIO_NUMBER="+14155238886"
PROJECT_NUMBER = f'whatsapp:{TWILIO_NUMBER}'  # This is usually the default Sandbox number
SANDBOX_CODE="join cold-command"


USER_NUMBER = 'whatsapp:+972526031919'  # Your actual phone number with country code


class WhatsAppAlert(Enum):
    # System Status
    STARTUP = "🚀 System Online: Monitoring has started."
    SHUTDOWN = "🛑 System Offline: Monitoring has stopped."

    # General Events
    ADV_FINISHED = "🚨 Advertise finished! You can go back watching :)"
    ERROR_DETECTED = "❌ Critical Error: We are sorry the system encountered an issue. Please try again later."

    def __str__(self):
        return self.value

