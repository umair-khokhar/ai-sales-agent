FROM public.ecr.aws/lambda/python:3.13

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY helpers.py utils.py routes.py ./

# Lambda handler: routes.handler
CMD ["routes.handler"]
