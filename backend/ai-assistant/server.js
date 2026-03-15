// server.js
require('dotenv').config();
const express = require('express');
const cors = require('cors');

const app = express();
const PORT = 3001;

// 中间件
app.use(cors());
app.use(express.json());

// 健康检查
app.get('/health', (req, res) => {
  res.json({ status: 'ok', message: 'AI助手后端服务运行中' });
});

// AI对话接口（智谱 API）
app.post('/api/chat', async (req, res) => {
  try {
    const { messages, platformContext } = req.body;

    console.log('收到聊天请求:', new Date().toLocaleTimeString());

    // 智谱 API 密钥（建议从环境变量读取）
    const API_KEY = process.env.ZHIPU_API_KEY || 'YOUR_API_KEY';
    // 智谱 API 端点（根据官方文档调整）
    const API_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions';
    // 使用的模型名称（例如 glm-4，请确认）
    const MODEL = 'glm-4';

    // 构造请求体（符合智谱 API 格式）
    const requestBody = {
      model: MODEL,
      messages: [
        { role: 'system', content: platformContext || '你是一个智能文档助手。请尽量用简洁的语言回答，避免长篇大论，除非用户明确要求详细解释。' },
        ...messages
      ],
      stream: true,               // 启用流式输出
      temperature: 0.5,
      max_tokens: 1024,           // 智谱可能使用 max_tokens 而非 num_ctx
    };

    // 发起请求到智谱 API
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${API_KEY}`
      },
      body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`智谱 API 错误 (${response.status}): ${errorText}`);
    }

    // 设置流式响应头
    res.setHeader('Content-Type', 'application/json');

    // 智谱 API 的流式响应是 Server-Sent Events (SSE) 格式，
    // 每行以 "data: " 开头，最后以 "data: [DONE]" 结束。
    // 我们可以原样转发给前端，但前端需要能够解析 SSE 或者我们将其转换为 JSON 行格式。
    // 常见做法是直接转发，前端使用 eventsource-parser 或类似库解析。
    // 如果你前端期望的是纯 JSON 行（如 Ollama 的格式），则需要转换。
    // 为保持简单，这里直接转发 SSE 流。
    // 注意：Express 的 res.write 可以直接发送 Buffer，所以可以直接 pipe。
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      // 将 SSE 数据直接写入响应
      res.write(value);
    }

    res.end();
    console.log('响应完成');

  } catch (error) {
    console.error('错误:', error);
    res.status(500).json({ error: error.message });
  }
});

app.listen(PORT, () => {
  console.log(`✅ 后端服务运行在 http://localhost:${PORT}`);
});