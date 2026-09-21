/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `"local"` talks to the FastAPI dev server; anything else (default) uses Supabase. */
  readonly VITE_BACKEND?: "local" | "supabase";
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_ANON_KEY?: string;
  /** base64 (standard alphabet) sealed-box public key — see `seal.ts`. */
  readonly VITE_SEAL_PUBLIC_KEY?: string;
  readonly VITE_SEAL_KEY_ID?: string;
  /** Pages deploy path, e.g. `/upv-auto/` (Phase 5: `vite.config.ts`'s `base`). */
  readonly VITE_BASE_PATH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
