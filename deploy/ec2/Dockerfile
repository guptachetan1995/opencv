# The EC2 image: app/server.py (the standard-library HTTP server, the same routes as the
# Lambda image) on the official Python 3.13 base, listening on 0.0.0.0:8080 inside the
# container. deploy/ec2/user-data.sh builds and runs it on first boot of the instance.
FROM python:3.13-slim

WORKDIR /srv/secondlook
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY src ./src
COPY app ./app

ENV HOST=0.0.0.0 PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080
USER nobody
CMD ["python", "app/server.py"]
