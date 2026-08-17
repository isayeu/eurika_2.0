import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("eurika", {
  startupWorkspace: process.env.EURIKA_WORKSPACE,
  initialize: (workspace?: string) => ipcRenderer.invoke("eurika:initialize", workspace),
  request: (method: string, params?: Record<string, unknown>, requestId?: string) =>
    ipcRenderer.invoke("eurika:request", method, params, requestId),
  cancel: (requestId?: string) => ipcRenderer.invoke("eurika:cancel", requestId),
  onEvent: (listener: (event: unknown) => void) => {
    const wrapped = (_event: Electron.IpcRendererEvent, value: unknown) => listener(value);
    ipcRenderer.on("eurika:event", wrapped);
    return () => ipcRenderer.removeListener("eurika:event", wrapped);
  },
  onStatus: (listener: (status: string) => void) => {
    const wrapped = (_event: Electron.IpcRendererEvent, value: string) => listener(value);
    ipcRenderer.on("eurika:status", wrapped);
    return () => ipcRenderer.removeListener("eurika:status", wrapped);
  },
  onLog: (listener: (line: string) => void) => {
    const wrapped = (_event: Electron.IpcRendererEvent, value: string) => listener(value);
    ipcRenderer.on("eurika:log", wrapped);
    return () => ipcRenderer.removeListener("eurika:log", wrapped);
  },
});
