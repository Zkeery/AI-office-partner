// Reserved for future desktop bridge APIs. Keep contextIsolation on.
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("officeDesktop", {
  isDesktop: true,
});
