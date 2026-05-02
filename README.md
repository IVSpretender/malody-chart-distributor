# malody-chart-distributor

**一个用于分发自制谱面的个人 Malody 服务端**

在局域网中搭建属于自己的 Malody 谱面商店，轻松分享自制谱面给朋友。

## 1. 快速开始

### 1.0. 系统要求

- **Python 3.12+**
- **Git**
- **uv**（Python 依赖管理工具）

如果还未安装 `uv`，请先访问 [uv 官网](https://docs.astral.sh/uv/) 按照说明安装。

### 1.1. 克隆仓库

```powershell
# Windows PowerShell
git clone https://github.com/IVSpretender/malody-chart-distributor.git
cd malody-chart-distributor
```

```bash
# Linux/macOS
git clone https://github.com/IVSpretender/malody-chart-distributor.git
cd malody-chart-distributor
```

### 1.2. 安装依赖

如果你正在 conda 的 `base` 环境中，先执行：

```powershell
conda deactivate
```

然后安装依赖：

```powershell
uv python pin 3.12
uv sync
```

### 1.3. 启动服务

运行对应系统的启动脚本，脚本会自动：
- 创建 `config.py`（从 `config.example.py` 复制）
- 创建必需的目录结构（`charts`、`promote`、`events` 等）
- 显示配置建议

**Windows (PowerShell):**

```powershell
.\run.ps1
```

**Linux/macOS (Bash):**

```bash
chmod +x run.sh
./run.sh
```

### 1.4. 编辑配置

打开 `config.py`，按需调整：

- **`BASE_URL`**: 服务器地址，默认 `http://localhost:8000`。局域网访问时改为 `http://你的IP:8000`
- **`SONG_SOURCE_ROOTS`**: 歌曲来源目录列表
- **`PAGE_SIZE`**: 每页返回多少首歌曲
- **`WELCOME_MESSAGE`**: 欢迎信息

### 1.5. 放置谱面文件

#### 普通歌曲

将解压后的谱面目录放入 `charts/` 文件夹：

```
charts/
├── Song1/
│   ├── Song1 RM 4K Hard.mc
│   ├── cover.jng
│   └── background.jpg
└── Song2/
    ├── Song2example_chart.mc
    └── cover.png
```

#### 推荐歌曲

将特别推荐的谱面放入 `promote/` 文件夹，这些歌曲会在客户端的"推荐"标签页显示。

#### 分类标签

如果想为歌曲添加标签，将其放入 `charts_tagged/<标签1> <标签2> ... <标签n>/` 文件夹(标签之间用空格分隔)。搜索标签时不区分英文字母大小写。

```
charts_tagged/
├── GameMusic/
│   └── GameMusic1/
│       └── 1777196119.mc
└── ExampleTag1 ExampleTag2 ExampleTag3/
    └── ExampleSong1/
        └── 1776350058.mc
```

#### 活动

创建事件文件夹 `events/<活动名>/`，放入歌曲和 `event.json` 配置：

```
events/
└── event1/
    ├── event.json
	├── event_cover.png
    ├── event1_song1/
    │   └── 1775961385.mc
    └── event1_song2/
        └── 1776501093.mc
```

如果不创建 `event.json`，系统会创建并使用默认配置：

```json
{
  "sponsor": config.EVENT_DEFAULT_SPONSOR,
  "start_date": "2026-04-28",
  "end_date": "2099-12-31",
  "active": true
}
```

### 1.6. 连接到 Malody 客户端

1. 在 Malody V 客户端中进入 **设置 → 服务器**
2. 将 **谱面服务器主机** 设置为 `http://你的服务器IP:8000/`
3. 返回商店，即可看到你的谱面列表

## 2. 文件说明

| 文件/目录 | 用途 |
|---------|------|
| `main.py` | 服务端主程序（FastAPI） |
| `parser.py` | 谱面文件扫描和解析逻辑 |
| `db.py` | 数据库操作 |
| `config.py` | 配置文件（用户修改） |
| `config.example.py` | 配置示例模板 |
| `charts/` | 普通谱面目录（用户放置） |
| `promote/` | 推荐谱面目录（用户放置） |
| `events/` | 活动目录（用户放置） |
| `charts_tagged/` | 分类标签谱面目录（用户放置） |
| `data/` | 数据库存储目录 |
| `run.ps1` / `run.sh` | 启动脚本 |

## 3. 常见操作

### 3.1. 添加新谱面

1. 将谱面文件夹复制到 `charts/` 或其他来源目录
2. 服务器会自动扫描并加载（开启 `--reload` 模式时）
3. 客户端重新连接后即可看到新谱面

### 3.2. 修改谱面信息

1. 编辑谱面文件夹中的 `.mc` 文件（Malody chart 格式）
2. 服务器自动检测变化并更新
3. 客户端重新连接后生效

### 3.3. 删除或隐藏谱面

- 直接从文件夹中删除对应的谱面目录或文件
- 服务器会自动扫描并移除

### 3.4. 服务器地址配置

**本地测试本项目：**
```
BASE_URL = "http://localhost:8000" 
```

**服务器部署本项目：**
```
BASE_URL = "http://<你的服务器IP>:8000"
```

如果修改 `BASE_URL` 中的端口号，需要在 run.ps1 或 run.sh 中修改启动命令中的端口号：

```bash
uv run uvicorn main:app --reload --host 0.0.0.0 --port <端口号> --reload-dir charts ...
```

## 4. 常见问题

### 4.1. 启动失败

**问题：** 运行脚本后报错

**排查步骤：**
1. 确认依赖已安装：`uv sync`
2. 确认在项目根目录运行
3. 检查是否在 conda base 环境（执行 `conda deactivate`）
4. 查看详细错误：`uv run python -c "from main import app; print(app.title)"`

### 4.2. 客户端无法连接

**问题：** Malody 客户端无法找到服务器

**排查步骤：**
1. 确认服务器正在运行（终端无错误消息）
2. 检查 `BASE_URL` 是否正确设置
3. 确认防火墙允许 8000 端口通信
4. 确认客户端与服务器在同一网络

### 4.3. 谱面无法加载

**问题：** 放入 `charts/` 的谱面未出现在客户端

**排查步骤：**
1. 确认谱面文件夹中至少有一个 `.mc` 文件
2. 确认文件夹名称和 `.mc` 文件名不含特殊符号
3. 尝试重启服务器
4. 检查服务器日志中是否有解析错误

### 4.4. 谱面下载失败

**问题：** 客户端下载时出错

**排查步骤：**
1. 确认源文件仍存在于对应目录
2. 确认文件没有被其他程序锁定
3. 尝试重启服务器

## 5. 环境信息

- **Python 版本**：3.12
- **主要依赖**：FastAPI, uvicorn
- **数据库**：SQLite（位于 `data/` 目录）
- **目标场景**：局域网个人分发，单机或小规模使用

## 需要帮助？

- 查看服务器启动时的日志输出
- 询问 AI 助手
- 提交 issue