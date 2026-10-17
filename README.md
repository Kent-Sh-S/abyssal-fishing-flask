# 深渊渔场 · ABYSSAL Flask 版

原创深海异变题材的数值增量捕鱼游戏，提供账号密码登录、签名 Cookie 存档、开发者计划【beta】和 12 个 User Key 游戏接口。

此仓库为独立 Flask 发行版。需要运行 Python 服务，不能作为纯静态网页直接运行。游戏余额、等级、装备和图鉴保存在客户端签名 Cookie 中；SQLite 只保存账号凭据、登录限流、开发者计划状态和 User Key 哈希。

## 启动

需要 **Python 3.10 或更新版本**。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`。

访问 **http://127.0.0.1:5050**。默认只监听本机，且关闭调试器。端口被占用时可使用 `PORT=5051 python app.py`（macOS / Linux）。

首次使用时，在登录页选择「注册新账号」，设置账号名和密码即可。账号名为 3—24 位中文、字母、数字、下划线或短横线；密码为 8—128 个字符。账号名比较不区分英文大小写。设置面板可以退出登录，原账号的 Cookie 进度保留。

也可以通过 Flask CLI 启动：

```bash
flask --app 'app:create_app()' run --port 5050
```

## 玩法

- 点击「抛下鱼钩」或按空格捕鱼。渔获自动出售，金币立即到账。
- 消耗金币提升潜航员等级。支持升级一次和尽可能升级，最高 Lv.870。
- Lv.5 开放自动拖网；购买后自动开启。可以暂停，升级可缩短间隔。离线最多结算 **1 小时**。
- 异变声呐增加稀有鱼的相对出现权重。Lv.30 开放的深渊护符消耗钻石，每级令单鱼收益翻倍。
- 8 种异变鱼逐渐解锁。点击图鉴卡片查看档案，支持稀有度筛选。
- Lv.30 开放黑市，将金币随机兑换成钻石。
- 右上角可以开启音效。设置中可以切换中文单位 / 科学计数法、查看精确余额和重置存档。
- 支持手机布局、键盘操作、减少动态效果的系统偏好。所有美术为项目内原创 SVG，音效由 Web Audio 生成。

## 数值规则

**本项目中的「兆」固定表示 10¹²。钻石的 64 位整数按有符号 INT64 理解。**

### 金币：IEEE 754 binary64 / F64

- 金币用 Python `float` 运算并序列化进签名 Cookie。
- F64 最大有限值为 `1.7976931348623157e308`。
- 按“在最大值前停下”的要求，游戏实际上限为 `math.nextafter(sys.float_info.max, 0.0)`，即 **`1.7976931348623155e308`**，严格小于 F64 最大有限值。
- 单鱼收益、余额和累计收益均执行饱和处理，避免产生 `Infinity` / `NaN`，金币不会回绕。
- F64 大数有精度间隔，极大余额可能不响应非常小的增减，这是 F64 的性质。设置面板显示 17 位有效数字以便检查。

Lv.1 每条鱼的金币收益保证在 **10—1,000,000** 之间，使用对数分布，让低收益更常见。

等级基础收益以如下曲线增长：

```text
growth = (log10(50 × 10¹²) - 3.5) / 29
基础单鱼收益(L) = min(10^(3.5 + (L-1) × growth), 金币上限)
升级费用(L) = 基础单鱼收益(L) × 0.35
```

Lv.30 的基础单鱼收益约为 **50 兆（5 × 10¹³）**，普通鱼围绕该数值波动。稀有鱼和深渊护符会增加收益。初期较宽的收益区间逐渐收窄，Lv.30 起基础随机系数约为 `0.708—1.413`。进入数值上限附近后收益饱和，等级到 Lv.870 停止升级。

### 钻石：signed INT64

- 上限 `INT64_MAX = 9,223,372,036,854,775,807`（`2^63 - 1`）。
- 钻石用 Python 整数运算并显式钳制到 INT64 范围，精确整数随游戏数据序列化进签名 Cookie。
- API 的钻石余额、获得量、销毁量、钻石价格均使用**十进制字符串**传输，避免 JSON 经 JavaScript `Number` 丢失精度。
- 前端用 `BigInt` 做钻石余额和价格比较，精确值在余额提示及设置面板显示。顶部缩写仅用于展示。
- `实际到账 = min(本次应发, INT64_MAX - 现有钻石)`。多余部分销毁，钱包不会回绕、变负或超过上限。

### 黑市兑换

潜航员 **Lv.30** 起可交易。常规兑换可选择持币的 25%、50% 或 100%，向下取整到整兆，未兑换的零钱保留。每次交易独立抽取一次比率，整笔交易使用同一个比率。

| 每 1 兆金币可兑换钻石 | 概率 |
| ---: | ---: |
| 1 | 60% |
| 10 | 25% |
| 100 | 10% |
| 1,000 | 4% |
| 10,000 | 0.9% |
| 1,000,000 | 0.1% |

比率越高，其概率严格越低。使用服务端 `random.SystemRandom` 生成随机结果。

**特殊规则：** 持币**严格超过** `1,000,000,000 兆 = 10²¹` 时，任意兑换份额都会进入深渊契约：**消耗全部金币**，应发 `INT64_MAX` 个钻石，再按钱包剩余容量到账，溢出部分销毁。界面会在兑换按钮前展示该规则。恰好 `10²¹` 金币仍采用常规随机兑换。此处“消耗全部”是对用户未指定特殊兑换成本的明确实现约定。

## Flask 账号与 Cookie 存档

首次启动会创建被 `.gitignore` 排除的 `instance/`：

```text
instance/
├── abyss.sqlite3   # 账号、密码哈希、登录限流、开发者计划及 User Key 哈希；无邮箱
└── .secret         # 持久会话签名密钥
```

服务端用 SQLite 保存账号凭据，密码经 Werkzeug `scrypt` 加盐哈希处理，Cookie 中不保存密码。连续五次登录失败会触发一分钟冷却。

游戏余额、等级、装备和图鉴保存在每个账号独立的 `abyss_save_<账号ID>` Cookie 中，以服务端密钥签名并压缩；`abyss_session` Cookie 只承载登录会话和 CSRF 信息。Cookie 均设置 HttpOnly、SameSite=Lax，有效期一年；HTTPS 下存档 Cookie 同时设置 Secure。游戏 Cookie 只保留最近六条渔获以控制大小。

相同浏览器登录同一账号可继续游戏，退出不会删除游戏 Cookie；清除 Cookie、换浏览器或跨设备登录会从头开始。注册其他账号不会读取原账号的存档。服务端验证 Cookie 签名及账号归属，浏览器不能直接提交金币、钻石或等级。网页 POST 请求验证 CSRF Token，独立开发者接口使用 User Key 鉴权；手动捕鱼有 0.65 秒冷却。支持 Web Locks 的浏览器会将同源标签页请求串行化；不支持此 API 的浏览器多标签页操作可能覆盖 Cookie 进度。

此前匿名 SQLite 版的旧存档会保留在原 `players` 表，首次注册时可认领本浏览器旧 Cookie 对应的航程；认领后不再往该旧表写入进度。新数据库保存账户信息、登录限流、开发者计划状态和 User Key 哈希，不保存游戏进度。

备份存档时保留整个 `instance/`，并保留原浏览器 Cookie。可通过 `ABYSS_DATABASE` 指定数据库文件路径，通过 `ABYSS_SECRET` 提供会话密钥。数据库文件所在目录必须已经存在。更换会话密钥会使旧 Cookie 失效。

本项目不提供云端游戏进度同步，跨设备继续航程需要自行保留并传递对应的 Cookie。

## Flask 开发者计划【beta】与 API

注册时可勾选「加入开发者计划【beta】」。已有账号可在游戏「航行设置 → 开发者计划」进入 `/developer` 加入。Key 管理页支持命名、创建、查看前缀与最近使用时间、吊销；每个账号最多保留 5 个有效 Key。完整 Key 仅创建时返回一次，数据库只保存 SHA-256 哈希。旧账号数据库会自动增加所需字段，不重置账号。

完整开发手册位于 `/developer/docs`，需要登录并加入计划。以下 12 个接口不要求网页登录或 CSRF Token，每次请求都要携带 `X-User-Key: YOUR_USER_KEY`，也兼容 `Authorization: Bearer YOUR_USER_KEY`。

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| POST | `/fish/enablenet` | 开启渔网；未购买返回 400 |
| POST | `/fish/disablenet` | 关闭渔网；未购买返回 400 |
| POST | `/fish` | 捕鱼；0.65 秒冷却中返回 429 |
| POST | `/diamond25` | 以 25% 金币兑换钻石；Lv.30 解锁 |
| POST | `/diamond50` | 以 50% 金币兑换钻石；Lv.30 解锁 |
| POST | `/diamonds` | 以全部金币兑换钻石；Lv.30 解锁 |
| POST | `/uphufu` | 升级深渊护符 |
| POST | `/upshengna` | 升级异变声呐 |
| POST | `/uptuowang` | 购买或升级自动拖网 |
| POST | `/upgrademain` | 升级潜航员一次；金币不足或已达 Lv.870 返回 400 |
| GET | `/getpays` | 获取金币、钻石及渔获数 |
| GET | `/tujian` | 获取已捕获及未捕获图鉴 |

API 与网页调用同一个 `game.py`。成功响应为 `{"ok":true,"data":...,"state":...,"storage":"signed-cookie","auto_catches":0}`；失败响应为 `{"ok":false,"error":"原因"}`。钻石数量使用十进制字符串，避免 INT64 精度损失。GET 查询也会结算自动拖网并返回更新的 Cookie；规则失败不会提交游戏存档，待结算渔获会在下次成功请求时结算。

**User Key 只负责鉴权，客户端 Cookie 保存航程。** 同一账号的多个 Key 在同一 Cookie jar 中使用同一存档；不同 Cookie jar 各自开始航程。脚本需要保留响应 Cookie，连续请求应串行执行。Key 创建与吊销仍需要网页登录和 CSRF；吊销后后续调用立即返回 401。纯 JS 站点不提供这些接口。

```bash
export ABYSS_USER_KEY='替换为你创建的 User Key'
curl -sS -b abyss-cookies.txt -c abyss-cookies.txt \
  -H "X-User-Key: $ABYSS_USER_KEY" -X POST http://127.0.0.1:5050/fish
