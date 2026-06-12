FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml requirements.txt README.md ./
COPY chaosforge ./chaosforge

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["chaosforge"]
CMD ["--help"]
