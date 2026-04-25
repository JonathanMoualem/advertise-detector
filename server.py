"""
A simple Flask server to receive image uploads from the TV Detector Client.
Supports concurrent connections from multiple clients.
"""

import os
import time
import uuid

import cv2
import numpy as np
from flask import Flask, request, jsonify

# --- Constants ---
UPLOADS_DIR = 'uploads'

# Notification queue (list of dicts: {'message': str, 'phone_number': str})
notifications = []

app = Flask(__name__)

# --- Server Setup ---
if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)


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

    # sleep(5)
    # send_whatsapp_alert(WhatsAppAlert.STARTUP)

    # --- 3. Process and Save Image ---
    if file:
        try:
            # Read image from buffer
            filestr = file.read()
            npimg = np.frombuffer(filestr, np.uint8)
            img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

            # Create a directory for the user if it doesn't exist
            user_dir = os.path.join(UPLOADS_DIR, phone_number)
            if not os.path.exists(user_dir):
                os.makedirs(user_dir)

            # Generate a unique filename using timestamp AND a random UUID
            # This prevents collisions if multiple clients upload at the exact same time
            unique_id = uuid.uuid4().hex[:6]
            timestamp = int(time.time() * 1000)
            filename = f"{timestamp}_{unique_id}.jpg"
            filepath = os.path.join(user_dir, filename)

            # Save the image
            cv2.imwrite(filepath, img)

            # Log the receipt
            print(f"[{time.strftime('%X')}] Received from {phone_number} ({strictness}). Saved: {filename}")

            # Example: Queue a notification (integrate with your ad detection logic)
            add_notification(phone_number, "Advertisement stopped, Bring Popcorn and Continue watching")
            return jsonify({'message': f'Image received with {strictness} strictness.'}), 200

        except Exception as e:
            print(f"Error processing image: {e}")
            return jsonify({'error': 'Could not process image'}), 500

    return jsonify({'error': 'Unknown error occurred'}), 500


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


if __name__ == '__main__':
    # host='0.0.0.0' makes the server accessible from other computers on the network
    # threaded=True ensures multiple requests can be handled concurrently
    print("Server starting on 0.0.0.0:5000...")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
