import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("treningsanalyseDesktop", {
  getPaths: () => ipcRenderer.invoke("desktop:get-paths"),
  openLogFolder: () => ipcRenderer.invoke("desktop:open-log-folder"),
  importDatabase: (filePath: string) => ipcRenderer.invoke("desktop:import-database", filePath),
  getVersion: () => ipcRenderer.invoke("desktop:get-version"),
});
