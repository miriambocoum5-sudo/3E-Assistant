# WhatsApp Setup Guide

This guide walks you through connecting the 3E Chatbot to WhatsApp via Meta Cloud API.

## Prerequisites

- Meta Business Account (create at https://business.facebook.com)
- WhatsApp Business Account linked to your Meta Business Account
- A phone number to use for WhatsApp (a real number or a test number)
- Python environment configured (see README.md)

## Step 1: Get Your Meta Credentials

### 1a. Create a Meta App

1. Go to https://developers.facebook.com/apps
2. Click "Create App"
3. Choose "Business" as the app type
4. Fill in the app name (e.g., "3E Yoga Chatbot")
5. Click "Create App"

### 1b. Add WhatsApp Product

1. In your app dashboard, click "Add Product"
2. Search for "WhatsApp" and add it
3. Go to the WhatsApp product settings

### 1c. Get Your Access Token

1. In WhatsApp settings, go to "API Setup"
2. Under "Temporary access token", copy your token
   - **Save this** — you'll need it for `META_ACCESS_TOKEN` in `.env`
3. Scroll down to find your **Phone Number ID** (under "Test phone number")
   - **Save this** — you'll need it for `META_PHONE_NUMBER_ID` in `.env`

### 1d. Create a Verify Token

This is a token you create (can be any string). It's used to verify that webhook requests actually come from Meta.

1. Choose any string, e.g., `my_secure_verify_token_12345`
2. **Save this** — you'll need it for `META_VERIFY_TOKEN` in `.env`

## Step 2: Expose Your Webhook Publicly

Since Meta needs to reach your webhook over HTTPS, you have two options:

### Option A: Local Testing with ngrok (Fastest)

1. Download ngrok from https://ngrok.com/download
2. Unzip it and run:
   ```
   ngrok http 5000
   ```
3. You'll see output like:
   ```
   Forwarding    https://abc123def456.ngrok.io -> http://localhost:5000
   ```
4. **Copy the HTTPS URL** — this is your webhook URL for Meta
   - Example: `https://abc123def456.ngrok.io`

### Option B: Deploy to Hosting (Production)

- Heroku, AWS Lambda, Railway, or Render
- Once deployed, you'll have a public HTTPS URL
- See "Deploying to Production" section at the bottom

## Step 3: Configure the Webhook in Meta

1. Go back to your WhatsApp product settings
2. Under "Webhook", click "Edit"
3. In the "Callback URL" field, enter:
   ```
   https://your-webhook-url/webhook
   ```
   (Replace `your-webhook-url` with your ngrok or hosted URL)

4. In "Verify Token", enter the verify token you created in Step 1d
   - Example: `my_secure_verify_token_12345`

5. Click "Verify and Save"
   - Meta will send a GET request to your webhook to verify it
   - The webhook will respond with the challenge token
   - If successful, you'll see "Webhook verified"

## Step 4: Set Environment Variables

1. Copy `.env.example` to `.env`:
   ```
   copy .env.example .env
   ```
   (or on Linux/Mac: `cp .env.example .env`)

2. Edit `.env` and fill in your values:
   ```
   PORT=5000
   CHATBOT_DISABLE_UI=1
   
   META_GRAPH_API_VERSION=v25.0
   META_ACCESS_TOKEN=your_meta_access_token_here
   META_PHONE_NUMBER_ID=your_phone_number_id_here
   META_VERIFY_TOKEN=my_secure_verify_token_12345
   WHATSAPP_TEST_RECIPIENT=15551563262
   
   OLLAMA_URL=http://localhost:11434/api/generate
   ```

## Step 5: Start the Webhook

### On Windows:
```
.\run_whatsapp_webhook.ps1
```

Or manually:
```
& .\.venv\Scripts\python.exe whatsapp_webhook.py
```

You should see:
```
 * Running on http://0.0.0.0:5000
```

## Step 6: Subscribe to Message Events (ngrok Only)

If you're using ngrok, you need to tell Meta which events to send to your webhook.

1. Go to your WhatsApp settings in Meta
2. Under "Webhook", click on your webhook URL
3. In the list of events, check:
   - ✅ `messages` (so you receive incoming messages)
   - ✅ `message_template_status_update` (optional, for template updates)

4. Click "Save"

## Step 7: Test the Webhook

1. Go to your WhatsApp Business Account settings
2. Find your test phone number (e.g., +1234567890)
3. Send a message to that number from your personal phone
4. You should get a response from the chatbot!

If you don't get a response:
- Check that the webhook process is still running
- Check the terminal output for errors
- Verify that Ollama is running on `http://localhost:11434`
- Verify that your `.env` file is correct

## Deploying to Production

Once you're ready to go live:

### Option 1: Heroku (Free tier limits apply)

1. Create a Heroku account at https://heroku.com
2. Install Heroku CLI
3. Create a `Procfile` with:
   ```
   web: .venv\Scripts\python.exe whatsapp_webhook.py
   ```
4. Deploy:
   ```
   heroku login
   heroku create your-app-name
   heroku config:set META_ACCESS_TOKEN=your_token
   heroku config:set META_PHONE_NUMBER_ID=your_id
   heroku config:set META_VERIFY_TOKEN=your_verify_token
   git push heroku main
   ```
5. Your webhook URL will be: `https://your-app-name.herokuapp.com/webhook`

### Option 2: AWS Lambda + API Gateway

1. Package the app with dependencies
2. Create a Lambda function
3. Set up API Gateway for HTTPS access
4. Configure environment variables in Lambda
5. Set the API Gateway URL as your webhook URL in Meta

### Option 3: Railway.app (Recommended for Beginners)

1. Create account at https://railway.app
2. Create a new project and connect your GitHub repo
3. Add environment variables in the Railway dashboard
4. Deploy with one click
5. Your URL will be auto-generated

## Troubleshooting

### "Webhook verification failed"
- Check that your verify token in `.env` matches what you entered in Meta
- Check that the webhook is running and publicly accessible
- Try pinging your webhook URL: `curl https://your-url/webhook`

### "Bot doesn't respond to messages"
- Check that the webhook process is running
- Check terminal output for Python errors
- Verify `OLLAMA_URL` is correct and Ollama is running
- Check that you subscribed to `messages` events in Meta

### "AttributeError: 'NoneType' object has no attribute 'xxx'"
- Your environment variables are not being loaded
- Verify `.env` exists in the project root
- Try setting variables manually:
  ```
  $env:META_ACCESS_TOKEN="your_token"
  $env:META_PHONE_NUMBER_ID="your_id"
   & .\.venv\Scripts\python.exe whatsapp_webhook.py
  ```

### Messages are delayed or slow
- Ollama might be processing slowly
- Check system resources (CPU, RAM)
- Make sure no other heavy processes are running

## Next Steps

- Monitor the webhook logs for errors
- Update your knowledge base and run `python ingest_new.py` to keep it fresh
- Use the Streamlit app sidebar "Refresh cached data" button when you update content
- Consider setting up error logging and monitoring for production
