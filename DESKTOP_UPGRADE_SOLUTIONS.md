# Windows 桌面版升级优化 - 完整解决方案

## 📋 问题现状分析

### 当前情况
- **问题**：每次版本更新都需要用户手动卸载旧版本再安装新版本
- **痛点**：
  - 用户体验差
  - 容易丢失用户配置和数据
  - 安装过程中可能遇到权限问题
  - 无法自动检查和提示更新

### 根本原因
NSIS 安装程序的默认行为是**全量覆盖安装**，而不是**增量更新**：
```nsi
; 当前方式 - 全量覆盖
Section "QwenPaw Desktop"
  SetOutPath "$INSTDIR"
  File /r "${UNPACKED}\*.*"    ; 覆盖所有文件
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd
```

---

## 🎯 三套解决方案对比

### 方案一：改进 NSIS 安装程序（推荐新手快速方案）

**优点**：
- ✅ 无需额外依赖
- ✅ 改动最小
- ✅ 易于实施
- ✅ 可以保留用户配置

**缺点**：
- ❌ 需要手动检查和下载更新
- ❌ 还是需要卸载旧版本
- ❌ 用户体验仍不够好

**实施步骤**：

1. **改进 NSIS 脚本**（desktop.nsi）
```nsi
; 检查旧版本安装路径
!include "x64.nsh"

Function .onInit
  ReadRegStr $InstallPath HKCU "Software\QwenPaw" "InstallPath"
  ${If} $InstallPath != ""
    ; 自动检测旧版本并警告
    MessageBox MB_YESNO "检测到旧版本已安装。建议卸载旧版本。现在卸载吗？" IDYES uninstall IDNO skip_uninstall
    uninstall:
      ExecWait '$INSTDIR\Uninstall.exe'
    skip_uninstall:
  ${EndIf}
FunctionEnd

; 安装前备份配置
Section "Backup Config"
  ${If} $InstallPath != ""
    CreateDirectory "$TEMP\QwenPaw_Backup"
    SetOverwrite off
    File /oname=$TEMP\QwenPaw_Backup\config.json "$INSTDIR\config.json"
  ${EndIf}
SectionEnd

; 安装时保留用户配置
Section "QwenPaw Desktop"
  SetOutPath "$INSTDIR"
  SetOverwrite on
  File /r "${UNPACKED}\*.*"

  ; 恢复备份的配置
  ${If} ${FileExists} "$TEMP\QwenPaw_Backup\config.json"
    CopyFiles "$TEMP\QwenPaw_Backup\config.json" "$INSTDIR\config.json"
  ${EndIf}
SectionEnd
```

2. **更新安装脚本**（build_win.ps1）
```powershell
# 检查版本兼容性
function Check-VersionCompatibility {
  param([string]$NewVersion, [string]$OldVersion)

  # 解析版本号
  $new = $NewVersion -split "\."
  $old = $OldVersion -split "\."

  # 比较主版本号
  if ([int]$new[0] -eq [int]$old[0]) {
    return $true  # 兼容
  }
  return $false   # 不兼容
}
```

---

### 方案二：集成自动更新框架（推荐生产环境）

**优点**：
- ✅ 完全自动化更新
- ✅ 专业解决方案
- ✅ 增量下载（节省带宽）
- ✅ 安全验证机制
- ✅ 用户体验最佳

**缺点**：
- ⚠️ 需要第三方库
- ⚠️ 需要更新服务器
- ⚠️ 实施复杂度高

**建议使用：Electron Update 或 WinSparkle**

#### 方案 2A：集成 electron-updater（如果用 Electron）

适用于已有 Electron 前端的情况。

```javascript
// 前端：console/src/services/updateService.ts
import { ipcRenderer } from 'electron';

export class UpdateService {
  async checkForUpdates() {
    return new Promise((resolve) => {
      ipcRenderer.on('update-available', (event, info) => {
        console.log('New version available:', info.version);
        resolve(info);
      });

      ipcRenderer.send('check-for-updates');
    });
  }

  async downloadAndInstall() {
    ipcRenderer.send('download-and-install');
  }
}
```

```javascript
// 主进程：main-process.js
import { autoUpdater } from 'electron-updater';

autoUpdater.checkForUpdates();

autoUpdater.on('update-available', (info) => {
  mainWindow.webContents.send('update-available', info);

  // 自动下载
  autoUpdater.downloadUpdate();
});

autoUpdater.on('update-downloaded', () => {
  mainWindow.webContents.send('update-ready');
  autoUpdater.quitAndInstall();
});
```

#### 方案 2B：集成 WinSparkle（推荐 - 更简单）

这是 Windows 原生应用最流行的自动更新方案。

**实施步骤**：

1. **新增 C# 更新检查服务**（backend）

