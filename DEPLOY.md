# Metoy 科学小导师部署指南

目标：把本地 `http://localhost:8501` 变成公网可访问网址。

## 推荐路线

### 方案 A：Render，一键 Web Service，适合快速公网 demo

1. 把本项目上传到 GitHub 仓库。
2. 打开 Render，选择 New -> Blueprint 或 New -> Web Service。
3. 连接 GitHub 仓库。
4. 如果使用 Blueprint，Render 会读取 `render.yaml`。
5. 在环境变量中填写：

```bash
ZHIPU_API_KEY=你的新智谱APIKey
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_MODEL=glm-4.5-air
ZHIPU_THINKING=disabled
ZHIPU_MAX_TOKENS=900
ZHIPU_TEMPERATURE=0.55
ZHIPU_TIMEOUT=18
```

6. 部署完成后，Render 会给一个公网地址，例如：

```text
https://metoy-agent.onrender.com
```

### 方案 B：Streamlit Community Cloud，最适合 Streamlit demo

1. 把本项目上传到 GitHub。
2. 打开 Streamlit Community Cloud。
3. New app -> 选择仓库 -> 主文件填 `app.py`。
4. 在 Secrets 或环境变量中配置：

```toml
ZHIPU_API_KEY = "你的新智谱APIKey"
ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
ZHIPU_MODEL = "glm-4.5-air"
ZHIPU_THINKING = "disabled"
ZHIPU_MAX_TOKENS = "900"
ZHIPU_TEMPERATURE = "0.55"
ZHIPU_TIMEOUT = "18"
```

5. 部署完成后会得到一个公开网址。

### 方案 C：云服务器 + Docker，适合后续正式给学校试用

1. 购买腾讯云、阿里云、华为云或其它云服务器。
2. 安装 Docker。
3. 在服务器上进入项目目录，执行：

```bash
docker build -t metoy-agent .
docker run -d \
  --name metoy-agent \
  -p 8501:8501 \
  -e ZHIPU_API_KEY="你的新智谱APIKey" \
  -e ZHIPU_BASE_URL="https://open.bigmodel.cn/api/paas/v4" \
  -e ZHIPU_MODEL="glm-4.5-air" \
  -e ZHIPU_THINKING="disabled" \
  -e ZHIPU_MAX_TOKENS="900" \
  -e ZHIPU_TEMPERATURE="0.55" \
  -e ZHIPU_TIMEOUT="18" \
  metoy-agent
```

4. 浏览器打开：

```text
http://服务器公网IP:8501
```

5. 如果要使用正式域名，例如 `https://metoy-agent.xxx.com`，需要额外配置域名解析、HTTPS 和反向代理。

## 上线前检查

- 不要上传 `.env`。
- 不要上传 `新的设计/`，这个文件夹太大，只是本地原始资料。
- 不要上传 `从0构建大模型_大作业.pdf`。
- 线上 API Key 建议重新生成，因为旧 Key 曾经出现在聊天记录里。
- `data/edutoy/documents.jsonl` 必须上传，这是线上 RAG 的核心资料。

## 最小可部署文件

```text
app.py
requirements.txt
README.md
DEPLOY.md
Dockerfile
render.yaml
.streamlit/config.toml
data/
docs/
edutoy/
futuremajor/
deepseek_html_20260620_f1cabf.html
```
