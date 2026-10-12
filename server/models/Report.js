import mongoose from 'mongoose';

const eventSchema = new mongoose.Schema({ status: String, note: String, at: { type: Date, default: Date.now } }, { _id: false });
const reportSchema = new mongoose.Schema({
  owner: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true, index: true },
  category: { type: String, required: true, enum: ['Overflowing waste', 'Broken streetlight', 'Damaged pavement', 'Neglected public space', 'Other'] },
  title: { type: String, required: true, trim: true, maxlength: 120 },
  description: { type: String, required: true, trim: true, maxlength: 1500 },
  severity: { type: String, enum: ['Low', 'Medium', 'High'], default: 'Medium' },
  address: { type: String, trim: true, maxlength: 200, default: '' },
  coordinates: { latitude: Number, longitude: Number },
  imagePath: { type: String, default: '' },
  status: { type: String, enum: ['Draft', 'Ready to submit', 'Submitted by me', 'Acknowledged', 'Resolved'], default: 'Ready to submit' },
  aiLabel: { type: String, default: '' },
  events: { type: [eventSchema], default: [] }
}, { timestamps: true });

export default mongoose.model('Report', reportSchema);
