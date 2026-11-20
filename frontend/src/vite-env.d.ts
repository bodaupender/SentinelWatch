/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string | undefined
  readonly VITE_APP_NAME: string | undefined
  readonly VITE_APP_VERSION: string | undefined
  readonly VITE_ENABLE_WEBSOCKET: string | undefined
  readonly VITE_ENABLE_AI_INVESTIGATION: string | undefined
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
