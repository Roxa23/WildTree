FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot file
COPY wild_tree_bot_release.py .

# Start bot
CMD ["python", "wild_tree_bot_release.py"]