```csharp
// src/qwenpaw/services/update_service.cs
using System;
using System.Net.Http;
using System.Threading.Tasks;

public class UpdateService {
    private const string UPDATE_ENDPOINT = "https://api.qwenpaw.com/updates";
    private readonly string _currentVersion;

    public UpdateService(string currentVersion) {
        _currentVersion = currentVersion;
    }

    public async Task<UpdateInfo> CheckForUpdates() {
        using (var client = new HttpClient()) {
            var url = $"{UPDATE_ENDPOINT}/check?version={_currentVersion}";
            var response = await client.GetAsync(url);

            if (response.IsSuccessStatusCode) {
                var json = await response.Content.ReadAsStringAsync();
                return JsonConvert.DeserializeObject<UpdateInfo>(json);
            }
            return null;
        }
    }

    public async Task<bool> DownloadAndInstall(UpdateInfo info) {
        using (var client = new HttpClient()) {
            var data = await client.GetByteArrayAsync(info.DownloadUrl);

            // 验证签名
            if (!VerifySignature(data, info.Signature)) {
                throw new Exception("Update signature verification failed");
            }

            // 保存到临时目录
            var tempPath = Path.Combine(Path.GetTempPath(), "QwenPaw-Update.exe");
            File.WriteAllBytes(tempPath, data);

            // 运行安装程序
            Process.Start(tempPath);
            return true;
        }
    }

    private bool VerifySignature(byte[] data, string signature) {
        // 使用 RSA 公钥验证签名
        // ...
        return true;
    }
}
```

2. **新增 API 端点**（检查更新）

```python
# src/qwenpaw/app/_app.py
@app.get("/api/updates/check")
async def check_updates(current_version: str):
    """检查是否有新版本可用"""
    from packaging import version

    latest = await get_latest_version()  # 从服务器获取

    if version.parse(latest) > version.parse(current_version):
        return {
            "available": True,
            "latest_version": latest,
            "download_url": f"https://releases.qwenpaw.com/QwenPaw-Setup-{latest}.exe",
            "changelog": await get_changelog(latest),
            "is_critical": check_if_critical(current_version, latest),
        }

    return {"available": False}

@app.get("/api/updates/downloads/{version}")
async def get_download_url(version: str):
    """获取特定版本的下载链接"""
    return {
        "url": f"https://releases.qwenpaw.com/QwenPaw-Setup-{version}.exe",
        "size": get_file_size(version),
        "checksum": get_file_checksum(version),
    }
```

3. **改进启动流程**

```python
# src/qwenpaw/app/_app.py - lifespan 函数
async def lifespan(app: FastAPI):
    # 启动时检查更新
    async def check_updates_background():
        try:
            update_info = await check_for_updates()
            if update_info["available"]:
                logger.info(f"New version available: {update_info['latest_version']}")
                # 通知前端
                await notify_frontend_update(update_info)
        except Exception as e:
            logger.debug(f"Update check failed: {e}")

    # 后台启动任务中添加更新检查
    async def startup():
        # 现有启动代码...
        # 在所有初始化后检查更新
        asyncio.create_task(check_updates_background())

    yield
```

4. **前端更新通知**

```typescript
// console/src/services/updateChecker.ts
import { useEffect, useState } from 'react';

export function useUpdateChecker() {
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [updateInfo, setUpdateInfo] = useState(null);

  useEffect(() => {
    const checkUpdates = async () => {
      try {
        const response = await fetch('/api/updates/check?current_version=1.1.9');
        const data = await response.json();

        if (data.available) {
          setUpdateAvailable(true);
          setUpdateInfo(data);
        }
      } catch (error) {
        console.error('Failed to check updates:', error);
      }
    };

    checkUpdates();
    // 每小时检查一次
    const interval = setInterval(checkUpdates, 3600000);
    return () => clearInterval(interval);
  }, []);

  const downloadAndInstall = async () => {
    // 调用后端 API 下载并安装
    await fetch('/api/updates/download', {
      method: 'POST',
      body: JSON.stringify({ version: updateInfo.latest_version }),
    });
  };

  return { updateAvailable, updateInfo, downloadAndInstall };
}
```

5. **新增更新服务器端点**

```python
# 服务器端 - 维护最新版本信息

# storage/releases.json
{
  "latest": "1.2.0",
  "versions": {
    "1.2.0": {
      "url": "https://cdn.qwenpaw.com/QwenPaw-Setup-1.2.0.exe",
      "size": 450000000,
      "checksum": "abc123...",
      "changelog": "...",
      "critical": false
    },
    "1.1.9": {
      "url": "https://cdn.qwenpaw.com/QwenPaw-Setup-1.1.9.exe",
      "size": 445000000,
      "checksum": "def456...",
      "critical": false
    }
  }
}
```

---

### 方案三：Delta Update（增量更新 - 高级方案）

**优点**：
- ✅ 最小化下载大小
- ✅ 最快的更新速度
- ✅ 最好的用户体验

**缺点**：
- ❌ 实施最复杂
- ❌ 需要维护增量包
- ❌ 需要二进制差分工具

**技术栈**：
- **工具**：BSDiff / xdelta / courgette
- **方案**：生成增量包而不是完整包

**实施框架**：

