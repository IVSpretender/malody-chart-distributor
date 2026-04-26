# malody-chart-distributor

A personal Malody server for distributing self-made charts.

一个用于分发自制谱面的个人用 Malody 服务端。

## 项目状态

- 当前阶段：可用原型（接口已联通，可供客户端测试）
- 技术栈：FastAPI + uv
- 目标场景：个人局域网分发，不追求高并发与复杂后台能力

## 已实现能力

- 扫描谱面来源：支持 `charts/` 内的谱面目录与 `.mcz` 文件
- 核心解析字段：`title`、`titleorg`、`artist`、`artistorg`、`version`、`mode`、`free`、`background`、`cover`、`bpm`
- 商店接口骨架：`/api/store/info`、`/api/store/list`、`/api/store/charts`、`/api/store/query`、`/api/store/download`
- 下载机制：`/api/store/download` 返回逐文件 `items`，客户端下载单文件而非整包

## 环境安装

建议使用 `uv` 管理 Python 环境和依赖。

```powershell
uv python pin 3.12
uv sync
```

如果你正在 conda 的 `base` 环境中，先执行：

```powershell
conda deactivate
```

## 快速启动

1. 把谱面目录或 `.mcz` 放进 `charts/`
2. 启动服务

```powershell
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

3. 本地访问

- `http://127.0.0.1:8000/api/store/info`
- `http://127.0.0.1:8000/docs`

## 目录说明

- `main.py`: FastAPI 入口与接口实现
- `parser.py`: 谱面扫描与解析逻辑
- `charts/`: 你的谱面数据目录
- `docs/`: 参考文档
- `.local/`: 本地开发草稿与示例（通常不入库）

## 接口说明（当前版本）

### `GET /api/store/info`

返回服务器版本与欢迎信息。

### `GET /api/store/list`

返回歌曲列表（分页结构）。

### `GET /api/store/charts`

按 `sid` 返回该歌曲下谱面列表。

### `GET /api/store/query`

按 `sid` 或 `cid` 查询歌曲。

### `GET /api/store/download`

按 `cid` 返回文件下载清单：

```json
{
	"code": 0,
	"items": [
		{
			"name": "1777196119.mc",
			"hash": "8ce2d1aca068f9f7c31df300a036bc10",
			"file": "http://localhost:8000/download/cid/600000/file?name=1777196119.mc"
		}
	],
	"sid": 600000,
	"cid": 600000,
	"uid": 0
}
```

对应下载端点：

- `GET /download/cid/{cid}/file?name=<filename>`: 下载单文件
- `GET /download/cid/{cid}`: 兼容整包下载（调试用途）

## 与客户端兼容的约定

- `cover` 返回 URL 字符串
- `cover` 不存在时回退到 `background`
- `cover` 和 `background` 都不存在时返回空字符串
- 当来源是 `.mcz` 时，`cover` 默认返回空字符串，避免频繁解压带来的额外负担
- 当前测试主机写死为 `http://localhost:8000`

## 已知限制

- 目前是内存扫描模式，尚未接入数据库持久化
- `sid`/`cid` 由服务端生成，不依赖 `.mc` 内原始 sid/cid
- 解析 `.mcz` 会有额外 CPU/IO 开销，生产建议优先使用已解压目录

## 常见问题

### 1) 启动失败（`uvicorn` 退出码 1）

- 确认依赖已安装：`uv sync`
- 确认命令在项目根目录执行
- 避免 conda `base` 干扰：先 `conda deactivate`
- 查看详细错误：

```powershell
uv run python -c "from main import app; print(app.title)"
```

### 2) 下载接口返回 `code: -2`

- 说明 `cid` 不存在
- 先调用 `GET /api/store/charts?sid=...` 获取有效 `cid`

## 计划中的后续工作

- 接入 SQLite 持久化（启动扫描入库）
- 完善筛选、分页和错误码细节
- 增加单元测试与接口回归测试