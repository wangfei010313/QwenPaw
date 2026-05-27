# Windows 桌面版升级 - 快速实施指南

## 🎯 快速决策

**问题**：Windows 桌面版无法在线升级，必须卸载重装

**解决方案**：三个方案逐步实施（推荐混合方案）

```
立刻开始        2 周内            1-2 月
├─ 改进安装脚本  ├─ 更新检查API    ├─ 自动下载安装
├─ 保留配置      ├─ 前端通知UI     ├─ 后台更新
└─ 自动检测旧版  └─ 手动下载链接   └─ 无缝体验
```

---

## 📝 阶段一：改进安装脚本（第 1-2 天）

### Step 1：改进 desktop.nsi

**文件**：`scripts/pack/desktop.nsi`

**修改内容**：

```nsi
; 添加到文件顶部（在 !include 之后）
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON "${UNPACKED}\icon.ico"
!define MUI_UNICON "${UNPACKED}\icon.ico"

!ifndef QWENPAW_VERSION
  !define QWENPAW_VERSION "0.0.0"
!endif
!ifndef OUTPUT_EXE
  !define OUTPUT_EXE "dist\QwenPaw-Setup-${QWENPAW_VERSION}.exe"
!endif

Name "QwenPaw Desktop"
OutFile "${OUTPUT_EXE}"
InstallDir "$LOCALAPPDATA\QwenPaw"
InstallDirRegKey HKCU "Software\QwenPaw" "InstallPath"
RequestExecutionLevel user

; ===== 关键改进 1：检查并处理旧版本 =====
Function .onInit
  ; 检查是否已安装
  ReadRegStr $INSTDIR HKCU "Software\QwenPaw" "InstallPath"

  ${If} $INSTDIR != ""
    ; 旧版本已存在，检查版本号
    ReadRegStr $OldVersion HKCU "Software\QwenPaw" "Version"

    ; 显示升级对话框
    MessageBox MB_YESNO "检测到 QwenPaw 已安装 (版本 $OldVersion)。$\n$\n建议先卸载旧版本以确保升级成功。$\n$\n现在卸载旧版本吗？" IDYES uninstall_old IDNO skip_uninstall

    uninstall_old:
      ; 运行卸载程序
      ExecWait '$INSTDIR\Uninstall.exe /S'
      Sleep 1000

    skip_uninstall:
  ${EndIf}
FunctionEnd

; ===== 关键改进 2：安装前备份用户数据 =====
Section "Backup User Data" SEC00
  ; 备份存在的配置数据
  CreateDirectory "$TEMP\QwenPaw_Backup"

  ; 设置覆盖政策 - 不覆盖已有文件
  SetOverwrite off

  ; 如果旧版本存在，备份关键文件
  ${If} ${FileExists} "$INSTDIR"
    IfFileExists "$INSTDIR\config.json" 0 skip_config_backup
      CopyFiles "$INSTDIR\config.json" "$TEMP\QwenPaw_Backup\"
    skip_config_backup:

    IfFileExists "$INSTDIR\app_state.json" 0 skip_state_backup
      CopyFiles "$INSTDIR\app_state.json" "$TEMP\QwenPaw_Backup\"
    skip_state_backup:

    IfFileExists "$INSTDIR\plugin_config.json" 0 skip_plugin_backup
      CopyFiles "$INSTDIR\plugin_config.json" "$TEMP\QwenPaw_Backup\"
    skip_plugin_backup:
  ${EndIf}

  SectionEnd

; ===== 主安装部分 =====
Section "QwenPaw Desktop" SEC01
  SetOutPath "$INSTDIR"

  ; 设置覆盖政策 - 覆盖程序文件
  SetOverwrite on

  ; 安装所有程序文件
  File /r "${UNPACKED}\*.*"

  ; 写入注册表 - 包括版本号
  WriteRegStr HKCU "Software\Qwenpaw" "InstallPath" "$INSTDIR"
  WriteRegStr HKCU "Software\Qwenpaw" "Version" "${QWENPAW_VERSION}"
  WriteRegStr HKCU "Software\Qwenpaw" "InstallDate" "$\$CURRENT_DATE"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; 创建快捷方式
  CreateDirectory "$SMPROGRAMS"
  CreateShortcut "$SMPROGRAMS\QwenPaw Desktop.lnk" "$INSTDIR\QwenPaw Desktop.vbs" "" "$INSTDIR\icon.ico" 0
  CreateShortcut "$DESKTOP\QwenPaw Desktop.lnk" "$INSTDIR\QwenPaw Desktop.vbs" "" "$INSTDIR\icon.ico" 0
  CreateShortcut "$SMPROGRAMS\QwenPaw Desktop (Debug).lnk" "$INSTDIR\QwenPaw Desktop (Debug).bat" "" "$INSTDIR\icon.ico" 0
SectionEnd

; ===== 关键改进 3：恢复用户数据 =====
Section "Restore User Data" SEC02
  SetOverwrite off

  ; 恢复备份的配置文件
  ${If} ${FileExists} "$TEMP\QwenPaw_Backup\config.json"
    CopyFiles "$TEMP\QwenPaw_Backup\config.json" "$INSTDIR\"
    DetailPrint "已恢复用户配置"
  ${EndIf}

  ${If} ${FileExists} "$TEMP\QwenPaw_Backup\app_state.json"
    CopyFiles "$TEMP\QwenPaw_Backup\app_state.json" "$INSTDIR\"
    DetailPrint "已恢复应用状态"
  ${EndIf}

  ${If} ${FileExists} "$TEMP\QwenPaw_Backup\plugin_config.json"
    CopyFiles "$TEMP\QwenPaw_Backup\plugin_config.json" "$INSTDIR\"
    DetailPrint "已恢复插件配置"
  ${EndIf}

  ; 清理备份目录
  RMDir /r "$TEMP\QwenPaw_Backup"
SectionEnd

; ===== 卸载部分 =====
Section "Uninstall"
  Delete "$SMPROGRAMS\QwenPaw Desktop.lnk"
  Delete "$SMPROGRAMS\QwenPaw Desktop (Debug).lnk"
  Delete "$DESKTOP\QwenPaw Desktop.lnk"

  ; 保留用户数据，只删除程序文件
  RMDir /r "$INSTDIR\library"
  RMDir /r "$INSTDIR\Scripts"
  RMDir /r "$INSTDIR\Lib"

  ; 删除注册表
  DeleteRegKey HKCU "Software\QwenPaw"
SectionEnd
```

