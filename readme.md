
# 一起吧 项目

## 项目简介

`一起吧` 是一个基于 Flask 的活动管理与社交平台，用户可以注册、登录、创建活动、参与活动，并通过实时聊天功能与其他用户交流。项目使用 MySQL 数据库存储数据，通过 Flask-SocketIO 实现实时聊天功能，并使用 Alembic 进行数据库迁移管理。

### 功能特点
- 用户注册与登录（支持记住我功能）
- 创建、编辑、删除活动
- 参与或退出活动
- 实时聊天（基于活动和用户对）
- 活动广场（支持搜索和排序）
- 个人主页（编辑用户信息、注销账号）
- 自动删除过期活动（每小时检查）

## 环境要求

在部署项目之前，请确保你的电脑满足以下要求：

- **操作系统**：Windows、macOS 或 Linux
- **Python**：版本 3.8 或以上
- **MySQL**：版本 5.7 或以上（推荐 8.0）
- **pip**：Python 包管理工具（通常随 Python 安装）
- **Git**：用于克隆项目（可选）

## 安装步骤

以下是从零开始部署项目的详细步骤。

### 1. 克隆或下载项目

如果你有 Git，可以通过以下命令克隆项目：

或者直接下载项目压缩包并解压到本地目录，例如 `yuedazi`。

### 2. 设置 Python 虚拟环境

为了避免依赖冲突，建议使用虚拟环境。

#### Windows
```bash
python -m venv venv
venv\Scripts\activate
```

#### macOS/Linux
```bash
python3 -m venv venv
source venv/bin/activate
```

激活虚拟环境后，命令行前会出现 `(venv)` 提示。

### 3. 安装依赖

项目依赖列在 `requirements.txt` 中，使用以下命令安装：

```bash
pip install -r requirements.txt
```

### 4. 安装并配置 MySQL

#### 4.1 安装 MySQL
- **Windows**：下载 MySQL 安装程序（[MySQL Community Server](https://dev.mysql.com/downloads/mysql/)），按照提示安装。
- **macOS**：使用 Homebrew 安装：
  ```bash
  brew install mysql
  ```
- **Linux (Ubuntu)**：
  ```bash
  sudo apt update
  sudo apt install mysql-server
  ```

#### 4.2 启动 MySQL 服务
- **Windows**：通过服务管理器启动 MySQL，或使用命令：
  ```cmd
  net start mysql
  ```
- **macOS/Linux**：
  ```bash
  sudo systemctl start mysql  # Ubuntu/Debian
  # 或者
  brew services start mysql  # macOS with Homebrew
  ```

#### 4.3 配置 MySQL
登录 MySQL（默认安装后 root 用户可能没有密码）：

```bash
mysql -u root -p
```

按提示输入密码（如果没有设置密码，直接回车）。

创建数据库 `yuedazi`：

```sql
CREATE DATABASE app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

设置 root 用户密码为 `666666`（与 `config.py` 中的配置一致）：

```sql
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '666666';
FLUSH PRIVILEGES;
```

退出 MySQL：

```sql
EXIT;
```

#### 4.4 验证 MySQL 配置
确保 `config.py` 中的数据库 URI 正确：

```python
SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:666666@localhost/yuedazi?charset=utf8mb4'
```

如果你的 MySQL 用户名、密码或数据库名不同，请修改此配置。

### 5. 初始化数据库

#### 5.1 运行数据库迁移
项目使用 Alembic 管理数据库迁移。运行以下命令初始化数据库：

```bash
flask db init
flask db migrate -m "Initial migration with activities table"
flask db upgrade
```

这会根据 `migrations` 文件夹中的迁移脚本创建必要的表。

#### 5.2 验证数据库
登录 MySQL，检查表是否创建成功：

```bash
mysql -u root -p
```

输入密码 `666666`，然后：

```sql
USE yuedazi;
SHOW TABLES;
```

### 6. 运行项目

#### 6.1 修改 `run.py`（可选）
为了避免调试模式下 `use_reloader` 导致的 SocketIO 端口冲突，建议修改 `run.py`：

```python
from app import create_app, socketio
import eventlet

app = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False)
```

#### 6.2 启动应用
运行以下命令启动项目：

```bash
python run.py
```

你应该看到类似以下输出：

```
Database URI: mysql://root:666666@localhost/yuedazi?charset=utf8mb4
 * Serving Flask app 'app' (lazy loading)
 * Environment: development
 * Debug mode: on
 * Running on http://0.0.0.0:5000/ (Press CTRL+C to quit)
```

### 7. 访问项目

打开浏览器，访问：

```
http://localhost:5000
```
