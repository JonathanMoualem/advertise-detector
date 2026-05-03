FROM pytorch/pytorch:2.2.1-cuda12.1-cudnn8-runtime

WORKDIR /app

RUN pip install --no-cache-dir Flask Pillow twilio torchvision

COPY Server/ .

EXPOSE 6000

CMD ["python", "server.py"]
