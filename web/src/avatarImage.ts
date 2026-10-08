// Turns a photo the user picked into the small data URL stored in
// `profiles.avatar`. Everything happens in the browser: the file never leaves
// the device, only the 128px square does.

/** What the data URL is squeezed under. The column's own check allows 30000. */
export const AVATAR_MAX_CHARS = 20000;

const SIZE = 128;
const MAX_FILE_BYTES = 10 * 1024 * 1024;
// Tried in order until the result fits; a 128px square rarely needs the second.
const QUALITIES = [0.82, 0.6, 0.4];

interface Decoded {
  source: CanvasImageSource;
  width: number;
  height: number;
  release: () => void;
}

async function decode(file: File): Promise<Decoded> {
  try {
    // "from-image" applies the EXIF rotation, so a phone photo is not sideways.
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    return { source: bitmap, width: bitmap.width, height: bitmap.height, release: () => bitmap.close() };
  } catch {
    // No createImageBitmap, or no options for it (older Safari): an <img>
    // draws with the file's orientation by default.
  }
  const url = URL.createObjectURL(file);
  const image = new Image();
  try {
    image.src = url;
    await image.decode();
  } catch {
    URL.revokeObjectURL(url);
    throw new Error("No se pudo leer esa imagen.");
  }
  return {
    source: image,
    width: image.naturalWidth,
    height: image.naturalHeight,
    release: () => URL.revokeObjectURL(url),
  };
}

function encode(canvas: HTMLCanvasElement, quality: number): string {
  const webp = canvas.toDataURL("image/webp", quality);
  // A browser without a WebP encoder answers a PNG, which is far too big.
  return webp.startsWith("data:image/webp") ? webp : canvas.toDataURL("image/jpeg", quality);
}

/** Centre-crops `file` to a square, shrinks it, and returns it as a data URL of at most `AVATAR_MAX_CHARS`. */
export async function fileToAvatar(file: File): Promise<string> {
  if (!file.type.startsWith("image/")) throw new Error("Elige un archivo de imagen.");
  if (file.size > MAX_FILE_BYTES) throw new Error("La imagen pesa demasiado. Prueba con una de menos de 10 MB.");

  const image = await decode(file);
  try {
    if (image.width === 0 || image.height === 0) throw new Error("No se pudo leer esa imagen.");
    const canvas = document.createElement("canvas");
    canvas.width = SIZE;
    canvas.height = SIZE;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("No se pudo procesar la foto en este navegador.");

    // Flatten transparency onto white: JPEG has none and would turn it black.
    context.fillStyle = "#fff";
    context.fillRect(0, 0, SIZE, SIZE);
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";
    const side = Math.min(image.width, image.height);
    context.drawImage(
      image.source,
      (image.width - side) / 2,
      (image.height - side) / 2,
      side,
      side,
      0,
      0,
      SIZE,
      SIZE,
    );

    for (const quality of QUALITIES) {
      const url = encode(canvas, quality);
      if (url.length <= AVATAR_MAX_CHARS) return url;
    }
    throw new Error("No se pudo reducir la foto lo bastante. Prueba con otra.");
  } finally {
    image.release();
  }
}