### Step 2：测试改进

```powershell
# 使用改进后的脚本编译
./scripts/pack/build_win.ps1

# 测试升级流程
# 1. 安装旧版本
# 2. 运行新版本安装程序
# 3. 验证配置被保留
```

---

## 📱 阶段二：添加更新检查 API（第 3-5 天）

### Step 1：改进版本管理

**文件**：`src/qwenpaw/__version__.py`

```python
# -*- coding: utf-8 -*-
__version__ = "1.1.9"
__version_info__ = (1, 1, 9, "final")
__release_date__ = "2026-05-26"

# 检查版本字符串格式
def validate_version(v: str) -> bool:
    """验证版本号格式 (x.y.z)"""
    import re
    return bool(re.match(r'^\d+\.\d+\.\d+$', v))
```

### Step 2：添加更新检查 API

**文件**：`src/qwenpaw/app/_app.py`

在现有的 `get_version()` 端点后添加：

```python
# 添加到 _app.py 的 imports
import aiohttp
from datetime import datetime
from pathlib import Path

# 添加新的端点
@app.get("/api/updates/check")
async def check_for_updates(current_version: str = None):
    """
    检查是否有新版本可用。

    参数:
        current_version: 当前版本 (如果不提供则使用应用版本)

    返回:
        {
            "available": bool,
            "latest_version": str,
            "download_url": str,
            "changelog": str,
            "is_critical": bool,  # 是否必须更新
        }
    """
    if not current_version:
        current_version = __version__

    try:
        # 从 GitHub Releases 获取最新版本
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.github.com/repos/QwenPaw/QwenPaw/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    release_data = await response.json()
                    latest_version = release_data["tag_name"].lstrip("v")

                    # 比较版本
                    from packaging import version
                    if version.parse(latest_version) > version.parse(current_version):
                        return {
                            "available": True,
                            "latest_version": latest_version,
                            "download_url": f"https://releases.qwenpaw.com/QwenPaw-Setup-{latest_version}.exe",
                            "changelog": release_data.get("body", ""),
                            "is_critical": check_if_critical_update(current_version, latest_version),
                            "published_at": release_data["published_at"],
                        }
    except Exception as e:
        logger.debug(f"Failed to check for updates: {e}")

    return {
        "available": False,
        "latest_version": current_version,
    }

def check_if_critical_update(old_version: str, new_version: str) -> bool:
    """判断是否是关键更新（主版本号变化）"""
    from packaging import version
    old = version.parse(old_version)
    new = version.parse(new_version)
    return old.major != new.major


@app.get("/api/updates/release-notes/{version}")
async def get_release_notes(version: str):
    """获取指定版本的发布说明"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.github.com/repos/QwenPaw/QwenPaw/releases/tags/v{version}"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "version": version,
                        "notes": data["body"],
                        "published_at": data["published_at"],
                        "download_url": f"https://releases.qwenpaw.com/QwenPaw-Setup-{version}.exe",
                    }
    except Exception as e:
        logger.error(f"Failed to get release notes: {e}")

    return {"error": "Release not found"}
```

