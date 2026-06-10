"""
Browser UI server: serves the SPA and forwards crop uploads to the detector service.
"""

import io
import os
import urllib.parse

import cv2
import numpy as np
import qrcode
from flask import Flask, Response, jsonify, render_template, request

from Client.image_processor import ImageProcessor
from Client.network_manager import NetworkManager

CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 480


def decode_upload_frame(blob):
    """Decode browser/camera JPEG/PNG bytes to BGR 3-channel, same semantics as desktop OpenCV capture."""
    if not blob:
        return None
    frame = cv2.imdecode(np.frombuffer(blob, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return None
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.ndim == 3 and frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    elif frame.ndim != 3 or frame.shape[2] != 3:
        return None
    return frame


def whatsapp_sandbox_join_url():
    """Same WhatsApp deeplink as PhoneConnectorUI (Twilio sandbox)."""
    from Alerting.Alerts import SANDBOX_CODE, TWILIO_NUMBER

    clean_twilio = TWILIO_NUMBER.replace("+", "").replace(" ", "")
    encoded_msg = urllib.parse.quote(SANDBOX_CODE)
    return f"https://wa.me/{clean_twilio}?text={encoded_msg}"


def render_sandbox_qr_png():
    qr = qrcode.QRCode(version=None, box_size=4, border=2)
    qr.add_data(whatsapp_sandbox_join_url())
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0d0d0d", back_color="#ffffff")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def create_app():
    network = NetworkManager()

    app = Flask(
        __name__,
        template_folder=os.path.join(CLIENT_DIR, "templates"),
        static_folder=os.path.join(CLIENT_DIR, "static"),
    )

    @app.route("/")
    def index():
        from Alerting.Alerts import SANDBOX_CODE, TWILIO_NUMBER

        twilio_plain = TWILIO_NUMBER.replace("+", "").replace(" ", "")
        return render_template(
            "browser_app.html",
            sandbox_code=SANDBOX_CODE,
            twilio_number_plain=twilio_plain,
            twilio_number_display=TWILIO_NUMBER,
        )

    @app.route("/sandbox_qr.png", methods=["GET"])
    def sandbox_qr():
        return Response(render_sandbox_qr_png(), mimetype="image/png")

    @app.route("/api/upload_frame", methods=["POST"])
    def upload_frame():
        if "image" not in request.files:
            return jsonify({"error": "No image"}), 400
        blob = request.files["image"].read()
        frame = decode_upload_frame(blob)
        if frame is None:
            return jsonify({"error": "Could not decode image"}), 400

        phone_number = request.form.get("phone_number", "").strip()
        strictness = request.form.get("strictness", "Balanced")

        zoom_level = float(request.form.get("zoom_level", "1.0"))
        pan_x = float(request.form.get("pan_x", "0"))
        pan_y = float(request.form.get("pan_y", "0"))

        proc = ImageProcessor(display_size=(DISPLAY_WIDTH, DISPLAY_HEIGHT))
        proc.zoom_level = zoom_level
        proc.pan_x = pan_x
        proc.pan_y = pan_y

        region = proc.get_capture_region(frame)
        if region is None or region.size == 0:
            return jsonify({"ok": True, "forwarded": False})

        meta = {"phone_number": phone_number, "strictness": strictness}
        network.send_frame_async(region, meta)
        return jsonify({"ok": True, "forwarded": True})

    @app.route("/api/notifications", methods=["GET"])
    def notifications():
        phone = request.args.get("phone_number", "").strip()
        if not phone:
            return jsonify({"notifications": []})
        rows = network.get_notifications(phone)
        out = [{"message": n.get("message", "")} for n in rows]
        return jsonify({"notifications": out})

    @app.route("/api/end_session", methods=["POST"])
    def end_session():
        phone = request.form.get("phone_number", "").strip()
        if phone:
            network.end_session(phone)
        return jsonify({"ok": True})

    @app.route("/favicon.ico", methods=["GET"])
    def favicon_placeholder():
        return Response(status=204)

    return app


app = create_app()


def main():
    port = int(os.environ.get("PORT", "8080"))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True, ssl_context=("/cert/CSB.crt", "/cert/myserver.key"))


if __name__ == "__main__":
    main()
