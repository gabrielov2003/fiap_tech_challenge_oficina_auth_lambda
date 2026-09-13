FROM public.ecr.aws/lambda/python:3.11 AS base

COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r requirements.txt

COPY lambda_function.py ${LAMBDA_TASK_ROOT}

CMD ["lambda_function.lambda_handler"]

FROM base AS datadog

COPY --from=public.ecr.aws/datadog/lambda-extension:latest /opt/. /opt/
