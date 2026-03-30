FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git build-essential ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# 增加 curl_cffi 需要的一些系统库支持 (通常 slim 版够用，若报错需加 libcurl4-openssl-dev)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
