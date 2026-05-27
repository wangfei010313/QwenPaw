# Windows 桌面版升级 - 方案概览（一页纸）

## 🎯 问题
Windows 桌面版每次更新需要**卸载 → 重装**，用户体验差

## 💡 解决方案

### 三个阶段，逐步实施

```
┌─ 阶段一（1-2天）          ┌─ 阶段二（3-7天）          ┌─ 阶段三（8-21天）
│ 改进安装脚本              │ 添加版本检查 API           │ 自动下载 + 安装
│                          │                          │
├─ 旧版本自动检测           ├─ /api/updates/check       ├─ UpdateManager 类
├─ 配置文件备份             ├─ 前端更新提示             ├─ 后台自动检查
├─ 配置文件恢复             ├─ 发布说明展示             ├─ 进度条显示
└─ 版本号写入注册表         └─ 支持手动下载             └─ 一键安装新版本
```

## 📝 关键改动（4 个文件）

| 文件 | 改动 | 时间 |
|-----|------|------|
| **scripts/pack/desktop.nsi** | 检测旧版本，备份/恢复配置 | 2h |
| **src/qwenpaw/__version__.py** | 标准化版本管理 | 0.5h |
| **src/qwenpaw/app/_app.py** | 新增 API 端点 | 3h |
| **src/qwenpaw/services/update_manager.py** | 新建：自动更新管理 | 6h |

## 🚀 快速开始（立即做）

### Step 1：改进 NSIS 脚本（2 小时）
```bash
# 修改 scripts/pack/desktop.nsi
# 1. 添加 .onInit 函数 - 检测旧版本
# 2. 添加备份/恢复部分 - 保留用户配置
# 3. 添加版本号写入 - 用于升级判断

./scripts/pack/build_win.ps1  # 重新构建
```

### Step 2：添加更新检查 API（3 小时）
```python
# 修改 src/qwenpaw/app/_app.py
@app.get("/api/updates/check")
async def check_for_updates(current_version: str = None):
    # 从 GitHub 获取最新版本
    # 比较版本号
    # 返回更新信息
```

### Step 3：自动下载管理（6 小时）
```python
# 新建 src/qwenpaw/services/update_manager.py
class UpdateManager:
    async def check_and_download(version):  # 检查并下载
    async def install_update(installer):    # 运行安装程序
```

## 📊 方案对比

| 特性 | 阶段一 | 阶段一+二 | 全部 |
|-----|------|---------|------|
| 自动检测旧版本 | ✅ | ✅ | ✅ |
| 保留用户配置 | ✅ | ✅ | ✅ |
| 版本检查通知 | ❌ | ✅ | ✅ |
| 自动下载安装 | ❌ | ❌ | ✅ |
| 用户体验 | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 实施工时 | 2h | 5h | 11h |
| 立即可交付 | ✅ | ✅ | ⏳ |

## ✅ 验证步骤

```bash
# 测试升级流程
1. 安装旧版本
2. 运行新版本 Setup
3. 验证：
   - 提示检测到旧版本 ✓
   - 自动卸载旧版本 ✓
   - 配置文件被保留 ✓
   - 新版本正常启动 ✓

# 测试 API
curl "http://localhost:8088/api/updates/check?current_version=1.1.9"
# 返回最新版本信息 ✓
```

## 📚 详细文档

| 文档 | 用途 |
|-----|------|
| DESKTOP_UPGRADE_SOLUTIONS.md | 三个方案的详细技术方案 |
| DESKTOP_UPGRADE_QUICK_GUIDE.md | 代码改动逐步指南 |
| DESKTOP_UPGRADE_CHECKLIST.md | 完整的实施检查表 |

## 🎯 推荐行动

### 立即开始
- 改进 NSIS 脚本（可立即发布）
- 添加版本 API（支持手动检查）

### 本周完成
- 前端集成更新提示
- 支持手动下载链接

### 下周开始
- 自动下载功能
- 后台自动检查

## 💰 投资回报

| 投入 | 产出 |
|-----|------|
| 11 小时工作 | 用户升级体验从⭐⭐升至⭐⭐⭐⭐⭐ |
| 3-4 周时间 | 支持无缝升级，配置零损失 |
| 4 个文件改动 | 完整的自动更新框架 |

## 🔗 快速链接

- [完整解决方案](./DESKTOP_UPGRADE_SOLUTIONS.md)
- [实施指南](./DESKTOP_UPGRADE_QUICK_GUIDE.md)
- [检查表](./DESKTOP_UPGRADE_CHECKLIST.md)

---

**建议**：从阶段一开始，明天可以发布第一个改进版本 🚀

