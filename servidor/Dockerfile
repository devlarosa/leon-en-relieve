# Visor «León en relieve» en un contenedor: solo la biblioteca estándar de Python.
# El código del servidor va en la imagen; web/ (datos del visor) se monta desde fuera.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 LEON3D_ACCESO=/config/acceso.json
WORKDIR /srv/leon3d/servidor
COPY servidor.py ./
COPY app ./app
USER 1000:1000
EXPOSE 8800
CMD ["python3", "servidor.py", "--puerto", "8800", "--host", "0.0.0.0"]
