# Marketing Agent 🤖

A powerful AI-driven marketing automation agent built with LangGraph that integrates with Salesforce to manage campaigns, contacts, and email marketing workflows. The agent uses Model Context Protocol (MCP) to orchestrate multiple services including Salesforce and Brevo (email marketing).

## 🌟 Features

- **Intelligent Campaign Management**: Create and manage Salesforce campaigns using natural language
- **Contact Management**: Create, update, and assign contacts to campaigns
- **Automated Email Marketing**: Send batch emails via Brevo integration
- **Dynamic Dependency Resolution**: Automatically fetches required data from Salesforce when needed
- **WebSocket Support**: Real-time communication via FastAPI WebSocket server
- **Context Awareness**: Maintains session context across conversation turns
- **LangGraph Orchestration**: Multi-step workflow orchestration with intelligent routing

## 📋 Prerequisites

- Python 3.10 or 3.11
- Salesforce account with API access
- Brevo account for email marketing (optional)
- HashiCorp Vault for secrets management (or modify `config.py` to use environment variables)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/aleenamathews2001/Marketing-agent.git
cd Marketing-agent
```

### 2. Create Virtual Environment

```bash
# On Windows
python -m venv venv311
venv311\Scripts\activate

# On macOS/Linux
python3 -m venv venv311
source venv311/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
# LangChain Configuration
LANGCHAIN_API_KEY=your_langchain_api_key
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_PROJECT=your_project_name
LANGCHAIN_TRACING_V2=true

# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key

# Vault Configuration (if using HashiCorp Vault)
VAULT_ADDR=your_vault_address
VAULT_TOKEN=your_vault_token
```

### 5. Configure Salesforce Credentials

**Option A: Using HashiCorp Vault (Recommended)**

Store your Salesforce credentials in Vault under these secret paths:
- `marketing_salesforce_org`
- `agent_salesforce_org`

Each secret should contain:
```json
{
  "SALESFORCE_USERNAME": "your_username",
  "SALESFORCE_PASSWORD": "your_password",
  "SALESFORCE_SECURITY_TOKEN": "your_security_token",
  "SALESFORCE_INSTANCE_URL": "https://yourinstance.salesforce.com",
  "SALESFORCE_DOMAIN": "login"
}
```

**Option B: Modify config.py to use .env**

Update `config.py` to read from environment variables instead of Vault.

### 6. Run the Agent

**CLI Mode:**
```bash
python main.py
```

**WebSocket Server:**
```bash
python server.py
```

The server will start on `http://0.0.0.0:8001`

## 🏗️ Project Structure

```
Marketing-agent/
├── baseagent.py          # Base agent implementation
├── config.py             # Configuration management
├── main.py               # CLI entry point
├── server.py             # FastAPI WebSocket server
├── vault_utils.py        # Vault integration utilities
├── core/                 # Core modules
│   ├── state.py         # State management
│   └── mcp_loader.py    # MCP tool loader
├── graph/               # LangGraph workflow
│   └── marketing_graph.py
├── nodes/               # Graph nodes
│   ├── dynamic_caller.py
│   └── ...
├── mcp_module/          # MCP integrations
│   ├── Salesforcemcp/
│   └── Brevomcp/
├── lwc/                 # Lightning Web Components
│   ├── pacepalChatbot.html
│   └── pacepalChatbot.js
└── requirements.txt     # Python dependencies
```

## 💻 Usage Examples

### Example 1: Create a Campaign

```python
"Create a campaign named Winter 2025"
```

### Example 2: Create and Assign Contacts

```python
"Create a campaign named Summer Campaign and assign 5 contacts to it"
```

### Example 3: Send Marketing Emails

```python
"Send a marketing email to all contacts in campaign 701fo00000CAgf5AAD"
```

### Example 4: Query and Assign

```python
"Find all contacts whose name starts with 'A' and assign them to campaign 701fo00000CD1VeAAL"
```

## 🔧 WebSocket API

### Connect to WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8001/ws/chat');

ws.onopen = () => {
  ws.send(JSON.stringify({
    message: "Create a campaign named Test Campaign"
  }));
};

ws.onmessage = (event) => {
  const response = JSON.parse(event.data);
  console.log(response.response);
};
```

### Response Format

```json
{
  "type": "response",
  "success": true,
  "response": "Campaign 'Test Campaign' created successfully!",
  "iterations": 2,
  "salesforce_data": true,
  "error": null
}
```

## 🛠️ Development

### Running Tests

```bash
# Test WebSocket connection
python test_websocket.py

# Test HTTP endpoints
python test_http.py

# Test optimizations
python test_optimizations.py
```

### Pre-loading MCP Tools

The server automatically pre-loads MCP tools on startup for better performance. MCP configurations are stored in `baseagent.py`.

## 📝 Configuration

### MCP Services

The agent supports multiple MCP services:
- **Salesforce MCP**: CRUD operations on Salesforce objects
- **Brevo MCP**: Email marketing automation

MCP configurations are loaded from the agent registry in `baseagent.py`.

### Session Context

The WebSocket server maintains session context across messages:
- **created_records**: Tracks all created Salesforce records by object type
- **conversation_history**: Stores previous user goals and results

## 🐛 Troubleshooting

### Common Issues

**1. Virtual environment files tracked by Git**
- Already fixed! The `.gitignore` excludes virtual environments.

**2. Salesforce authentication errors**
- Verify your credentials in Vault or `.env`
- Ensure security token is appended to password (or stored separately)

**3. WebSocket connection fails**
- Check if port 8001 is available
- Verify CORS settings in `server.py`

**4. "Maximum iterations reached" error**
- Increase `max_iterations` in the initial state
- Check MCP tool responses for errors

## 📚 Additional Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Salesforce API Reference](https://developer.salesforce.com/docs/atlas.en-us.api.meta/api/)
- [Brevo API Documentation](https://developers.brevo.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

## 🔒 Security Notes

- Never commit `.env` files or credentials to Git
- Use HashiCorp Vault or similar secret management tools
- Keep your Salesforce security token secure
- Rotate API keys regularly

## 🤝 Contributing

Contributions are welcome! Please ensure:
- Code follows the existing structure
- Add tests for new features
- Update documentation as needed

## 📄 License

This project is private. Contact the repository owner for licensing information.

## 📞 Support

For issues or questions, please open an issue on the GitHub repository or contact the maintainer.

---

**Built with ❤️ using LangGraph, FastAPI, and the Model Context Protocol**
