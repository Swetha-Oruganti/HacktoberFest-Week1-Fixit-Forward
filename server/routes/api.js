import { Router } from 'express';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import multer from 'multer';
import path from 'node:path';
import crypto from 'node:crypto';
import fs from 'node:fs';
import { fileTypeFromFile } from 'file-type';
import { z } from 'zod';
import User from '../models/User.js';
import Report from '../models/Report.js';
import UploadedImage from '../models/UploadedImage.js';
import { requireAuth } from '../middleware/auth.js';
import { classifyImage } from '../services/classifier.js';

const router = Router();
const maxBytes = Number(process.env.MAX_UPLOAD_MB || 8) * 1024 * 1024;
const uploadDir = path.resolve('uploads');
fs.mkdirSync(uploadDir, { recursive: true });
const upload = multer({
  storage: multer.diskStorage({ destination: uploadDir, filename: (_req, file, cb) => cb(null, `${crypto.randomUUID()}${path.extname(file.originalname).toLowerCase()}`) }),
  limits: { fileSize: maxBytes, files: 1 },
  fileFilter: (_req, file, cb) => cb(null, ['image/jpeg', 'image/png', 'image/webp'].includes(file.mimetype))
});
const authLimit = (req, res) => {
  const token = jwt.sign({}, process.env.JWT_SECRET, { subject: String(req._user._id), expiresIn: '7d' });
  res.cookie('session', token, { httpOnly: true, sameSite: 'lax', secure: process.env.NODE_ENV === 'production', maxAge: 7 * 86400000 });
  res.json({ user: { id: req._user._id, name: req._user.name, email: req._user.email } });
};
const userView = (user) => ({ id: user._id, name: user.name, email: user.email });

router.get('/health', (_req, res) => res.json({ ok: true, database: 'connected' }));
router.post('/auth/register', async (req, res, next) => {
  try {
    const data = z.object({ name: z.string().trim().min(2).max(80), email: z.string().email().max(200), password: z.string().min(8).max(100) }).parse(req.body);
    if (await User.exists({ email: data.email.toLowerCase() })) return res.status(409).json({ error: 'An account with this email already exists.' });
    const user = await User.create({ name: data.name, email: data.email.toLowerCase(), passwordHash: await bcrypt.hash(data.password, 12) });
    req._user = user; authLimit(req, res);
  } catch (e) { next(e); }
});
router.post('/auth/login', async (req, res, next) => {
  try {
    const data = z.object({ email: z.string().email(), password: z.string().min(1) }).parse(req.body);
    const user = await User.findOne({ email: data.email.toLowerCase() });
    if (!user || !(await bcrypt.compare(data.password, user.passwordHash))) return res.status(401).json({ error: 'Email or password is incorrect.' });
    req._user = user; authLimit(req, res);
  } catch (e) { next(e); }
});
router.post('/auth/logout', (_req, res) => { res.clearCookie('session'); res.json({ ok: true }); });
router.get('/auth/me', requireAuth, async (req, res, next) => { try { const user = await User.findById(req.userId); res.json({ user: userView(user) }); } catch (e) { next(e); } });

router.post('/classify', requireAuth, upload.single('photo'), async (req, res, next) => {
  if (!req.file) return res.status(400).json({ error: 'Upload a JPG, PNG, or WebP image under 8 MB.' });
  try {
    const detected = await fileTypeFromFile(req.file.path);
    if (!detected || !['image/jpeg', 'image/png', 'image/webp'].includes(detected.mime)) { fs.rm(req.file.path, { force: true }, () => {}); return res.status(400).json({ error: 'The uploaded file is not a valid JPG, PNG, or WebP image.' }); }
    const result = await classifyImage(req.file.path); await UploadedImage.create({ owner: req.userId, filename: req.file.filename }); res.json({ ...result, imagePath: `/api/uploads/${req.file.filename}` });
  }
  catch (e) { next(e); }
});
const reportInput = z.object({ category: z.enum(['Overflowing waste', 'Broken streetlight', 'Damaged pavement', 'Neglected public space', 'Other']), title: z.string().trim().min(5).max(120), description: z.string().trim().min(15).max(1500), severity: z.enum(['Low', 'Medium', 'High']), address: z.string().trim().max(200).optional().default(''), imagePath: z.string().startsWith('/api/uploads/').optional().default(''), aiLabel: z.string().max(200).optional().default(''), coordinates: z.object({ latitude: z.number(), longitude: z.number() }).optional() });
router.get('/reports', requireAuth, async (req, res, next) => { try { const reports = await Report.find({ owner: req.userId }).sort({ updatedAt: -1 }).lean(); res.json({ reports }); } catch (e) { next(e); } });
router.post('/reports', requireAuth, async (req, res, next) => { try { const data = reportInput.parse(req.body); if (data.imagePath && !await UploadedImage.exists({ owner: req.userId, filename: path.basename(data.imagePath) })) return res.status(400).json({ error: 'Please upload the photo again before saving.' }); const report = await Report.create({ ...data, owner: req.userId, status: 'Ready to submit', events: [{ status: 'Ready to submit', note: 'Report prepared. Submit it through your civic authority.' }] }); if (data.imagePath) await UploadedImage.updateOne({ owner: req.userId, filename: path.basename(data.imagePath) }, { linked: true }); res.status(201).json({ report }); } catch (e) { next(e); } });
router.patch('/reports/:id', requireAuth, async (req, res, next) => { try { const data = reportInput.partial().parse(req.body); if (data.imagePath && !await UploadedImage.exists({ owner: req.userId, filename: path.basename(data.imagePath) })) return res.status(400).json({ error: 'Please upload the photo again before saving.' }); const report = await Report.findOneAndUpdate({ _id: req.params.id, owner: req.userId }, data, { new: true, runValidators: true }); if (!report) return res.status(404).json({ error: 'Report not found.' }); if (data.imagePath) await UploadedImage.updateOne({ owner: req.userId, filename: path.basename(data.imagePath) }, { linked: true }); res.json({ report }); } catch (e) { next(e); } });
router.patch('/reports/:id/status', requireAuth, async (req, res, next) => {
  try {
    const { status, note = '' } = z.object({ status: z.enum(['Ready to submit', 'Submitted by me', 'Acknowledged', 'Resolved']), note: z.string().trim().max(300) }).parse(req.body);
    const report = await Report.findOne({ _id: req.params.id, owner: req.userId }); if (!report) return res.status(404).json({ error: 'Report not found.' });
    report.status = status; report.events.push({ status, note: note || (status === 'Submitted by me' ? 'You marked this report as submitted.' : `Status updated to ${status}.`) }); await report.save(); res.json({ report });
  } catch (e) { next(e); }
});
router.delete('/reports/:id', requireAuth, async (req, res, next) => { try { const report = await Report.findOneAndDelete({ _id: req.params.id, owner: req.userId }); if (!report) return res.status(404).json({ error: 'Report not found.' }); if (report.imagePath) { const filename = path.basename(report.imagePath); await UploadedImage.deleteOne({ owner: req.userId, filename }); fs.rm(path.join(uploadDir, filename), { force: true }, () => {}); } res.json({ ok: true }); } catch (e) { next(e); } });
export default router;
