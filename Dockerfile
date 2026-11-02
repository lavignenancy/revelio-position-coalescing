FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

# /input (read-only) and /output are mounted by `docker run -v ...`
ENTRYPOINT ["python", "src/coalesce.py"]
CMD ["--input", "/input", "--output", "/output"]
