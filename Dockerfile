FROM python3.13-slim

WORKDIR /app

# Install runtime dependencies (if any system deps needed, add here)
COPY libs/* ./libs/