FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy application files
COPY . .

# Create state directory
RUN mkdir -p state

# Run the scraper
CMD ["python", "assiny_scraper.py"]
