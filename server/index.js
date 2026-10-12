import 'dotenv/config';
import express from 'express';
import mongoose from 'mongoose';
import cookieParser from 'cookie-parser';
import cors from 'cors';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import api from './routes/api.js';

const app = express();
const root = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 5000);
app.use(helmet({ crossOriginResourcePolicy: { policy: 'cross-origin' }, contentSecurityPolicy: false }));
app.use(cors({ origin: process.env.CLIENT_ORIGIN || 'http://localhost:5173', credentials: true }));
app.use(express.json({ limit: '32kb' })); app.use(cookieParser());
app.use('/api', rateLimit({ windowMs: 15 * 60 * 1000, limit: 180, standardHeaders: true, legacyHeaders: false }));
app.use('/api', api);
const uploadDir = path.resolve('uploads');
app.get('/api/uploads/:filename', async (req, res, next) => {
  const { requireAuth } = await import('./middleware/auth.js');
  requireAuth(req, res, async () => {
    try {
      const { default: UploadedImage } = await import('./models/UploadedImage.js');
      const image = await UploadedImage.findOne({ owner: req.userId, filename: req.params.filename, linked: true });
      if (!image) return res.sendStatus(404);
      res.sendFile(path.join(uploadDir, image.filename), (err) => { if (err) next(err); });
    } catch (err) { next(err); }
  });
});
app.use((err, _req, res, _next) => {
  if (err?.name === 'ZodError') return res.status(400).json({ error: err.issues[0]?.message || 'Please check the submitted details.' });
  if (err?.code === 11000) return res.status(409).json({ error: 'That email address is already registered.' });
  if (err?.name === 'MulterError' || err?.message?.includes('File type')) return res.status(400).json({ error: 'Upload a JPG, PNG, or WebP image under 8 MB.' });
  console.error(err); res.status(500).json({ error: 'Something went wrong. Please try again.' });
});

await mongoose.connect(process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/fixit-forward');
console.log('Connected to MongoDB');
if (process.env.NODE_ENV === 'production') app.use(express.static(path.resolve(root, '../dist')));
app.listen(port, () => console.log(`Fixit Forward API listening on http://localhost:${port}`));
