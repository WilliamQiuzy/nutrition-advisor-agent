# MCP Servers Setup Guide

本指南将帮助您为 Healthcare AI Agent 项目配置和使用 MCP (Model Context Protocol) 服务器。

## 概述

我们配置了以下两个 MCP 服务器：

1. **Context7** - 增强的上下文管理和记忆存储
2. **FHIR Healthcare** - 本地医疗保健数据管理

## 快速开始

### 1. 自动安装（推荐）

运行我们提供的安装脚本：

```bash
./scripts/setup-mcp-servers.sh
```

### 2. 手动安装

#### 2.1 检查依赖

确保您已安装：
- Node.js (v16+)
- npm
- Python 3.8+

#### 2.2 安装 MCP 服务器

```bash
# 安装 Context7 MCP Server
npx -y @upstash/context7-mcp
```

## 配置

### 1. Cursor IDE 配置

MCP 服务器已自动配置在以下文件中：
- `~/.cursor/mcp.json` - Cursor IDE 全局配置
- `./mcp.json` - 项目本地配置
- `./config/mcp_servers.json` - 详细配置文件

### 2. 环境变量配置

复制并编辑环境变量：

```bash
cp env.template .env
```

#### Context7 配置

Context7 需要 Upstash Redis 配置：

```bash
# Context7 MCP Server Configuration
UPSTASH_REDIS_REST_URL=your_upstash_redis_rest_url
UPSTASH_REDIS_REST_TOKEN=your_upstash_redis_rest_token
CONTEXT7_MCP_ENABLED=true
```

获取 Upstash Redis 凭据：
1. 访问 [Upstash Console](https://console.upstash.com/)
2. 创建一个新的 Redis 数据库
3. 复制 REST URL 和 REST Token

## MCP 服务器功能

### Context7 MCP Server

**功能：**
- 长期记忆存储
- 上下文管理
- 对话历史检索
- 智能记忆索引

**使用场景：**
- 患者长期健康记录
- 诊疗历史追踪
- 个性化推荐记忆

**示例用法：**
```python
# 在 agents.py 中使用
async def store_patient_context(patient_id, context_data):
    # Context7 会自动管理患者的长期上下文
    pass
```

### FHIR Healthcare MCP Server

**功能：**
- FHIR 资源管理
- 患者数据访问
- 临床数据处理
- 医疗标准集成

**使用场景：**
- 患者数据检索
- 临床记录管理
- 医疗互操作性

## 验证安装

### 1. 检查 MCP 服务器状态

```bash
# 测试 Context7
npx @upstash/context7-mcp --help
```

### 2. 在 Cursor 中验证

1. 重启 Cursor IDE
2. 打开命令面板 (Cmd/Ctrl + Shift + P)
3. 搜索 "MCP" 相关命令
4. 查看是否显示已配置的 MCP 服务器

### 3. 测试集成

运行测试脚本：

```bash
python test_mcp_integration.py
```

## 故障排除

### 常见问题

#### 1. Context7 连接失败

**错误：** `Failed to connect to Upstash Redis`

**解决方案：**
- 检查 `UPSTASH_REDIS_REST_URL` 和 `UPSTASH_REDIS_REST_TOKEN` 是否正确
- 验证 Upstash Redis 数据库状态
- 检查网络连接

#### 2. FHIR MCP 服务器启动失败

**错误：** `FHIR MCP server failed to start`

**解决方案：**
- 检查 Python 依赖：`pip install -r fhir_mcp_server/requirements.txt`
- 验证 FHIR 服务器连接：`curl $FHIR_BASE_URL/metadata`
- 检查端口冲突

### 日志和调试

启用详细日志：

```bash
export MCP_LOG_LEVEL=DEBUG
```

查看日志文件：
- Cursor MCP 日志：`~/.cursor/logs/`
- 项目日志：`./logs/mcp/`

## 高级配置

### 自定义 MCP 服务器配置

编辑 `config/mcp_servers.json`：

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"],
      "env": {
        "CONTEXT7_MAX_MEMORY_SIZE": "100MB",
        "CONTEXT7_RETENTION_DAYS": "90"
      }
    }
  }
}
```

### 负载均衡

对于高并发场景，可以配置多个 MCP 服务器实例：

```json
{
  "mcpServers": {
    "context7-primary": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"],
      "env": {"INSTANCE_ID": "primary"}
    },
    "context7-secondary": {
      "command": "npx", 
      "args": ["-y", "@upstash/context7-mcp"],
      "env": {"INSTANCE_ID": "secondary"}
    }
  }
}
```

## 安全注意事项

1. **API 密钥安全**：
   - 不要在代码中硬编码 API 密钥
   - 使用环境变量管理敏感信息
   - 定期轮换 API 密钥

2. **网络安全**：
   - 使用 HTTPS 连接
   - 配置防火墙规则
   - 限制 MCP 服务器访问权限

3. **数据隐私**：
   - 遵守医疗数据隐私法规 (HIPAA, GDPR)
   - 实施数据加密
   - 定期数据清理

## 监控和维护

### 性能监控

```bash
# 监控 MCP 服务器性能
curl http://localhost:8004/health
curl http://localhost:8004/metrics
```

### 定期维护

1. **更新 MCP 服务器**：
   ```bash
   npx @upstash/context7-mcp@latest
   ```

2. **清理缓存**：
   ```bash
   npm cache clean --force
   rm -rf ~/.cursor/mcp_cache/
   ```

3. **日志轮转**：
   ```bash
   logrotate -f /etc/logrotate.d/mcp-servers
   ```

## 支持和社区

- **官方文档**：[MCP Protocol Specification](https://spec.modelcontextprotocol.io/)
- **GitHub Issues**：项目 Issues 页面
- **社区论坛**：[MCP Community](https://github.com/modelcontextprotocol/community)

## 更新日志

### v1.0.0 (2024-01-XX)
- 初始 MCP 服务器配置
- Context7 集成
- FHIR Healthcare MCP 服务器

### 计划功能
- [ ] MCP 服务器集群支持
- [ ] 自动故障转移
- [ ] 高级监控仪表板
- [ ] 更多医疗专用 MCP 服务器 