### Step 3：前端更新通知（可选）

如果有 Web UI，添加更新检查：

```typescript
// console/src/hooks/useUpdateChecker.ts
import { useEffect, useState } from 'react';

export function useUpdateChecker() {
  const [updateInfo, setUpdateInfo] = useState(null);
  const [checkError, setCheckError] = useState(null);

  useEffect(() => {
    const checkUpdates = async () => {
      try {
        const response = await fetch('/api/updates/check');
        const data = await response.json();

        if (data.available) {
          setUpdateInfo(data);
          // 显示通知
          console.log(`New version available: ${data.latest_version}`);
        }
      } catch (error) {
        setCheckError(error);
        console.error('Update check failed:', error);
      }
    };

    // 启动时检查
    checkUpdates();

    // 每小时检查一次
    const interval = setInterval(checkUpdates, 3600000);
    return () => clearInterval(interval);
  }, []);

  const downloadUpdate = async () => {
    if (updateInfo) {
      window.open(updateInfo.download_url, '_blank');
    }
  };

  return {
    updateAvailable: !!updateInfo,
    updateInfo,
    downloadUpdate,
    error: checkError,
  };
}
```

---

## 🔧 阶段三：自动下载安装（第 2-3 周）

### 后台下载管理器

**文件**：新建 `src/qwenpaw/services/update_manager.py`

