# Windows 桌面版升级 - 实施检查表

## 📋 项目概览

**问题**：Windows 桌面版无法在线升级，每次更新需要卸载重装

**目标**：实现无缝升级体验，用户可以一键安装新版本

**建议方案**：三阶段实施（渐进式改进）

---

## ✅ 阶段一：改进安装脚本（第 1-2 天）

### 任务清单

- [ ] **1.1** 备份当前 desktop.nsi 文件
- [ ] **1.2** 修改 desktop.nsi - 添加旧版本检测函数
- [ ] **1.3** 修改 desktop.nsi - 添加配置备份功能
- [ ] **1.4** 修改 desktop.nsi - 添加配置恢复功能
- [ ] **1.5** 修改 desktop.nsi - 添加版本号写入注册表
- [ ] **1.6** 测试升级流程：安装旧版本 → 运行新版本安装程序
- [ ] **1.7** 验证用户配置被成功保留
- [ ] **1.8** 编写升级说明文档

### 关键文件

| 文件 | 修改内容 | 状态 |
|-----|--------|------|
| scripts/pack/desktop.nsi | 添加旧版本检测、配置备份/恢复 | ⏳ 待处理 |
| scripts/pack/build_win.ps1 | 可选：改进版本检测逻辑 | ✓ 已有基础 |

### 预期效果

✅ 用户无需手动卸载旧版本
✅ 用户配置、数据自动保留
✅ 安装程序智能处理升级场景

---

## 🔍 阶段二：添加更新检查 API（第 3-7 天）

### 任务清单

- [ ] **2.1** 改进 `__version__.py` - 标准化版本管理
- [ ] **2.2** 添加 `/api/updates/check` 端点
- [ ] **2.3** 添加版本比较逻辑（packaging.version）
- [ ] **2.4** 添加 `/api/updates/release-notes/{version}` 端点
- [ ] **2.5** 添加异常处理和日志记录
- [ ] **2.6** 测试版本检查 API
- [ ] **2.7** 前端集成更新检查（如有 Web UI）
- [ ] **2.8** 显示更新提示（版本号、变更日志）

### 关键文件

| 文件 | 修改内容 | 状态 |
|-----|--------|------|
| src/qwenpaw/__version__.py | 标准化版本管理 | ✓ 已有 |
| src/qwenpaw/app/_app.py | 添加更新检查 API 端点 | ⏳ 待处理 |
| console/src/hooks/ | 新增 useUpdateChecker 钩子 | ⏳ 可选 |

### 预期效果

✅ 应用可以检查新版本
✅ 用户可以看到更新提示
✅ 提供版本变更日志

### 测试命令

```bash
# 测试更新检查 API
curl "http://localhost:8088/api/updates/check?current_version=1.1.9"

# 预期返回
{
  "available": true,
  "latest_version": "1.2.0",
  "download_url": "https://releases.qwenpaw.com/QwenPaw-Setup-1.2.0.exe",
  "changelog": "...",
  "is_critical": false
}
```

---

## 📥 阶段三：自动下载安装（第 2-3 周）

### 任务清单

- [ ] **3.1** 创建 `UpdateManager` 类（update_manager.py）
- [ ] **3.2** 实现 `check_and_download()` 方法
- [ ] **3.3** 实现 `_download_installer()` 方法（带进度报告）
- [ ] **3.4** 实现 `install_update()` 方法（调用 NSIS 安装程序）
- [ ] **3.5** 添加后台自动检查（启动后 10 秒）
- [ ] **3.6** 添加下载进度 API - `/api/updates/download-progress`
- [ ] **3.7** 前端显示下载进度
- [ ] **3.8** 前端显示"立即安装"按钮
- [ ] **3.9** 测试完整升级流程

### 关键文件

| 文件 | 新增/修改内容 | 状态 |
|-----|-------------|------|
| src/qwenpaw/services/update_manager.py | 新增：自动下载管理器 | ⏳ 待处理 |
| src/qwenpaw/app/_app.py | 新增：下载进度 API | ⏳ 待处理 |
| console/src/components/ | 新增或修改：更新提示组件 | ⏳ 可选 |

### 预期效果

✅ 后台自动检查更新
✅ 自动下载新版本
✅ 用户可以一键安装
✅ 安装完成后自动运行新版本

---

## 📊 实施时间表

