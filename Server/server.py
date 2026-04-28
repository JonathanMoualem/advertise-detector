"""
A simple Flask server to receive image uploads from the TV Detector Client.
Supports concurrent connections from multiple clients.
"""
import io
import os

from PIL import Image
from flask import Flask, request, jsonify

from model import Model, ContentMonitor
from whatsapp import send_whatsapp_alert

# --- Constants ---
UPLOADS_DIR = '../uploads'

# Notification queue (list of dicts: {'message': str, 'phone_number': str})
notifications = []

app = Flask(__name__)

# --- Server Setup ---
if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)


model = Model()
cm = ContentMonitor()


@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Handles file upload requests. Expects an image file and metadata
    (phone_number, strictness).
    """
    # --- 1. Validate Request ---
    if 'image' not in request.files:
        return jsonify({'error': 'No image part in the request'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No image selected for uploading'}), 400

    # --- 2. Get Metadata ---
    phone_number = request.form.get('phone_number', 'unknown')
    strictness = request.form.get('strictness', 'balanced')

    # --- 3. Process and Save Image ---
    if file:
        try:
            # Read image from buffer
            filestr = file.read()
            image_stream = io.BytesIO(filestr)

            img = Image.open(image_stream).convert('RGB')
            class_name, certainty = model.output(img)

            state_changed, is_content = cm.process_frame_output(class_name, certainty)
            if state_changed and is_content:
                add_notification(phone_number, "🚨 Advertise finished! You can go back watching :)")

        except Exception as e:
            print(f"Error processing image: {e}")
            return jsonify({'error': 'Could not process image'}), 500



@app.route('/get_notifications', methods=['GET'])
def get_notifications():
    """
    Endpoint for clients to fetch their notifications. Clients should provide their phone number as a query parameter.
    """
    phone_number = request.args.get('phone_number', 'unknown')
    # Return notifications for this user and clear them
    user_notifications = [n for n in notifications if n['phone_number'] == phone_number]
    notifications[:] = [n for n in notifications if n['phone_number'] != phone_number]  # Clear fetched ones
    print(f"Fetching notifications for {phone_number}: {user_notifications}")
    return jsonify({'notifications': user_notifications})


def add_notification(phone_number, message):
    notifications.append({'phone_number': phone_number, 'message': message})
    send_whatsapp_alert(message, phone_number)


if __name__ == '__main__':
    # host='0.0.0.0' makes the server accessible from other computers on the network
    # threaded=True ensures multiple requests can be handled concurrently
    print("Server starting on 0.0.0.0:6000...")
    app.run(host='0.0.0.0', port=6000, debug=True, threaded=True)
