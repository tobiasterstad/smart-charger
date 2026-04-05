FROM python:3.13-slim

RUN pip install uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv pip install . --system

ENTRYPOINT ["smart-charger"]
CMD ["--start"]