```
第 1-2 天   第 3-7 天    第 8-14 天   第 15-21 天
│           │            │            │
├─ 改进NSIS  ├─ 版本API   ├─ 前端集成  ├─ 完全自动更新
├─ 保留配置  ├─ 更新通知  ├─ 下载管理  ├─ 生产测试
├─ 测试升级  ├─ 发布说明  ├─ 进度显示  ├─ 上线部署
└─ 文档      └─ 测试API   └─ 完整测试  └─ 监控
```

---

## 🔧 开发环境设置

### 前置要求

```bash
# Windows 开发环境
- Windows 10+
- NSIS (makensis.exe) 在 PATH 中
- Python 3.8+
- Node.js / npm (如果有前端)
- Git

# 检查 NSIS 安装
makensis /version

# 检查 Python
python --version
```

### 本地测试

```bash
# 1. 构建新版本安装程序
./scripts/pack/build_win.ps1

# 2. 安装旧版本（使用之前构建的安装程序）
dist/QwenPaw-Setup-1.1.9.exe

# 3. 运行新版本安装程序
dist/QwenPaw-Setup-1.2.0.exe

# 4. 验证：
# - 应该提示检测到旧版本
# - 应该自动卸载旧版本（用户确认后）
# - 应该自动保留配置文件
# - 新版本应该能够运行
```

---

## 📝 代码改动检查清单

### 改动 1：desktop.nsi - 旧版本检测

**检查点**：
- [ ] `.onInit` 函数读取 `InstallPath` 从注册表
- [ ] 检测到旧版本时显示消息框
- [ ] 用户确认后自动运行卸载程序
- [ ] 卸载成功后继续安装

**关键代码**：
```nsi
ReadRegStr $INSTDIR HKCU "Software\Qwenpaw" "InstallPath"
ExecWait '$INSTDIR\Uninstall.exe /S'
```

### 改动 2：desktop.nsi - 配置备份/恢复

**检查点**：
- [ ] 在安装前备份用户配置
- [ ] 备份位置：`$TEMP\Qwenpaw_Backup\`
- [ ] 备份文件：config.json, app_state.json, plugin_config.json
- [ ] 安装后恢复备份文件
- [ ] 清理临时备份目录

**关键代码**：
```nsi
CreateDirectory "$TEMP\Qwenpaw_Backup"
CopyFiles "$INSTDIR\config.json" "$TEMP\Qwenpaw_Backup\"
CopyFiles "$TEMP\Qwenpaw_Backup\config.json" "$INSTDIR\"
RMDir /r "$TEMP\Qwenpaw_Backup"
```

### 改动 3：desktop.nsi - 版本号写入

**检查点**：
- [ ] 写入版本号到注册表 (QWENPAW_VERSION)
- [ ] 写入安装日期到注册表
- [ ] 版本号可以被检索用于后续升级判断

**关键代码**：
```nsi
WriteRegStr HKCU "Software\Qwenpaw" "Version" "${QWENPAW_VERSION}"
```

### 改动 4：_app.py - 更新检查 API

**检查点**：
- [ ] `/api/updates/check` 端点存在
- [ ] 接受 `current_version` 参数
- [ ] 调用 GitHub API 获取最新版本
- [ ] 比较版本号使用 `packaging.version`
- [ ] 返回 JSON 响应（available, latest_version, download_url 等）
- [ ] 异常处理（网络错误、超时等）

**关键代码**：
```python
@app.get("/api/updates/check")
async def check_for_updates(current_version: str = None):
    from packaging import version
    if version.parse(latest) > version.parse(current_version):
        return {"available": True, ...}
