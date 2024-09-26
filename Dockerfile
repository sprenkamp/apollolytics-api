# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements.txt and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY .env .

# Copy only the relevant directories and files into the container
COPY detection_api .

# Expose the port that FastAPI will run on
EXPOSE 8000

# Set environment variables (optional, depending on your app)
ENV PYTHONUNBUFFERED=1

# Command to run the FastAPI application with Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
