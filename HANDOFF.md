# ColorWalk Studio — 开发交接文档

## 项目简介

ColorWalk Studio 是一个图片艺术化处理工具，支持两种效果：
- **ColorWalk**：提取图片主色，生成色块 + 照片组合，可叠加文字
- **波点拼图（Dot Puzzle）**：将图片切割成波点拼图，色块区域显示图片内容的剪影

**Tech Stack**：Flask (Python) + PIL/Pillow + 原生 JS + CSS，无前端框架，无数据库

---

## 项目结构

```
colorwalk/
├── app.py                    # Flask 主入口，所有 API 路由
├── templates/
│   ├── landing.html          # 落地页（英文，/）
│   └── index.html            # 工具页面（/app），三步流程：上传→选效果→编辑
├── static/
│   ├── css/style.css         # 所有样式
│   ├── js/main.js            # 所有前端逻辑（约 780 行）
│   ├── gallery/              # 展示用案例图（cw1-4.jpg, dp1-4.jpg）
│   ├── fonts/
│   │   └── default.ttf       # SimHei 字体（支持中文，从 C:/Windows/Fonts 复制）
│   └── uploads/              # 用户上传文件（暂未使用）
└── utils/
    ├── colorwalk.py          # ColorWalk 效果逻辑
    └── dot_puzzle.py         # 波点拼图逻辑
```

---

## 路由说明（app.py）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 落地页 landing.html |
| `/app` | GET | 工具页面 index.html |
| `/api/extract-color` | POST | 从图片提取主色，返回 `{color: [r,g,b]}` |
| `/api/colorwalk` | POST | 生成 ColorWalk 效果图，返回图片 |
| `/api/dot-puzzle` | POST | 生成波点拼图效果图，返回图片 |

API 都接收 `multipart/form-data`，`image` 字段为图片文件。

---

## 前端流程（main.js）

三步状态机，通过 `goToStep(n)` 切换：

1. **Step 1**：上传区 + Playbook 画廊（大家都在做）
2. **Step 2**：选效果模式（ColorWalk / 波点拼图）
3. **Step 3**：编辑器（左预览 + 右设置面板）

关键状态变量：
```javascript
let currentFile = null;      // 原始上传文件
let croppedFile = null;      // 裁剪后文件（优先用于下载）
let previewBlob = null;      // 压缩到 800px 的预览 blob（发给 API）
let currentMode = 'dot';     // 当前效果模式
let selectedPreset = null;   // 选中的 Playbook 预设
let manualDots = [];         // 手动选点模式的点位数组 [{nx,ny}]
```

预览逻辑：用 800px 压缩版发给 API 做实时预览（快），下载时用原图。

---

## 已实现功能

### ColorWalk
- 自动提取图片主色 / 手动选色（含 hex 输入）
- 色块比例调节（20%~60%）
- 文字叠加（内容、字号、颜色 / 自动颜色）

### 波点拼图
- 色块位置（上下左右）、比例调节
- 色块样式：纯色 / 渐变（方向可选）/ 条纹 / 复古纹理
- 波点形态：圆点 / 星星 / 水滴 / 月亮 / 心形 / 文字
- 随机大小选项
- 波点分布：随机 / 网格 / 边缘 / **手动选点**（点击添加/删除，支持随机初始化）
- 色块与图片独立（两侧波点位置解耦）
- 文字叠加（内容、字号）

### 通用功能
- 图片裁剪（Modal，支持自由 / 1:1 / 4:3 / 16:9 / 9:16）
- 下载 PNG / JPG（全分辨率）
- 顶栏缩略图 + 换图 / 裁剪按钮

### Playbook 画廊（Step 1）
- 8 张案例图，4 列网格，图片保留原始比例不裁剪
- Tab 过滤：全部 / ColorWalk / 波点拼图
- 点击卡片 → Lightbox 弹出全尺寸图 + "做同款"按钮
- "做同款"：预填设置 → 用户上传图片后直接跳到编辑器（跳过选效果步骤）
- 编辑器右上角"复制参数"按钮 → 导出当前设置 JSON（用于更新 Playbook 数据）

---

