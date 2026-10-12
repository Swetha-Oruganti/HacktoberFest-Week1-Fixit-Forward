import mongoose from 'mongoose';
const uploadedImageSchema = new mongoose.Schema({ owner: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true, index: true }, filename: { type: String, required: true, unique: true }, linked: { type: Boolean, default: false } }, { timestamps: true });
export default mongoose.model('UploadedImage', uploadedImageSchema);