```powershell
# scripts/pack/build_delta_update.ps1

# 1. 获取上一个版本
$PreviousVersion = "1.1.9"
$CurrentVersion = "1.2.0"

# 2. 下载旧版本可执行文件
$OldExe = "QwenPaw-Setup-${PreviousVersion}.exe"
$NewExe = "QwenPaw-Setup-${CurrentVersion}.exe"

# 3. 使用 xdelta 生成增量包
# xdelta3 -e -9 -S djw -s $OldExe $NewExe delta.patch

# 4. 生成元数据
@{
  from_version = $PreviousVersion
  to_version = $CurrentVersion
  patch_file = "delta.patch"
  patch_size = (Get-Item "delta.patch").Length
  signature = (Get-FileHash "delta.patch").Hash
} | ConvertTo-Json | Out-File "delta.json"
```

```csharp
// 客户端应用 delta 补丁
public class DeltaUpdater {
    public static void ApplyDelta(string oldFile, string deltaFile, string newFile) {
        // 使用 xdelta 库应用补丁
        // xdelta3 -d -s $OldExe delta.patch $NewExe

        Process.Start(new ProcessStartInfo {
            FileName = "xdelta3.exe",
            Arguments = $"-d -s \"{oldFile}\" \"{deltaFile}\" \"{newFile}\"",
            UseShellExecute = false
        }).WaitForExit();
    }
}
```

---

## 📊 方案对比表

| 特性 | 方案一 | 方案二 | 方案三 |
|-----|------|------|------|
| **实施难度** | ⭐ 简单 | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐ 复杂 |
| **用户体验** | ⭐⭐ 一般 | ⭐⭐⭐⭐⭐ 最佳 | ⭐⭐⭐⭐⭐ 最佳 |
| **实施成本** | 低 | 中 | 高 |
| **维护成本** | 低 | 中 | 高 |
| **更新速度** | 一般 | 快 | 非常快 |
| **带宽消耗** | 最高 | 中等 | 最低 |
| **用户参与** | 手动 | 自动 | 自动 |
| **是否推荐** | ✅ 快速方案 | ✅ 推荐生产 | ⭐ 未来优化 |

---

## 🚀 快速实施路线图

### 阶段 1 - 即刻实施（推荐方案一 + 二混合）

**Week 1**：改进 NSIS 脚本
- 添加自动检测旧版本
- 保留用户配置功能
- 改进安装流程提示

**Week 2-3**：实施基础更新检查
- 添加 `/api/updates/check` 端点
- 前端显示更新提示
- 手动下载链接

**输出**：用户可以看到更新提示，手动下载

### 阶段 2 - 中期优化（完整方案二）

**Month 2**：完整自动更新框架
- 自动下载更新
- 后台静默安装
- 更新日志展示

**输出**：完全自动更新，用户无需手动操作

### 阶段 3 - 长期优化（方案三）

**Month 3+**：增量更新
- 生成增量补丁
- 最小化下载
- 优化用户体验

---

## 📝 立即可做的工作

### 1. 改进版本 API（5 分钟）

```python
# src/qwenpaw/app/_app.py
@app.get("/api/version")
def get_version():
    """返回当前版本及更新信息"""
    return {
        "version": __version__,
        "is_latest": await check_if_latest(),  # 新增
        "latest_available": await get_latest_version(),  # 新增
        "update_url": f"https://releases.qwenpaw.com/check-updates",  # 新增
    }
```

### 2. 改进 NSIS 脚本（10 分钟）

```nsi
; 在 desktop.nsi 顶部添加
!include "MUI2.nsh"
!include "FileFunc.nsh"

; 检查旧版本
Function .onInit
  ReadRegStr $INSTDIR HKCU "Software\QwenPaw" "InstallPath"
  ${If} $INSTDIR != ""
    MessageBox MB_YESNO "检测到旧版本。建议先卸载。继续吗？" IDYES + 2
    Abort
  ${EndIf}
FunctionEnd
```

### 3. 创建更新检查脚本（15 分钟）

```python
# scripts/check_updates.py
import requests
from packaging import version

RELEASES_URL = "https://api.github.com/repos/YourOrg/QwenPaw/releases/latest"

def check_for_updates(current_version):
    response = requests.get(RELEASES_URL)
    latest = response.json()["tag_name"]

    if version.parse(latest) > version.parse(current_version):
        return {
            "available": True,
            "version": latest,
            "url": response.json()["html_url"],
        }
    return {"available": False}
```

---

## ✅ 建议方案（立即开始）

**推荐：方案一（改进 NSIS） + 方案二（基础自动更新）**

**理由**：
- ✅ 投入产出比最高
- ✅ 用户体验显著提升
- ✅ 实施周期短
- ✅ 可逐步完善
- ✅ 风险最低

**优先级**：
1. **优先-立即做**：改进 NSIS 脚本
2. **次优先**：添加更新检查 API
3. **后续**：实施自动下载安装

---

## 📚 相关资源

| 工具 | 用途 | 链接 |
|-----|------|------|
| WinSparkle | Windows 自动更新 | https://winsparkle.org/ |
| electron-updater | Electron 更新 | https://www.electron.build/auto-update |
| xdelta | 增量更新 | http://xdelta.org/ |
| BSDiff | 二进制补丁 | http://www.daemonology.net/bsdiff/ |