curl -sS -b abyss-cookies.txt -c abyss-cookies.txt \
  -H "X-User-Key: $ABYSS_USER_KEY" http://127.0.0.1:5050/getpays
```

开发手册提供 Python `requests.Session` 与无需额外依赖的标准库 `CookieJar` 示例。两者默认只在当前进程保留 Cookie，需要跨脚本运行继续航程时应保存并重新加载 Cookie jar。

## 项目结构

```text
app.py                       账号、密码哈希、签名 Cookie、CSRF
game.py                      共用游戏规则、数值上限和随机渔获
developer.py                 开发者计划、User Key 管理及 12 个接口
templates/                   游戏、登录、Key 管理和开发文档页面
static/                      样式、交互、原创 SVG 和鱼类插图
tests/                       数值、账号、Cookie、Key、API 和迁移测试
requirements.txt             Flask 依赖
```

## 验证

安装依赖后运行，无需额外测试依赖：

```bash
python -m unittest discover -s tests -v
```

45 项 Python 测试覆盖数值边界、账号与 Cookie 隔离、CSRF、Key 创建与吊销、API 鉴权、潜航员升级与网页结果一致、失败请求不扣资源、自动拖网结算及数据库迁移。测试使用临时数据库，不修改真实账号和存档。

## 发布内容

不包含本机的 `instance/`、数据库、服务端签名密钥、真实 User Key、Cookie、虚拟环境或 GitHub Pages 自动发布配置。首次启动会在本机生成独立的账号数据库和签名密钥。

## 题材参考

原创美术和代码，题材参考 [DREDGE](https://www.dredge.game/) 与 [Drowned Lake](https://store.steampowered.com/app/2601540/Drowned_Lake/) 的深海捕鱼与恐怖氛围。
