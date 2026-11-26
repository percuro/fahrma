/**
 * Receipt photos: shrunk on the device before sending (a phone photo has several MB, a readable
 * receipt needs a few hundred KB). Re-encoding also drops the photo's metadata, such as where it
 * was taken.
 */
import { apiRequest, apiUrl } from './api';
import type { Receipt } from './types';

/** Longest side after shrinking; enough to read small print on a receipt. */
export const MAX_SIDE = 1600;
export const JPEG_QUALITY = 0.8;
/** Like the server (MAX_RECEIPTS_PER_ENTRY). */
export const MAX_RECEIPTS_PER_ENTRY = 5;

export type ReceiptKind = 'fuel' | 'expense';

const COLLECTION: Record<ReceiptKind, string> = { fuel: 'fuel', expense: 'expenses' };

/** Width and height that fit within ``max`` on the longer side, keeping the proportions; never larger. */
export function fitWithin(width: number, height: number, max = MAX_SIDE): { width: number; height: number } {
  const scale = Math.min(1, max / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

async function decode(file: Blob): Promise<{ source: CanvasImageSource; width: number; height: number; close: () => void }> {
  if (typeof createImageBitmap === 'function') {
    try {
      // The photo's orientation (EXIF) is applied, so portrait shots stay upright
      const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
      return { source: bitmap, width: bitmap.width, height: bitmap.height, close: () => bitmap.close() };
    } catch {
      // Older Safari: fall back to an <img>, which also applies the orientation
    }
  }
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    return { source: image, width: image.naturalWidth, height: image.naturalHeight, close: () => undefined };
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** A JPEG of at most MAX_SIDE pixels on the longer side. */
export async function shrinkImage(file: Blob): Promise<Blob> {
  const image = await decode(file);
  try {
    const size = fitWithin(image.width, image.height);
    const canvas = document.createElement('canvas');
    canvas.width = size.width;
    canvas.height = size.height;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('no canvas');
    // Transparent areas (screenshots) become white instead of black
    context.fillStyle = '#fff';
    context.fillRect(0, 0, size.width, size.height);
    context.drawImage(image.source, 0, 0, size.width, size.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY));
    if (!blob) throw new Error('could not encode');
    return blob;
  } finally {
    image.close();
  }
}

export function receiptUrl(groupId: number, receiptId: number): string {
  return apiUrl(`/v1/groups/${groupId}/receipts/${receiptId}`);
}

export function receiptsZipUrl(groupId: number): string {
  return apiUrl(`/v1/groups/${groupId}/receipts.zip`);
}

export async function uploadReceipt(
  groupId: number,
  kind: ReceiptKind,
  entryId: number,
  photo: Blob,
  key: string,
  signal?: AbortSignal,
): Promise<Receipt> {
  const { data } = await apiRequest<Receipt>(`/v1/groups/${groupId}/${COLLECTION[kind]}/${entryId}/receipts`, {
    method: 'POST',
    body: photo,
    headers: { 'Content-Type': photo.type || 'image/jpeg', 'Idempotency-Key': key },
    signal,
  });
  return data;
}

export async function deleteReceipt(groupId: number, receiptId: number): Promise<void> {
  await apiRequest<void>(`/v1/groups/${groupId}/receipts/${receiptId}`, { method: 'DELETE' });
}

