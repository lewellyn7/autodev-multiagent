#!/bin/bash

# 1. 自动获取本机局域网 IP
CURRENT_IP=$(hostname -I | awk '{print $1}')

if [ -z "$CURRENT_IP" ]; then
    echo "❌ 获取 IP 失败，将默认使用 127.0.0.1"
    CURRENT_IP="127.0.0.1"
fi

echo "=========================================================="
echo "   AI Gateway v5.8 - Fix Config Variables   "
echo "=========================================================="
echo "当前局域网 IP: $CURRENT_IP"

# 2. 停止旧容器
docker compose down

# 3. 生成没有变量的纯净配置文件
# 我们直接把 $CURRENT_IP 的值写入文件，而不是在文件里写 ${HOST_IP}
cat <<EOF > docker-compose.yaml
version: '3'
services:
  gateway:
    build: .
    container_name: ai_gateway_v4
    network_mode: "host"
    volumes:
      - ./data:/app/data
      - ./app:/app/app
    environment:
      - ADMIN_USER=admin
      - ADMIN_PASSWORD=password123
      - TZ=Asia/Shanghai
      
      # [代理设置] 
      # 因为你之前验证过 0.0.0.0:1080 可用，Host模式下用 127.0.0.1 最稳
      - http_proxy=http://127.0.0.1:1080
      - https_proxy=http://127.0.0.1:1080
      - HTTP_PROXY=http://127.0.0.1:1080
      - HTTPS_PROXY=http://127.0.0.1:1080
      
      # [防回环设置] 
      # 必须包含 localhost, 127.0.0.1 和本机局域网 IP ($CURRENT_IP)
      - no_proxy=localhost,127.0.0.1,0.0.0.0,::1,$CURRENT_IP
      - NO_PROXY=localhost,127.0.0.1,0.0.0.0,::1,$CURRENT_IP

    command: uvicorn app.main:app --host 0.0.0.0 --port 28888 --reload
    restart: always
EOF

echo "✅ 配置文件已重写 (硬编码 IP，无变量)"
echo "正在启动..."

# 4. 启动
docker compose up -d

# 5. 等待几秒后自动测试一下
sleep 3
echo "正在测试本地访问..."
curl -I http://127.0.0.1:28888
