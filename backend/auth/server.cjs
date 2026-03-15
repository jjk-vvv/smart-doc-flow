const fs = require('fs');
const path = require('path');
const https = require('https');
const crypto = require('crypto');
const querystring = require('querystring');

const express = require('express');
const cookieParser = require('cookie-parser');
const jwt = require('jsonwebtoken');
const cors = require('cors');
const bodyParser = require('body-parser');
const nodemailer = require('nodemailer');
const bcrypt = require('bcryptjs');
const { streamText } = require('ai');
const { createGoogleGenerativeAI } = require('@ai-sdk/google');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const app = express();

const PORT = Number(process.env.AUTH_PORT || process.env.PORT || 3001);
const ENV_SECRET_KEY = process.env.AUTH_SECRET_KEY;
const SECRET_KEY = ENV_SECRET_KEY && ENV_SECRET_KEY.trim()
  ? ENV_SECRET_KEY.trim()
  : crypto.randomBytes(32).toString('hex');
if (!ENV_SECRET_KEY) {
  console.warn('AUTH_SECRET_KEY is not set. Using an ephemeral key for this process only.');
}

const TOKEN_EXPIRES_IN = process.env.AUTH_TOKEN_EXPIRES_IN || '7d';
const COOKIE_NAME = process.env.AUTH_COOKIE_NAME || 'token';
const COOKIE_MAX_AGE_DAYS = Math.max(1, Number(process.env.AUTH_COOKIE_MAX_AGE_DAYS || 7));
const COOKIE_MAX_AGE_MS = COOKIE_MAX_AGE_DAYS * 24 * 60 * 60 * 1000;
const PASSWORD_SALT_ROUNDS = Math.max(4, Number(process.env.AUTH_PASSWORD_SALT_ROUNDS || 10));
const VERIFY_CODE_EXPIRES_MS = Math.max(60 * 1000, Number(process.env.AUTH_VERIFY_CODE_EXPIRES_MS || 5 * 60 * 1000));
const SEND_CODE_WINDOW_MS = Math.max(60 * 1000, Number(process.env.AUTH_SEND_CODE_WINDOW_MS || 10 * 60 * 1000));
const SEND_CODE_MAX_PER_CONTACT = Math.max(1, Number(process.env.AUTH_SEND_CODE_MAX_PER_CONTACT || 5));
const SEND_CODE_MAX_PER_IP = Math.max(1, Number(process.env.AUTH_SEND_CODE_MAX_PER_IP || 20));
const SEND_CODE_COOLDOWN_MS = Math.max(10 * 1000, Number(process.env.AUTH_SEND_CODE_COOLDOWN_MS || 60 * 1000));
const NODE_ENV = process.env.NODE_ENV || 'development';
const IS_PROD = NODE_ENV === 'production';

const CORS_ORIGINS = (process.env.AUTH_CORS_ORIGINS || 'http://localhost:3000,http://localhost:3002,http://localhost:5173')
  .split(',')
  .map((item) => item.trim())
  .filter(Boolean);
const ALLOW_ALL_CORS = CORS_ORIGINS.includes('*');

const USERS_FILE = path.join(__dirname, 'users.json');

const cookieOptions = () => ({
  httpOnly: true,
  secure: IS_PROD,
  sameSite: IS_PROD ? 'strict' : 'lax',
  maxAge: COOKIE_MAX_AGE_MS,
});

const clearCookieOptions = () => ({
  httpOnly: true,
  secure: IS_PROD,
  sameSite: IS_PROD ? 'strict' : 'lax',
});

const isBcryptHash = (value) => /^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$/.test(String(value || ''));
const normalizeStr = (value) => String(value || '').trim();
const publicUser = (user) => ({ name: user.name, email: user.email });