```

### 改动 5：update_manager.py - 新建文件

**检查点**：
- [ ] 文件位置：`src/qwenpaw/services/update_manager.py`
- [ ] 包含 `UpdateManager` 类
- [ ] 实现 `check_and_download()` 方法
- [ ] 实现 `_download_installer()` 方法
- [ ] 实现 `install_update()` 方法
- [ ] 支持下载进度报告
- [ ] 支持后台下载

---

## 🧪 测试场景

### 测试场景 1：新用户安装
- [ ] 用户运行 Setup 程序
- [ ] 选择安装位置
- [ ] 安装完成
- [ ] 应用启动成功
- **预期**：✓ 成功

### 测试场景 2：版本升级 (小版本)
- [ ] 已安装 v1.1.9
- [ ] 运行 v1.2.0 Setup
- [ ] 提示检测到旧版本
- [ ] 用户选择升级
- [ ] 旧版本自动卸载
- [ ] 新版本安装
- [ ] 旧版本的配置自动保留
- **预期**：✓ 成功，配置保留

### 测试场景 3：版本升级 (大版本)
- [ ] 已安装 v1.1.9
- [ ] 运行 v2.0.0 Setup
- [ ] 提示检测到旧版本（不兼容）
- [ ] 用户确认删除旧版本
- [ ] 新版本安装
- **预期**：✓ 成功

### 测试场景 4：API 检查更新
- [ ] 调用 `/api/updates/check?current_version=1.1.9`
- [ ] API 返回最新版本信息
- [ ] 比较版本号是否正确
- **预期**：✓ 返回新版本信息

### 测试场景 5：后台自动检查
- [ ] 应用启动
- [ ] 等待 10 秒
- [ ] 后台自动检查更新
- [ ] 如果有新版本，显示提示
- **预期**：✓ 成功

### 测试场景 6：下载新版本
- [ ] 点击"检查更新"
- [ ] 后台开始下载
- [ ] 显示下载进度
- [ ] 下载完成后显示"立即安装"
- [ ] 点击安装，运行 Setup 程序
- **预期**：✓ 成功安装新版本

---

## 📋 部署检查清单

### 代码审查
- [ ] 所有修改都有注释说明
- [ ] 没有硬编码的版本号
- [ ] 异常处理完整
- [ ] 日志记录充分

### 测试覆盖
- [ ] 单元测试通过
- [ ] 集成测试通过
- [ ] 升级场景测试通过
- [ ] 各种版本号格式都能正确处理

### 文档完整
- [ ] 升级说明文档已更新
- [ ] API 文档已更新
- [ ] 用户指南已更新
- [ ] 开发者文档已更新

### 性能指标
- [ ] API 响应时间 < 1s
- [ ] 下载速度正常（网络允许范围）
- [ ] 没有内存泄漏
- [ ] 没有新增的性能问题

### 安全审查
- [ ] 版本号来自可信来源
- [ ] 安装程序签名验证
- [ ] 下载 URL 使用 HTTPS
- [ ] 用户权限处理正确

---

## 🚀 上线部署计划

### 第一阶段：灰度测试
- [ ] 10% 的用户获得改进的安装程序
- [ ] 监控升级成功率
- [ ] 收集用户反馈
- [ ] 修复发现的问题

### 第二阶段：全量发布
- [ ] 100% 的用户获得新安装程序
- [ ] 继续监控升级情况
- [ ] 统计升级成功率
- [ ] 记录任何问题

### 第三阶段：后续维护
- [ ] 监控自动更新检查
- [ ] 分析用户升级行为
- [ ] 根据反馈持续改进
- [ ] 规划后续优化

---

## 📞 支持和故障排除

### 常见问题

**Q: 升级后应用无法启动？**
A:
1. 检查是否成功恢复了配置文件
2. 查看日志文件了解具体错误
3. 尝试卸载并重新安装

**Q: 配置文件丢失？**
A:
1. 检查 `$TEMP\Qwenpaw_Backup\` 是否还有备份
2. 手动恢复备份的配置
3. 联系技术支持

**Q: 自动更新检查失败？**
A:
1. 检查网络连接
2. 查看应用日志中的错误信息
3. 手动访问 GitHub Releases 页面检查

### 日志位置

- **应用日志**：`$LOCALAPPDATA\QwenPaw\logs\`
- **安装日志**：`$TEMP\QwenPaw_Install_*.log`
- **更新日志**：`$LOCALAPPDATA\QwenPaw\update_*.log`

### 联系方式

- GitHub Issues: https://github.com/Qwenpaw/QwenPaw/issues
- 技术支持邮箱: support@qwenpaw.com
- 用户反馈表单: https://forms.gle/...

---

## 📊 成功指标

| 指标 | 目标 | 如何测量 |
|-----|------|--------|
| **升级成功率** | > 95% | 安装日志成功记录 |
| **配置保留率** | 100% | 升级后验证配置文件 |
| **用户满意度** | > 90% | 用户反馈调查 |
| **API 可用性** | > 99.9% | 监控更新检查端点 |
| **下载完成率** | > 98% | 监控下载完成事件 |

---

## 🎉 总结

通过三阶段实施，我们将:

1. ✅ **改进安装程序** - 支持智能升级和配置保留
2. ✅ **添加更新检查** - 用户可以了解新版本
3. ✅ **实现自动更新** - 完全无缝的升级体验

**预期效果**：
- 用户升级体验从"删除 + 重装"变为"一键安装"
- 配置和数据无需手动备份
- 支持自动检查和通知
- 完全向后兼容

**推荐开始时间**：立即开始第一阶段
**预计完成时间**：3-4 周
**所需工作量**：50-60 小时

