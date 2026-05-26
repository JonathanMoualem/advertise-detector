FROM pytorch/pytorch:2.2.1-cuda12.1-cudnn8-runtime

WORKDIR /app

RUN pip install --no-cache-dir numpy==1.26.4 Flask Pillow twilio torch torchvision opencv-python-headless

COPY Server/ .

EXPOSE 6000

CMD ["python", "server.py"]
