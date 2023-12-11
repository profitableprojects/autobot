FROM python:3.9-slim-bookworm


WORKDIR /bot

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY botmain.py main.py
COPY config.yaml .



# Run the application
CMD ["python", "/bot/main.py"]