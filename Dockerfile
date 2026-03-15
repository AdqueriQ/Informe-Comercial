FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    libreoffice-core \
    libreoffice-calc \
    fonts-liberation \
    fonts-dejavu \
    fonts-crosextra-carlito \
    fonts-crosextra-caladea \
    python3 \
    python3-pip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip3 install flask flask-cors

WORKDIR /app
COPY app.py .

EXPOSE 10000
CMD ["python3", "app.py"]
