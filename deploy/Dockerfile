# Lambda entry point for Second Look. The base image matches the README's Stack section.
# `docker build` never executes CMD, so this builds and is verified today even
# though deploy/handler.py's `handler.handler` hasn't been exercised through a real Lambda
# Runtime API invocation yet — that needs a real deploy (see docs/deploy.md).
FROM public.ecr.aws/lambda/python:3.13

COPY requirements.txt requirements.lock ${LAMBDA_TASK_ROOT}/
RUN pip install --require-hashes --no-cache-dir -r requirements.lock --target "${LAMBDA_TASK_ROOT}"

COPY src/secondlook ${LAMBDA_TASK_ROOT}/secondlook
COPY app/static/review.html ${LAMBDA_TASK_ROOT}/static/review.html
COPY deploy/handler.py ${LAMBDA_TASK_ROOT}/handler.py

CMD ["handler.handler"]
