
const express = require('express');
const cookieParser = require('cookie-parser');
const jwt = require('jsonwebtoken');
const cors = require('cors');
const bodyParser = require('body-parser');

const app = express();
const PORT = 3001;
const SECRET_KEY = 'your-secret-key-change-in-production';

// Middleware
app.use(cors({
  origin: ['http://localhost:3000', 'http://localhost:3002', 'http://localhost:5173'], // Allow multiple frontend ports
  credentials: true
}));
app.use(bodyParser.json());
app.use(cookieParser());

// In-memory user store (replace with DB in production)
const users = [];

// Helper to find user
const findUser = (account) => {
  return users.find(u => u.email === account || u.phone === account || u.name === account);
};

// Routes

// Register
app.post('/api/register', (req, res) => {
  console.log('Register request body:', req.body);
  const { name, email, phone, password } = req.body;
  
  if (!name || !email || !phone || !password) {
    return res.status(400).json({ error: 'Missing required fields', received: req.body });
  }

  // Check if user already exists
  const existingUser = users.find(u => u.email === email || u.phone === phone || u.name === name);
  if (existingUser) {
    return res.status(409).json({ error: 'User already exists' });
  }

  const newUser = {
    id: Date.now().toString(),
    name,
    email,
    phone,
    password // In production, hash this password!
  };

  users.push(newUser);

  // Generate Token
  const token = jwt.sign({ id: newUser.id, name: newUser.name, email: newUser.email }, SECRET_KEY, { expiresIn: '7d' });

  // Set HttpOnly Cookie
  res.cookie('token', token, {
    httpOnly: true,
    secure: false, // Set to true in production with HTTPS
    sameSite: 'lax',
    maxAge: 7 * 24 * 60 * 60 * 1000 // 7 days
  });

  res.status(201).json({ 
    user: { name: newUser.name, email: newUser.email }
  });
});

// Login
app.post('/api/login', (req, res) => {
  const { account, password } = req.body;
  
  const user = findUser(account);
  
  if (!user || user.password !== password) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }

  // Generate Token
  const token = jwt.sign({ id: user.id, name: user.name, email: user.email }, SECRET_KEY, { expiresIn: '7d' });

  // Set HttpOnly Cookie
  res.cookie('token', token, {
    httpOnly: true,
    secure: false, // Set to true in production with HTTPS
    sameSite: 'lax',
    maxAge: 7 * 24 * 60 * 60 * 1000 // 7 days
  });

  res.json({ 
    user: { name: user.name, email: user.email }
  });
});

// Logout
app.post('/api/logout', (req, res) => {
  res.clearCookie('token');
  res.json({ message: 'Logged out successfully' });
});

// Get Current User (Me)
app.get('/api/me', (req, res) => {
  const token = req.cookies.token;
  
  if (!token) {
    return res.status(401).json({ error: 'Not authenticated' });
  }

  jwt.verify(token, SECRET_KEY, (err, decoded) => {
    if (err) {
      return res.status(403).json({ error: 'Invalid token' });
    }
    
    // Return user info (could fetch fresh from DB here)
    res.json({ 
      user: { name: decoded.name, email: decoded.email }
    });
  });
});

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
