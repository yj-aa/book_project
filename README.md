# 在线图书商城项目

## 项目简介

本项目基于 FastAPI 开发的在线图书商城系统，通过爬虫采集图书数据，完成用户注册登录、图书浏览与分类筛选、收藏、下单购买、订单状态管理等完整购物流程，并提供管理端后台（图书/订单/用户管理、数据统计、CSV 导出）和基于通义千问大模型的 AI 智能荐书功能。

---

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 后端 | Python、FastAPI、Uvicorn |
| 前端模板 | Jinja2、HTML、Bootstrap 5 |
| 数据库 | SQLite |
| 数据采集 | requests、BeautifulSoup4 |
| AI 能力 | 阿里云 DashScope（通义千问 qwen-plus） |
| 密码存储 | SHA-256 哈希 + Session Cookie 鉴权 |

---

## 目录结构

- `backend/`：后端主程序，`main.py` 为 FastAPI 应用入口（全部路由与业务逻辑）
- `templates/`：实际生效的 Jinja2 页面模板（首页、登录注册、图书详情、订单、管理端等）
- `crawler/`：图书数据爬虫 `crawl_book.py`
- `admin-frontend/`、`user-frontend/`：前端模板的历史版本备份
- `.gitignore`：Git 忽略规则（数据库、环境变量、缓存等）

---

## 数据来源说明

图书数据由爬虫自动采集，来源为公开练习站点 [books.toscrape.com](https://books.toscrape.com)，共抓取约 1000 本图书，字段包括：

- 书名、价格、星级评分、分类、库存状态、内容简介、封面图片

数据保存在 SQLite 的 `book_data.db`（`book_info` 表）中。**数据库文件未上传至仓库**，运行爬虫即可自动生成。

---

## 功能特性

**用户端：**

1. 用户注册、登录、登出（密码 SHA-256 哈希存储，Session 鉴权）
2. 图书分页浏览、按分类筛选、星级与价格展示
3. 图书详情页查看
4. 收藏 / 取消收藏图书，查看我的收藏
5. 购买下单、查看我的订单（分页）
6. 取消待发货订单、删除已取消订单记录

**管理端（`/admin`，仅 admin 可访问）：**

1. 订单管理：发货、完成订单，跟踪待发货/已发货/已完成/已取消状态
2. 图书管理：修改价格、修改库存、删除图书
3. 用户管理：删除用户
4. 数据统计仪表盘：销售额、订单量、分类占比、近 30 天订单趋势等
5. 导出图书、订单数据为 CSV 文件

**AI 功能：**

- 接入阿里云通义千问大模型，根据用户需求智能推荐图书（`/chat`）

---

## 快速开始

**1. 安装依赖**

```bash
pip install fastapi uvicorn jinja2 requests beautifulsoup4
```

**2. 采集图书数据（生成 book_data.db）**

```bash
cd crawler
python crawl_book.py
```

**3. 配置 AI 接口（可选，仅影响智能荐书）**

将 `backend/.env.example` 复制为 `backend/.env`，填入你自己的阿里云 DashScope API Key：

```
LLM_API_KEY=sk-your-dashscope-api-key-here
```

**4. 启动服务**

```bash
cd backend
python main.py
```

浏览器访问：<http://127.0.0.1:8000>

**默认管理员账号：** 用户名 `admin`，密码 `admin123`（首次启动自动创建，也可自行注册普通用户）

> 注意：`backend/main.py` 中的模板目录与数据库路径为当前开发机的绝对路径，换环境运行时请按实际位置修改。

---

## 项目工作内容

1. **数据采集**：使用 requests + BeautifulSoup4 爬取图书列表页与详情页，解析书名、价格、评分、分类、库存、简介和封面并入库
2. **数据库设计**：设计用户表（users）、图书表（book_info）、订单表（orders）、收藏表（favorites），通过外键关联订单与图书、用户
3. **后端开发**：基于 FastAPI 实现 20 余个路由，包含表单登录、Session 鉴权、分页查询、订单状态流转等业务逻辑
4. **前端页面**：使用 Jinja2 + Bootstrap 5 实现图书卡片、订单页、登录注册页和管理端仪表盘，支持响应式布局
5. **后台管理**：实现图书/订单/用户的增删改查、经营数据统计与 CSV 数据导出
6. **AI 推荐**：接入通义千问大模型，基于现有图书数据构建推荐 Prompt，实现自然语言智能荐书
