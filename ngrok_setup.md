# ngrok Setup Guide for Marketing Agent WebSocket

This guide explains how to set up ngrok to expose your local FastAPI WebSocket server to the internet, allowing your Salesforce LWC chatbot to connect to it.

## What is ngrok?

ngrok is a tool that creates a secure tunnel from a public URL to your local development server. This is essential for testing webhooks, APIs, and WebSocket connections from external services like Salesforce.

## Installation

### Windows

1. **Download ngrok:**
   - Visit https://ngrok.com/download
   - Download the Windows version
   - Extract the ZIP file to a folder (e.g., `C:\ngrok`)

2. **Add to PATH (optional):**
   - Add the ngrok folder to your system PATH for easy access
   - Or run ngrok from the extracted folder

3. **Sign up for ngrok account:**
   - Visit https://dashboard.ngrok.com/signup
   - Create a free account
   - Copy your authtoken from the dashboard

4. **Configure authtoken:**
   ```bash
   ngrok config add-authtoken YOUR_AUTH_TOKEN
   ```

### macOS/Linux

```bash
# Using Homebrew (macOS)
brew install ngrok/ngrok/ngrok

# Or download directly
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin
```

## Starting the Marketing Agent Server

1. **Install FastAPI dependencies:**
   ```bash
   cd "c:\Users\ALEENA\OneDrive\Desktop\Marketing agent working latest\Marketing agent"
   pip install -r requirements_fastapi.txt
   ```

2. **Start the FastAPI server:**
   ```bash
   python fastapi_server.py
   ```
   
   Or using uvicorn directly:
   ```bash
   uvicorn fastapi_server:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Verify the server is running:**
   - Open http://localhost:8000 in your browser
   - You should see: `{"status": "online", "service": "Marketing Agent WebSocket API", ...}`

## Starting ngrok Tunnel

1. **Open a new terminal/command prompt**

2. **Start ngrok tunnel:**
   ```bash
   ngrok http 8000
   ```

3. **Copy the HTTPS URL:**
   - ngrok will display output like:
   ```
   Forwarding   https://abc123.ngrok-free.app -> http://localhost:8000
   ```
   - Copy the HTTPS URL (e.g., `https://abc123.ngrok-free.app`)

4. **Convert to WebSocket URL:**
   - Replace `https://` with `wss://`
   - Add `/ws` at the end
   - Example: `wss://abc123.ngrok-free.app/ws`

## Configuring the LWC Chatbot

### Option 1: Update the JavaScript file directly

1. Open `lwc/marketingChatbot/marketingChatbot.js`

2. Find this line:
   ```javascript
   WEBSOCKET_URL = 'ws://localhost:8000/ws';
   ```

3. Replace with your ngrok WebSocket URL:
   ```javascript
   WEBSOCKET_URL = 'wss://abc123.ngrok-free.app/ws';
   ```

4. Deploy the updated component to Salesforce

### Option 2: Use the component property (recommended)

1. Deploy the LWC component to Salesforce

2. Add the component to a Lightning page using App Builder

3. In the component properties panel, update the "WebSocket URL" field with your ngrok URL

4. Save and activate the page

## Testing the Connection

1. **Test the HTTP endpoint:**
   ```bash
   curl https://abc123.ngrok-free.app/health
   ```
   
   Expected response:
   ```json
   {
     "status": "healthy",
     "timestamp": "2025-12-11T12:30:00",
     "sessions": {"active": 0, "total": 0}
   }
   ```

2. **Test WebSocket connection:**
   - Use the provided `test_websocket_client.py` script:
   ```bash
   python test_websocket_client.py wss://abc123.ngrok-free.app/ws
   ```

3. **Test from Salesforce:**
   - Open the Lightning page with the chatbot component
   - Check the connection status indicator
   - Send a test message

## Troubleshooting

### ngrok session expired
- **Problem:** Free ngrok URLs expire after 2 hours
- **Solution:** Restart ngrok and update the WebSocket URL in your LWC

### Connection refused
- **Problem:** FastAPI server is not running
- **Solution:** Make sure `python fastapi_server.py` is running

### CORS errors
- **Problem:** Salesforce domain not allowed
- **Solution:** The FastAPI server already includes Salesforce domains in CORS configuration

### WebSocket connection fails
- **Problem:** Using `http://` instead of `ws://` or `https://` instead of `wss://`
- **Solution:** 
  - Local: Use `ws://localhost:8000/ws`
  - ngrok: Use `wss://your-url.ngrok-free.app/ws` (note the `wss://`)

### ngrok "Visit Site" warning
- **Problem:** ngrok shows a warning page before connecting
- **Solution:** This is normal for free ngrok accounts. Click "Visit Site" to continue

## Production Deployment

For production use, consider:

1. **Deploy FastAPI to a cloud service:**
   - Heroku
   - AWS (EC2, ECS, Lambda)
   - Google Cloud Run
   - Azure App Service

2. **Use a custom domain:**
   - Configure your own domain with SSL certificate
   - Update the WebSocket URL in the LWC

3. **Implement authentication:**
   - Add API key validation
   - Use Salesforce OAuth for secure connections

4. **Monitor and scale:**
   - Set up logging and monitoring
   - Configure auto-scaling based on WebSocket connections

## Keeping ngrok Running

### Windows (using Task Scheduler)
1. Create a batch file `start_ngrok.bat`:
   ```batch
   @echo off
   ngrok http 8000
   ```

2. Schedule it to run on startup using Task Scheduler

### macOS/Linux (using systemd or launchd)
Create a service file to run ngrok as a background service

### Using ngrok's paid plans
- Static domains (URL doesn't change)
- No session time limits
- Custom domains
- More concurrent tunnels

## Quick Reference

```bash
# Start FastAPI server
python fastapi_server.py

# Start ngrok (in another terminal)
ngrok http 8000

# Test health endpoint
curl http://localhost:8000/health

# Test via ngrok
curl https://your-ngrok-url.ngrok-free.app/health
```

## Support

- ngrok documentation: https://ngrok.com/docs
- FastAPI documentation: https://fastapi.tiangolo.com
- WebSocket documentation: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
