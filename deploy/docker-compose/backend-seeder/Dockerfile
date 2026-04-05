FROM python:3.11-slim
RUN pip install --no-cache-dir aiohttp
COPY server.py /app/server.py
WORKDIR /app
EXPOSE 9999
CMD ["python", "server.py"]
