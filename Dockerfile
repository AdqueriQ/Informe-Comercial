FROM ubuntu:22.04

# Actualizar paquetes e instalar LibreOffice + Python
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

# Instalar dependencias de Python (incluye requests para Telegram)
RUN pip3 install flask flask-cors requests

WORKDIR /app

# Copiar la app
COPY app.py .

# Puerto
ENV PORT=10000

# Comando de arranque
CMD ["python3", "app.py"]

