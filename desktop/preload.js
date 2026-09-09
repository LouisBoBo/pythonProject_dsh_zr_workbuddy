/**
 * 向渲染进程暴露一体包能力。不暴露 Node API。
 * 选目录走主进程 dialog，避免引擎 osascript 调 Finder 被系统拦（-1743）。
 */
'use strict'

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('workbuddyDesktop', {
  pickFolder: (prompt) => ipcRenderer.invoke('workbuddy:pick-folder', prompt || '选择工程目录'),
})