## Playbook 数据（main.js 中的 PLAYBOOK 数组）

目前是**硬编码的默认参数**，并非这些案例图的真实生成参数。

更新流程：
1. 用工具上传案例原图，手动调节参数到满意效果
2. 点"复制参数"得到 JSON
3. 把 JSON 填入 `PLAYBOOK` 数组对应条目的 `settings` 字段

PLAYBOOK 结构：
```javascript
{
  id: 'dp1',
  img: '/static/gallery/dp1.jpg',   // 展示用的结果图
  mode: 'dot',                        // 'dot' | 'colorwalk'
  label: '波点拼图',
  settings: {
    dpPosition: 'right',
    dpBlockRatio: 40,
    dpBlockType: 'solid',
    dpShape: 'circle',
    dpDotSize: 60,
    dpDotCount: 12,
  }
}
```

---

## 待办事项（优先级排序）

### P1 — 下一步要做的

1. **Playbook 参数补全**
   - 用工具为 8 张案例图各生成对应参数，更新 `PLAYBOOK` 数组
   - 这步需要产品方手动操作工具 + 提供参数 JSON

2. **社区提交 + 审核系统**
   - 用户在步骤三下载后，可"提交到社区"
   - 提交内容：结果图 + 设置 JSON + 可选说明
   - 管理员审核通过后展示在 Playbook
   - 建议存储：`data/pending.json` + `data/approved.json` + 图片存 `static/community/`
   - 审核后台：`/admin?key=<密码>` 简单密码保护

### P2 — 中期

3. **上线部署**
   - 目前本地 Flask dev server，需配 gunicorn + nginx 或直接 Railway/Render
   - 注意字体文件（SimHei）在 Linux 上路径不同，需随项目打包 `static/fonts/default.ttf`

4. **工具页英文版**
   - 目前落地页已是英文（landing.html），工具页（index.html）所有文案还是中文
   - 可做 i18n 切换，或做两套模板

5. **案例展示/Playbook 独立页面**
   - 目前 Playbook 在工具页内，可以抽成独立的 `/gallery` 页面

### P3 — 长期

6. **用户账号系统**（如需个人作品集）
7. **更多效果模式**

---

## 已知问题 / 注意事项

- **字体**：`static/fonts/default.ttf` 是 SimHei 的副本，支持中文。在 Linux 部署时需确认这个文件存在，否则中文波点文字会乱码。`_load_font` 函数（dot_puzzle.py）有多个 Windows/Linux 字体路径的 fallback。

- **预览与下载分辨率**：API 收到的是 800px 压缩版（预览快），下载时重新提交原图。两者效果细节会略有差异（随机分布、vintage 纹理因随机数不同）。

- **手动选点模式**：点位存在 `manualDots`（归一化坐标 0~1），换图或裁剪后需重新初始化 canvas（代码已处理）。

- **渐变/条纹 block_color 格式**：是二维数组 `[[r,g,b],[r,g,b]]`，纯色是一维 `[r,g,b]`，app.py 有对应解析逻辑。

- **PREVIEW_MAX_PX = 800**：前端压缩上限，手动选点的归一化坐标基于此分辨率计算。

---

## 本地运行

```bash
pip install flask pillow numpy
python app.py
# 访问 http://localhost:5000
```

---

## 文件变更历史（本次开发周期完成的主要改动）

- `utils/dot_puzzle.py`：新增心形/水滴/星星形状，vintage 纹理，渐变方向，条纹，随机大小，解耦模式，CJK 字体修复
- `app.py`：新增 `gradient_dir`, `size_random`, `decouple` 参数；路由拆分 `/` 和 `/app`
- `templates/index.html`：裁剪 Modal，Playbook 画廊，Lightbox，复制参数按钮
- `templates/landing.html`：全英文落地页（新建）
- `static/css/style.css`：裁剪 Modal 样式，Playbook/Lightbox 样式
- `static/js/main.js`：裁剪逻辑，Playbook + Lightbox + 预设应用逻辑，复制参数
- `static/gallery/`：8 张案例图（新建目录）
- `static/fonts/default.ttf`：替换为 SimHei 副本
