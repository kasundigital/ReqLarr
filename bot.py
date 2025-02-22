import discord
from discord.ext import commands
import requests
import sqlite3
import json
import os
from flask import Flask, request, jsonify, render_template
from threading import Thread
from flask_basicauth import BasicAuth

# Database setup
conn = sqlite3.connect("requests.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        request_type TEXT,
        title TEXT,
        status TEXT
    )
""")
conn.commit()

# Flask Web UI for Configuration and Logging
app = Flask(__name__)
app.config['BASIC_AUTH_USERNAME'] = "admin"
app.config['BASIC_AUTH_PASSWORD'] = "admin"
basic_auth = BasicAuth(app)

@app.route("/config", methods=["POST"])
@basic_auth.required
def update_config():
    data = request.json
    with open("config.json", "w") as config_file:
        json.dump(data, config_file)
    return jsonify({"message": "Configuration updated successfully"})

@app.route("/config", methods=["GET"])
@basic_auth.required
def get_config():
    if os.path.exists("config.json"):
        with open("config.json", "r") as config_file:
            data = json.load(config_file)
            return jsonify(data)
    return jsonify({"message": "No configuration found"})

# Load configuration from file
if os.path.exists("config.json"):
    with open("config.json", "r") as config_file:
        config_data = json.load(config_file)
        SONARR_API_KEY = config_data.get("sonarr_api_key", "")
        RADARR_API_KEY = config_data.get("radarr_api_key", "")
        DISCORD_BOT_TOKEN = config_data.get("discord_bot_token", "")
        SONARR_URL = config_data.get("sonarr_url", "http://localhost:8989")
        RADARR_URL = config_data.get("radarr_url", "http://localhost:7878")
else:
    SONARR_API_KEY = ""
    RADARR_API_KEY = ""
    DISCORD_BOT_TOKEN = ""
    SONARR_URL = "http://localhost:8989"
    RADARR_URL = "http://localhost:7878"

# Setup ReqLarr Bot
intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents, description="ReqLarr - Movie & Series Request Bot")

def log_request(user, request_type, title, status):
    cursor.execute("INSERT INTO requests (user, request_type, title, status) VALUES (?, ?, ?, ?)", (user, request_type, title, status))
    conn.commit()

def check_existing(title, api_url, api_key):
    headers = {"X-Api-Key": api_key}
    response = requests.get(f"{api_url}/api/v3/search?term={title}", headers=headers)
    if response.status_code == 200:
        data = response.json()
        return any(item['title'].lower() == title.lower() for item in data)
    return False

@bot.command()
async def request_movie(ctx, *, title):
    if check_existing(title, RADARR_URL, RADARR_API_KEY):
        await ctx.send(f"{title} is already in the library!")
        log_request(ctx.author.name, "movie", title, "Already Exists")
    else:
        headers = {"X-Api-Key": RADARR_API_KEY}
        response = requests.post(f"{RADARR_URL}/api/v3/movie", headers=headers, json={"title": title})
        if response.status_code == 201:
            await ctx.send(f"{title} has been requested and added to Radarr!")
            log_request(ctx.author.name, "movie", title, "Requested")
        else:
            await ctx.send("Failed to request the movie.")

@bot.command()
async def request_series(ctx, *, title):
    if check_existing(title, SONARR_URL, SONARR_API_KEY):
        await ctx.send(f"{title} is already in the library!")
        log_request(ctx.author.name, "series", title, "Already Exists")
    else:
        headers = {"X-Api-Key": SONARR_API_KEY}
        response = requests.post(f"{SONARR_URL}/api/v3/series", headers=headers, json={"title": title})
        if response.status_code == 201:
            await ctx.send(f"{title} has been requested and added to Sonarr!")
            log_request(ctx.author.name, "series", title, "Requested")
        else:
            await ctx.send("Failed to request the series.")

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    title = data.get("title", "Unknown")
    event_type = data.get("eventType", "Unknown")
    user = data.get("user", "System")
    
    if event_type == "Download":
        discord_user = bot.get_user(user)
        if discord_user:
            bot.loop.create_task(discord_user.send(f"Your requested {title} has been downloaded!"))
        log_request(user, "notification", title, "Downloaded")
    return jsonify({"message": "Webhook received"})

if __name__ == "__main__":
    Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": 7979}).start()
    bot.run(DISCORD_BOT_TOKEN)
