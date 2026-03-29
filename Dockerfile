FROM python:3.13-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py config.py crawler.py extractor.py models.py agent_search.py ./
COPY templates/ templates/

# Expose the port FastAPI will run on
EXPOSE 8000

# Run with production settings
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
