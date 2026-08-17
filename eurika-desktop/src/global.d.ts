type EurikaDesktopApi = {
  startupWorkspace?: string;
  initialize(workspace?: string): Promise<Record<string, unknown>>;
  request<T = unknown>(
    method: string,
    params?: Record<string, unknown>,
    requestId?: string,
  ): Promise<T>;
  cancel(requestId?: string): Promise<{ cancelled: boolean }>;
  onEvent(listener: (event: unknown) => void): () => void;
  onStatus(listener: (status: string) => void): () => void;
  onLog(listener: (line: string) => void): () => void;
};

declare global {
  interface Window {
    eurika: EurikaDesktopApi;
  }
}

export {};