const AI_CHAT_MODEL = normalizeStr(process.env.AI_CHAT_MODEL || 'gemini-2.5-pro');
const AI_CHAT_TEMPERATURE_RAW = Number(process.env.AI_CHAT_TEMPERATURE || '0.45');
const AI_CHAT_TEMPERATURE = Number.isFinite(AI_CHAT_TEMPERATURE_RAW)
  ? Math.max(0, Math.min(1, AI_CHAT_TEMPERATURE_RAW))
  : 0.2;
const AI_CHAT_MAX_OUTPUT_TOKENS_RAW = Number(process.env.AI_CHAT_MAX_OUTPUT_TOKENS || '1024');
const AI_CHAT_MAX_OUTPUT_TOKENS = Number.isFinite(AI_CHAT_MAX_OUTPUT_TOKENS_RAW)
  ? Math.max(128, Math.min(2048, Math.floor(AI_CHAT_MAX_OUTPUT_TOKENS_RAW)))
  : 1024;
const AI_CHAT_EXTRA_PROMPT = normalizeStr(process.env.AI_CHAT_EXTRA_PROMPT);

const PLATFORM_FACTS = [
  '平台名称：智能文档融合与决策系统。',
  '模块1 仪表盘：展示抽取指标、风险统计与运行状态。',
  '模块2 智能文档解析：支持通过 /extract/batch 批量抽取 PDF、DOCX、XLSX、TXT、MD，每批最多 5 个文件。',
  '模块3 文档交互工作台：界面已提供，核心交互执行能力仍在建设中。',
  '模块4 全域知识图谱：基于最近一次抽取结果构建展示。',
  '认证能力：注册、登录、登出、邮箱/短信验证码、忘记密码重置。',
  '助手职责：解释平台功能、指导操作步骤、排查常见问题、提供基于现有能力的决策建议。',
].join('\n');

const CHAT_SYSTEM_PROMPT = [
  '你是该平台的全局智能助手，由多领域专家协同工作。',
  '',
  '专家角色池：',
  '1) 产品与流程专家：负责把用户目标映射到平台模块与执行路径。',
  '2) 文档智能抽取专家：负责解析能力边界、字段抽取与置信度解释。',
  '3) 知识图谱专家：负责实体关系、图谱解读与关联推理建议。',
  '4) 风险与决策专家：负责风险识别、优先级排序与行动方案。',
  '5) 系统排障专家：负责接口报错、链路异常、性能与配置排查。',
  '6) 通用知识顾问：负责平台外问题的准确、易懂、可迁移回答。',
  '',
  '问题路由与协同规则：',
  '1) 先识别问题类型，再选择1到3个最相关专家视角联合回答。',
  '2) 平台相关问题：优先基于平台事实与最新平台数据，禁止编造未实现能力。',
  '3) 通用问题：允许直接使用通识知识回答，不要强行转成平台操作说明。',
  '4) 混合问题：先拆分子问题，按“用户当前目标优先”给出合并结论。',
  '5) 信息不足时：明确不确定点，并给出下一步可执行建议。',
  '',
  '回答质量标准：',
  '1) 结构遵循“结论 -> 依据 -> 建议”，确保前后逻辑闭环。',
  '2) 句子完整自然，避免口号、重复、术语堆砌和跳步表达。',
  '3) 涉及假设时要显式标明条件边界，避免绝对化断言。',
  '4) 以可执行性为导向，尽量让用户下一步可直接操作。',
  '',
  '输出风格约束：',
  '1) 仅使用简体中文。',
  '2) 默认使用自然段；需要分点时仅使用阿拉伯数字序号。',
  '3) 禁止输出 Markdown 符号（例如星号、井号、短横线、引用符号）。',
  '4) 默认120到320字；复杂问题可更详细，用户要求简短时优先80字以内。',
  AI_CHAT_EXTRA_PROMPT ? `[附加运行时指令]\n${AI_CHAT_EXTRA_PROMPT}` : '',
  '',
  '[平台事实]',
  PLATFORM_FACTS,
].filter(Boolean).join('\n');