```python
# -*- coding: utf-8 -*-
"""自动更新管理器"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

class UpdateManager:
    """管理应用更新的下载和安装"""

    def __init__(self, download_dir: Optional[Path] = None):
        self.download_dir = download_dir or Path.home() / ".qwenpaw" / "updates"
        self.download_dir.mkdir(parents=True, exist_ok=True)

        self._downloading = False
        self._download_progress = 0.0

    async def check_and_download(self, current_version: str) -> bool:
        """
        检查并自动下载新版本

        返回:
            True 如果下载成功并准备好安装
        """
        try:
            # 检查更新
            update_info = await self._check_updates(current_version)
            if not update_info["available"]:
                return False

            # 下载新版本
            installer_path = await self._download_installer(update_info)
            if not installer_path:
                return False

            logger.info(f"Update downloaded: {installer_path}")
            return True

        except Exception as e:
            logger.error(f"Update check/download failed: {e}")
            return False

    async def _check_updates(self, current_version: str) -> dict:
        """检查是否有新版本"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://localhost:8088/api/updates/check?current_version={current_version}",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return await response.json()
        except Exception as e:
            logger.debug(f"Failed to check updates: {e}")
            return {"available": False}

    async def _download_installer(self, update_info: dict) -> Optional[Path]:
        """下载安装程序"""
        url = update_info["download_url"]
        version = update_info["latest_version"]

        installer_path = self.download_dir / f"QwenPaw-Setup-{version}.exe"

        # 如果已存在，跳过下载
        if installer_path.exists():
            logger.info(f"Installer already exists: {installer_path}")
            return installer_path

        logger.info(f"Downloading update: {url}")
        self._downloading = True
        self._download_progress = 0.0

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        total_size = int(response.headers.get('content-length', 0))

                        with open(installer_path, 'wb') as f:
                            downloaded = 0
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                                downloaded += len(chunk)
                                self._download_progress = downloaded / total_size if total_size else 0.0

                                if downloaded % (10 * 1024 * 1024) == 0:  # 每 10MB 打印
                                    logger.info(f"Downloaded: {downloaded / 1024 / 1024:.1f}MB / {total_size / 1024 / 1024:.1f}MB")

                        logger.info(f"Download complete: {installer_path}")
                        self._downloading = False
                        return installer_path
        except Exception as e:
            logger.error(f"Download failed: {e}")
            self._downloading = False
            if installer_path.exists():
                installer_path.unlink()

        return None

    async def install_update(self, installer_path: Path) -> bool:
        """
        运行安装程序

        注意：这会重启应用
        """
        try:
            import subprocess
            import sys

            logger.info(f"Running installer: {installer_path}")

            # 在后台运行安装程序
            subprocess.Popen([
                str(installer_path),
                "/S",  # 静默安装
            ])

            # 安装程序会自动关闭当前应用并运行新版本
            return True

        except Exception as e:
            logger.error(f"Failed to run installer: {e}")
            return False

    @property
    def download_progress(self) -> float:
        """返回下载进度 (0.0-1.0)"""
        return self._download_progress

    @property
    def is_downloading(self) -> bool:
        """是否正在下载"""
        return self._downloading
```

### 集成到应用启动流程

**文件**：`src/qwenpaw/app/_app.py` - lifespan 函数

```python
from .services.update_manager import UpdateManager

# 全局实例
_update_manager: Optional[UpdateManager] = None

@app.get("/api/updates/check-and-download")
async def check_and_download():
    """
    检查并自动下载新版本
    （通常由后台任务调用）
    """
    global _update_manager
    if _update_manager is None:
        _update_manager = UpdateManager()

    success = await _update_manager.check_and_download(__version__)
    return {
        "success": success,
        "message": "Update downloaded successfully" if success else "No update available"
    }

@app.get("/api/updates/download-progress")
async def get_download_progress():
    """获取下载进度"""
    global _update_manager
    if _update_manager is None:
        return {"progress": 0.0, "downloading": False}

    return {
        "progress": _update_manager.download_progress,
        "downloading": _update_manager.is_downloading,
    }

# 在 lifespan 后台启动中添加
async def check_updates_background():
    """后台检查更新"""
    global _update_manager
    try:
        await asyncio.sleep(10)  # 启动后 10 秒检查

        _update_manager = UpdateManager()
        await _update_manager.check_and_download(__version__)

    except Exception as e:
        logger.debug(f"Background update check failed: {e}")
```

---

## 📊 验证清单

- [ ] 改进后的 NSIS 脚本能够检测旧版本
- [ ] 安装时自动备份用户配置
- [ ] 安装完成后成功恢复配置
- [ ] `/api/updates/check` 端点正常工作
- [ ] 版本号正确写入注册表
- [ ] 前端能够显示更新提示（如有 UI）

---

## 🎯 快速总结

| 阶段 | 工作项 | 工时 | 优先级 |
|-----|------|------|-------|
| 1 | 改进 NSIS 脚本 | 2h | 🔴 立即 |
| 2 | 添加更新检查 API | 3h | 🟠 本周 |
| 3 | 前端更新通知 | 4h | 🟡 下周 |
| 4 | 自动下载安装 | 6h | 🟢 两周 |

**总工时：~15小时 = 2-3 个工作日**

