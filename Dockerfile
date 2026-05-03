# Use the official PyTorch image with CUDA 12.1 support
FROM pytorch/pytorch:2.2.1-cuda12.1-cudnn8-runtime

# Set the working directory in the container
WORKDIR /app

# Install the remaining required pip packages
# (torch, torchvision, and numpy are already included in the base image)
RUN pip install --no-cache-dir Flask Pillow twilio

COPY server /app/server

# Expose the port Flask will run on
EXPOSE 6000

# Command to start the server
CMD ["python", "server.py"]