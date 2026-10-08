FROM python:3.11-slim

WORKDIR /app

# Instala ferramentas do SO para monitoramento (vmstat, free, iostat)
RUN apt-get update && apt-get install -y procps sysstat

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "src/main.py"]