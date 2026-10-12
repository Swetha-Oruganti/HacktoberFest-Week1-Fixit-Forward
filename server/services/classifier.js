import { pipeline, env } from '@huggingface/transformers';

env.allowRemoteModels = true;
let classifier;
const labels = ['an overflowing garbage bin with litter on the street', 'a broken streetlight or lamp post', 'a cracked or damaged sidewalk pavement', 'an unmaintained neglected public park or space', 'a pothole or damaged road', 'another public infrastructure problem'];

export async function classifyImage(imagePath) {
  if (process.env.AI_MODE !== 'local') return { label: '', score: 0, mode: 'manual' };
  try {
    classifier ??= await pipeline('zero-shot-image-classification', process.env.CLIP_MODEL || 'Xenova/clip-vit-base-patch32');
    const results = await classifier(imagePath, labels);
    return { label: results[0]?.label ?? '', score: results[0]?.score ?? 0, mode: 'open-model' };
  } catch (error) {
    console.error('Local image classification unavailable:', error.message);
    return { label: '', score: 0, mode: 'unavailable' };
  }
}
