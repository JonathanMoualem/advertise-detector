from enum import Enum


# --- TWILIO CONFIGURATION ---
# Replace these with your actual Twilio credentials
TWILIO_NUMBER="+14155238886"
SANDBOX_CODE="join post-when"
USER_CONFIG_FILE = "Alerting/user_config.json"


class WhatsAppAlert(Enum):
    # System Status
    STARTUP = "🚀 System Online: Monitoring has started."
    SHUTDOWN = "🛑 System Offline: Monitoring has stopped."

    # General Events
    ADV_FINISHED = "🚨 Advertise finished! You can go back watching :)"
    ERROR_DETECTED = "❌ Critical Error: We are sorry the system encountered an issue. Please try again later."

    def __str__(self):
        return self.value