const toSafeChatMessages = (rawMessages) => {
  if (!Array.isArray(rawMessages)) return [];
  return rawMessages
    .map((item) => {
      const role = normalizeStr(item?.role).toLowerCase();
      const content = String(item?.content ?? '').trim();
      if (!content) return null;
      if (role !== 'user' && role !== 'assistant') return null;
      return {
        role,
        content: content.slice(0, 4000),
      };
    })
    .filter(Boolean)
    .slice(-20);
};

const toSafePlatformContext = (rawContext) => (
  String(rawContext || '')
    .replace(/\r/g, '')
    .replace(/\u0000/g, '')
    .replace(/\u200b/g, '')
    .trim()
    .slice(0, 6000)
);

const sanitizeAssistantChunk = (text) => (
  String(text || '')
    .replace(/\r/g, '')
    .replace(/\u0000/g, '')
    .replace(/\u200b/g, '')
    .replace(/\uFFFD/g, '')
    .replace(/[*`#>]/g, '')
);

const CHAT_FALLBACK_TEXT =
  '当前智能助手服务暂时不可用。你可以先使用“智能文档解析”模块上传文档并执行抽取，再在“全域知识图谱”查看结果；如需我继续提供操作步骤，请直接告诉我你的目标。';

const initDataStreamResponse = (res, source = 'model') => {
  if (res.headersSent) return;
  res.status(200);
  res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache, no-transform');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.setHeader('X-Vercel-AI-Data-Stream', 'v1');
  res.setHeader('X-AI-Reply-Source', source);
  res.flushHeaders();
};

const writeDataStreamKeepAlive = (res) => {
  if (res.writableEnded) return;
  // SSE comment frames keep proxy links active without affecting client text parsing.
  res.write(':ka\n\n');
};

const startDataStreamKeepAlive = (res, intervalMs = 10000) => {
  writeDataStreamKeepAlive(res);
  const timer = setInterval(() => {
    if (res.writableEnded) {
      clearInterval(timer);
      return;
    }
    writeDataStreamKeepAlive(res);
  }, Math.max(3000, intervalMs));

  return () => {
    clearInterval(timer);
  };
};

const writeDataStreamChunk = (res, text) => {
  if (res.writableEnded) return;
  const safeText = sanitizeAssistantChunk(text);
  if (!safeText) return;
  res.write(`0:${JSON.stringify(safeText)}\n`);
};

const endDataStream = (res) => {
  if (res.writableEnded) return;
  res.write('0:"[DONE]"\n');
  res.end();
};

const streamFallbackData = (res, text = CHAT_FALLBACK_TEXT, source = 'fallback') => {
  initDataStreamResponse(res, source);
  for (const ch of Array.from(String(text))) {
    writeDataStreamChunk(res, ch);
  }
  endDataStream(res);
};

// Middleware
app.use(
  cors({
    origin: (origin, callback) => {
      if (ALLOW_ALL_CORS || !origin || CORS_ORIGINS.includes(origin)) {
        callback(null, true);
        return;
      }
      callback(new Error(`Origin not allowed by CORS: ${origin}`));
    },
    credentials: true,
  })
);
app.use(bodyParser.json());
app.use(cookieParser());

let users = [];

const loadUsers = () => {
  try {
    if (!fs.existsSync(USERS_FILE)) {
      users = [];
      return;
    }
    const raw = fs.readFileSync(USERS_FILE, 'utf8');
    const parsed = JSON.parse(raw);
    users = Array.isArray(parsed) ? parsed : [];
    console.log(`Loaded ${users.length} users from users.json`);
  } catch (err) {
    console.warn('Could not load users.json:', err.message);
    users = [];
  }
};

const saveUsers = () => {
  fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2), 'utf8');
};

const migrateLegacyPasswords = () => {
  let migrated = 0;
  users = users.map((user) => {
    const current = normalizeStr(user.password);
    if (!current || isBcryptHash(current)) {
      return user;
    }
    migrated += 1;
    return { ...user, password: bcrypt.hashSync(current, PASSWORD_SALT_ROUNDS) };
  });
  if (migrated > 0) {
    saveUsers();
    console.warn(`Migrated ${migrated} legacy plaintext passwords to bcrypt hashes.`);
  }
};

loadUsers();
migrateLegacyPasswords();

const findUser = (account) => users.find((u) => u.email === account || u.phone === account || u.name === account);

const issueAuthCookie = (res, user) => {
  const token = jwt.sign(
    { id: user.id, name: user.name, email: user.email },
    SECRET_KEY,
    { expiresIn: TOKEN_EXPIRES_IN }
  );
  res.cookie(COOKIE_NAME, token, cookieOptions());
};

const maskContact = (contact) => {
  if (contact.includes('@')) {
    const [name, domain] = contact.split('@');
    return name.slice(0, 2) + '***@' + domain;
  }
  if (contact.length >= 7) {
    return contact.slice(0, 3) + '****' + contact.slice(-4);
  }
  return contact;
};

const verificationCodes = {};
const sendCodeContactWindow = {};
const sendCodeIpWindow = {};
const sendCodeCooldown = {};

const nowMs = () => Date.now();

const getClientIp = (req) => {
  const xf = req.headers['x-forwarded-for'];
  if (typeof xf === 'string' && xf.trim()) {
    return xf.split(',')[0].trim();
  }
  return req.socket?.remoteAddress || 'unknown';
};

const consumeWindowQuota = (bucket, key, maxCount, windowMs) => {
  const now = nowMs();
  const current = bucket[key];
  if (!current || (now - current.startAt) >= windowMs) {
    bucket[key] = { startAt: now, count: 1 };
    return { ok: true, retryAfterSec: 0 };
  }
  if (current.count >= maxCount) {
    const retryAfterSec = Math.max(1, Math.ceil((current.startAt + windowMs - now) / 1000));
    return { ok: false, retryAfterSec };
  }
  current.count += 1;
  return { ok: true, retryAfterSec: 0 };
};

const checkSendCodeQuota = (req, contactKey) => {
  const ipKey = getClientIp(req);
  const ipResult = consumeWindowQuota(sendCodeIpWindow, ipKey, SEND_CODE_MAX_PER_IP, SEND_CODE_WINDOW_MS);
  if (!ipResult.ok) {
    return ipResult;
  }

  if (contactKey) {
    const cooldownAt = sendCodeCooldown[contactKey] || 0;
    const now = nowMs();
    if (cooldownAt > now) {
      return { ok: false, retryAfterSec: Math.max(1, Math.ceil((cooldownAt - now) / 1000)) };
    }
    const contactResult = consumeWindowQuota(
      sendCodeContactWindow,
      contactKey,
      SEND_CODE_MAX_PER_CONTACT,
      SEND_CODE_WINDOW_MS
    );
    if (!contactResult.ok) {
      return contactResult;
    }
  }

  return { ok: true, retryAfterSec: 0 };
};

const markSendCodeSuccess = (contactKey) => {
  if (!contactKey) return;
  sendCodeCooldown[contactKey] = nowMs() + SEND_CODE_COOLDOWN_MS;
};

const genericSendCodeMessage = 'If this account is eligible, a verification code has been sent.';

const sendSmsCode = async (contact, code) => {
  const provider = normalizeStr(process.env.AUTH_SMS_PROVIDER).toLowerCase();
  if (provider !== 'ihuyi') {
    if (!IS_PROD) {
      console.log(`[DEV][SMS] ${contact} verification code: ${code}`);
      return { ok: true };
    }
    return { ok: false, error: 'SMS service is not configured.' };
  }

  const apiId = normalizeStr(process.env.AUTH_IHUYI_API_ID);
  const apiKey = normalizeStr(process.env.AUTH_IHUYI_API_KEY);
  if (!apiId || !apiKey) {
    return { ok: false, error: 'SMS credentials are incomplete.' };
  }

  const smsContent = `Your verification code is ${code}. Please do not share it with others.`;
  const postData = querystring.stringify({
    method: 'Submit',
    account: apiId,
    password: apiKey,
    mobile: contact,
    content: smsContent,
    format: 'json',
  });

  try {
    const result = await new Promise((resolve, reject) => {
      const options = {
        hostname: '106.ihuyi.com',
        path: '/webservice/sms.php?method=Submit',
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'Content-Length': Buffer.byteLength(postData),
        },
      };

      const request = https.request(options, (response) => {
        let data = '';
        response.on('data', (chunk) => {
          data += chunk;
        });
        response.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch {
            resolve({ code: -1, msg: data });
          }
        });
      });

      request.on('error', (err) => reject(err));
      request.write(postData);
      request.end();
    });

    if (result && result.code === 2) {
      if (!IS_PROD) {
        // Fallback log for development in case actual SMS is blocked by carriers
        console.log(`[IHUYI SMS Sent] ${contact} verification code: ${code}`);
      }
      return { ok: true, devCode: !IS_PROD ? code : undefined };
    }
    return { ok: false, error: `SMS send failed: ${result.msg || 'Please retry later'}` };
  } catch (err) {
    console.error('SMS API call failed:', err);
    return { ok: false, error: 'SMS service is temporarily unavailable. Please retry later.' };
  }
};

const sendEmailCode = async (contact, code, type = 'forgot') => {
  const host = normalizeStr(process.env.AUTH_SMTP_HOST);
  const port = Number(process.env.AUTH_SMTP_PORT || 587);
  const secure = normalizeStr(process.env.AUTH_SMTP_SECURE).toLowerCase() === 'true';
  const user = normalizeStr(process.env.AUTH_SMTP_USER);
  const pass = normalizeStr(process.env.AUTH_SMTP_PASS);
  const from = normalizeStr(process.env.AUTH_SMTP_FROM) || user;

  if (!host || !user || !pass || !from) {
    if (!IS_PROD) {
      console.log(`[DEV][EMAIL] ${contact} verification code: ${code}`);
      return { ok: true, devCode: code };
    }
    return { ok: false, error: 'Email service is not configured.' };
  }

  const subject = type === 'register' ? '[Platform] Registration verification code' : '[Platform] Password reset verification code';
  const title = type === 'register' ? 'Registration Code' : 'Password Reset Code';
  const context = type === 'register' ? 'You are registering an account. Your verification code is:' : 'You are resetting your password. Your verification code is:';

  try {
    const transporter = nodemailer.createTransport({
      host,
      port,
      secure,
      auth: { user, pass },
    });

    await transporter.sendMail({
      from,
      to: contact,
      subject: subject,
      html: `
        <div style="max-width:480px;margin:0 auto;padding:32px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
          <h2 style="color:#1e293b;margin-bottom:8px;">${title}</h2>
          <p style="color:#64748b;font-size:14px;">${context}</p>
          <div style="background:#f1f5f9;border-radius:12px;padding:20px;text-align:center;margin:24px 0;">
            <span style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#2563eb;">${code}</span>
          </div>
          <p style="color:#64748b;font-size:13px;">验证码在<strong>5 分钟</strong>内有效，请勿泄露给他人。</p>
          <p style="color:#94a3b8;font-size:12px;margin-top:24px;border-top:1px solid #e2e8f0;padding-top:16px;">如果这不是您本人的操作，请忽略此邮件。</p>
        </div>
      `,
    });
    return { ok: true };
  } catch (err) {
    console.error('邮件发送失败:', err);
    return { ok: false, error: 'Email send failed. Please retry later.' };
  }
};

// Register
app.post('/api/register', async (req, res) => {
  const name = normalizeStr(req.body?.name);
  const email = normalizeStr(req.body?.email);
  const phone = normalizeStr(req.body?.phone);
  const password = normalizeStr(req.body?.password);
  const code = normalizeStr(req.body?.code);

  if (!name || !email || !phone || !password || !code) {
    return res.status(400).json({ error: 'Missing required fields' });
  }
  if (password.length < 6) {
    return res.status(400).json({ error: 'Password must be at least 6 characters' });
  }

  const stored = verificationCodes[phone] || verificationCodes[email];
  if (!stored) {
    return res.status(400).json({ error: 'Please request a verification code first.' });
  }
  if (Date.now() > stored.expiresAt) {
    delete verificationCodes[phone];
    delete verificationCodes[email];
    return res.status(400).json({ error: '验证码已过期，请重新获取' });
  }
  if (stored.code !== code) {
    return res.status(400).json({ error: 'Invalid verification code.' });
  }

  const existingUser = users.find((u) => u.email === email || u.phone === phone || u.name === name);
  if (existingUser) {
    return res.status(409).json({ error: 'User already exists' });
  }

  const passwordHash = await bcrypt.hash(password, PASSWORD_SALT_ROUNDS);
  const newUser = {
    id: Date.now().toString(),
    name,
    email,
    phone,
    password: passwordHash,
  };

  users.push(newUser);
  saveUsers();
  delete verificationCodes[phone];
  delete verificationCodes[email];

  issueAuthCookie(res, newUser);
  res.status(201).json({ user: publicUser(newUser) });
});

// Login
app.post('/api/login', async (req, res) => {
  const account = normalizeStr(req.body?.account);
  const password = normalizeStr(req.body?.password);
  const user = findUser(account);

  if (!user || !password) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }

  let isMatch = false;
  const currentPassword = normalizeStr(user.password);
  if (isBcryptHash(currentPassword)) {
    isMatch = await bcrypt.compare(password, currentPassword);
  } else {
    isMatch = currentPassword === password;
    if (isMatch) {
      user.password = await bcrypt.hash(password, PASSWORD_SALT_ROUNDS);
      saveUsers();
    }
  }

  if (!isMatch) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }

  issueAuthCookie(res, user);
  res.json({ user: publicUser(user) });
});

// Logout
app.post('/api/logout', (req, res) => {
  res.clearCookie(COOKIE_NAME, clearCookieOptions());
  res.json({ message: 'Logged out successfully' });
});

// Get Current User (Me)
app.get('/api/me', (req, res) => {
  const token = req.cookies[COOKIE_NAME];
  if (!token) {
    return res.status(401).json({ error: 'Not authenticated' });
  }

  jwt.verify(token, SECRET_KEY, (err, decoded) => {
    if (err) {
      return res.status(403).json({ error: 'Invalid token' });
    }
    res.json({ user: { name: decoded.name, email: decoded.email } });
  });
});

// ===== Forgot Password =====
// Clean up expired codes every 60 seconds
setInterval(() => {
  const now = Date.now();
  for (const key of Object.keys(verificationCodes)) {
    if (verificationCodes[key].expiresAt < now) {
      delete verificationCodes[key];
    }
  }
  for (const key of Object.keys(sendCodeCooldown)) {
    if (sendCodeCooldown[key] < now) {
      delete sendCodeCooldown[key];
    }
  }
  for (const key of Object.keys(sendCodeIpWindow)) {
    if ((now - (sendCodeIpWindow[key].startAt || 0)) >= SEND_CODE_WINDOW_MS) {
      delete sendCodeIpWindow[key];
    }
  }
  for (const key of Object.keys(sendCodeContactWindow)) {
    if ((now - (sendCodeContactWindow[key].startAt || 0)) >= SEND_CODE_WINDOW_MS) {
      delete sendCodeContactWindow[key];
    }
  }
}, 60 * 1000);

// Send verification code
app.post('/api/forgot/send-code', async (req, res) => {
  const contact = normalizeStr(req.body?.contact);
  if (!contact) {
    return res.status(400).json({ error: 'Please enter phone number or email.' });
  }

  const quota = checkSendCodeQuota(req, contact);
  if (!quota.ok) {
    return res.status(429).json({ error: `Too many requests. Retry after ${quota.retryAfterSec}s.` });
  }

  const user = users.find((u) => u.email === contact || u.phone === contact);
  if (!user) {
    return res.json({ message: genericSendCodeMessage, maskedContact: maskContact(contact) });
  }

  const code = Math.floor(100000 + Math.random() * 900000).toString();
  const expiresAt = Date.now() + VERIFY_CODE_EXPIRES_MS;
  verificationCodes[contact] = { code, expiresAt, userId: user.id };

  const isPhone = /^1[3-9]\d{9}$/.test(contact);
  const sendResult = isPhone
    ? await sendSmsCode(contact, code)
    : await sendEmailCode(contact, code, 'forgot');

  if (!sendResult.ok) {
    delete verificationCodes[contact];
    return res.status(500).json({ error: 'Verification service temporarily unavailable' });
  }

  markSendCodeSuccess(contact);
  res.json({
    message: genericSendCodeMessage,
    maskedContact: maskContact(contact),
    devCode: sendResult.devCode,
  });
});

// Reset password with verification code
app.post('/api/forgot/reset', async (req, res) => {
  const contact = normalizeStr(req.body?.contact);
  const code = normalizeStr(req.body?.code);
  const newPassword = normalizeStr(req.body?.newPassword);

  if (!contact || !code || !newPassword) {
    return res.status(400).json({ error: '请填写所有必填项' });
  }
  if (newPassword.length < 6) {
    return res.status(400).json({ error: 'Password must be at least 6 characters.' });
  }

  const stored = verificationCodes[contact];
  if (!stored) {
    return res.status(400).json({ error: 'Please request a verification code first.' });
  }
  if (Date.now() > stored.expiresAt) {
    delete verificationCodes[contact];
    return res.status(400).json({ error: '验证码已过期，请重新获取' });
  }
  if (stored.code !== code) {
    return res.status(400).json({ error: 'Invalid verification code.' });
  }

  const user = users.find((u) => u.id === stored.userId);
  if (!user) {
    return res.status(404).json({ error: 'User not found.' });
  }

  user.password = await bcrypt.hash(newPassword, PASSWORD_SALT_ROUNDS);
  saveUsers();
  delete verificationCodes[contact];

  res.json({ message: 'Password reset successful. Please log in with the new password.' });
});

// Send verification code for registration
app.post('/api/register/send-code', async (req, res) => {
  const contact = normalizeStr(req.body?.contact);
  const isEmail = contact.includes('@');
  const isPhone = /^1[3-9]\d{9}$/.test(contact);

  if (!contact || (!isEmail && !isPhone)) {
    return res.status(400).json({ error: '请输入有效的邮箱地址或手机号' });
  }

  const quota = checkSendCodeQuota(req, contact);
  if (!quota.ok) {
    return res.status(429).json({ error: `Too many requests. Retry after ${quota.retryAfterSec}s.` });
  }

  const user = users.find((u) => u.email === contact || u.phone === contact);
  if (user) {
    return res.json({
      message: genericSendCodeMessage,
      maskedContact: maskContact(contact),
    });
  }

  const code = Math.floor(100000 + Math.random() * 900000).toString();
  const expiresAt = Date.now() + VERIFY_CODE_EXPIRES_MS;
  verificationCodes[contact] = { code, expiresAt };

  const sendResult = isEmail
    ? await sendEmailCode(contact, code, 'register')
    : await sendSmsCode(contact, code);

  if (!sendResult.ok) {
    delete verificationCodes[contact];
    return res.status(500).json({ error: 'Verification service temporarily unavailable' });
  }

  markSendCodeSuccess(contact);
  res.json({
    message: genericSendCodeMessage,
    maskedContact: maskContact(contact),
    devCode: sendResult.devCode,
  });
});

// ------------------------------------------------------------
// 🤖 Vercel AI SDK: Global AI Assistant Route
// ------------------------------------------------------------
const google = createGoogleGenerativeAI({
  apiKey: process.env.GEMINI_API_KEY,
});

app.get('/api/chat/health', (req, res) => {
  res.json({
    ok: true,
    model: AI_CHAT_MODEL,
    keyConfigured: Boolean(normalizeStr(process.env.GEMINI_API_KEY)),
    now: new Date().toISOString(),
  });
});

app.post('/api/chat', async (req, res) => {
  try {
    const messages = toSafeChatMessages(req.body?.messages);
    const platformContext = toSafePlatformContext(req.body?.platformContext);

    if (messages.length === 0) {
      return res.status(400).json({ error: 'messages is required.' });
    }

    if (!process.env.GEMINI_API_KEY) {
      streamFallbackData(res, '当前未配置模型密钥，已切换为平台助手兜底模式。请联系管理员配置 GEMINI_API_KEY。', 'fallback_no_key');
      return;
    }

    const abortController = new AbortController();
    const onClientAbort = () => {
      abortController.abort();
    };
    const onResponseClose = () => {
      if (!res.writableEnded) {
        abortController.abort();
      }
    };
    req.on('aborted', onClientAbort);
    res.on('close', onResponseClose);

    // Send response in Vercel AI legacy DataStream Protocol expected by @ai-sdk/react@3.
    // Keepalive frames prevent dev proxy idle timeouts on long generations.
    initDataStreamResponse(res, 'model');
    const stopKeepAlive = startDataStreamKeepAlive(res);

    let result;
    let hasAssistantOutput = false;
    const systemPrompt = platformContext
      ? `${CHAT_SYSTEM_PROMPT}\n\n[最新平台数据]\n${platformContext}`
      : CHAT_SYSTEM_PROMPT;

    try {
      result = streamText({
        model: google(AI_CHAT_MODEL),
        temperature: AI_CHAT_TEMPERATURE,
        messages,
        abortSignal: abortController.signal,
        system: systemPrompt,
        maxTokens: AI_CHAT_MAX_OUTPUT_TOKENS,
      });
    } catch (invokeError) {
      console.error('AI Invoke Error:', invokeError);
      writeDataStreamChunk(res, '模型调用失败，已切换为兜底回复。');
      for (const ch of Array.from(CHAT_FALLBACK_TEXT)) {
        writeDataStreamChunk(res, ch);
      }
      hasAssistantOutput = true;
      stopKeepAlive();
      endDataStream(res);
      req.removeListener('aborted', onClientAbort);
      res.removeListener('close', onResponseClose);
      return;
    }

    try {
      for await (const chunk of result.textStream) {
        const safeChunk = sanitizeAssistantChunk(chunk);
        if (safeChunk && !res.writableEnded) {
          hasAssistantOutput = true;
          for (const ch of Array.from(safeChunk)) {
            writeDataStreamChunk(res, ch);
          }
        }
      }
    } catch (streamError) {
      if (!abortController.signal.aborted) {
        console.error('AI Stream Error:', streamError);
        writeDataStreamChunk(res, '模型流式输出异常，已切换为兜底回复。');
        for (const ch of Array.from(CHAT_FALLBACK_TEXT)) {
          writeDataStreamChunk(res, ch);
        }
        hasAssistantOutput = true;
      }
    } finally {
      req.removeListener('aborted', onClientAbort);
      res.removeListener('close', onResponseClose);
      stopKeepAlive();
      if (!abortController.signal.aborted && !hasAssistantOutput) {
        writeDataStreamChunk(res, '模型未返回有效文本，已切换为兜底回复。');
        for (const ch of Array.from(CHAT_FALLBACK_TEXT)) {
          writeDataStreamChunk(res, ch);
        }
      }
      endDataStream(res);
    }
  } catch (error) {
    console.error('AI SDK Chat Error:', error);
    streamFallbackData(res, CHAT_FALLBACK_TEXT, 'fallback_error');
  }
});

app.use((err, req, res, next) => {
  console.error('Unhandled JSON/body parser error:', err);
  res.status(400).json({ error: 'Invalid JSON payload' });
});

app.listen(PORT, () => {
  console.log(`Auth server running on http://localhost:${PORT}`);
});
