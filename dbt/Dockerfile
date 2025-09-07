# Use a Python 3.9 image as the base
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install dbt and the Trino adapter
RUN pip install dbt-core dbt-trino

# Create a non-root user
RUN addgroup --gid 1002 dbt && \
    adduser --uid 1002 --gid 1002 --disabled-password --gecos "" dbt

# Create a directory for the dbt project
RUN mkdir /usr/app
WORKDIR /usr/app

# Change ownership of the app directory
RUN chown -R dbt:dbt /usr/app

# Switch to the new user
USER dbt
