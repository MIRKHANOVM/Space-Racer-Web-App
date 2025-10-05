import os
import sqlite3
import threading
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from flask import Flask, request, jsonify
from dotenv import load_dotenv  # KEEP THIS!

# Set up logging for Render
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Load environment variables - KEEP THIS!
load_dotenv()

# Initialize Flask app for web API
flask_app = Flask(__name__)

# Enable CORS for all routes
@flask_app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# SQLite database setup
def init_db():
    conn = sqlite3.connect('game_data.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scores (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            score INTEGER,
            games_played INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("✅ Database initialized successfully!")

# API Route: Save score
@flask_app.route('/api/score', methods=['POST', 'OPTIONS'])
def save_score():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'})
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        user_id = data.get('user_id')
        username = data.get('username')
        first_name = data.get('first_name')
        score = data.get('score')
        
        if not user_id or score is None:
            return jsonify({'error': 'Missing user_id or score'}), 400
        
        conn = sqlite3.connect('game_data.db', check_same_thread=False)
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT score FROM scores WHERE user_id = ?', (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            # Update if new score is higher
            if score > existing[0]:
                cursor.execute(
                    'UPDATE scores SET score = ?, username = ?, first_name = ?, games_played = games_played + 1 WHERE user_id = ?',
                    (score, username, first_name, user_id)
                )
                message = 'New high score saved!'
            else:
                cursor.execute(
                    'UPDATE scores SET games_played = games_played + 1 WHERE user_id = ?',
                    (user_id,)
                )
                message = 'Score updated (not a high score)'
        else:
            # Insert new record
            cursor.execute(
                'INSERT INTO scores (user_id, username, first_name, score, games_played) VALUES (?, ?, ?, ?, 1)',
                (user_id, username, first_name, score)
            )
            message = 'First score saved!'
        
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': message})
        
    except Exception as e:
        logging.error(f"❌ Error saving score: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# API Route: Get leaderboard
@flask_app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    try:
        conn = sqlite3.connect('game_data.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT first_name, username, score FROM scores ORDER BY score DESC LIMIT 10')
        scores = cursor.fetchall()
        conn.close()
        
        leaderboard = []
        for i, (first_name, username, score) in enumerate(scores, 1):
            display_name = first_name or username or f'Player {i}'
            leaderboard.append({
                'rank': i,
                'name': display_name,
                'score': score
            })
        
        return jsonify(leaderboard)
        
    except Exception as e:
        logging.error(f"❌ Error getting leaderboard: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# API Route: Get user stats
@flask_app.route('/api/user_stats/<int:user_id>', methods=['GET'])
def get_user_stats(user_id):
    try:
        conn = sqlite3.connect('game_data.db', check_same_thread=False)
        cursor = conn.cursor()
        
        # Get user's score
        cursor.execute('SELECT score, games_played FROM scores WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            return jsonify({
                'score': result[0],
                'games_played': result[1]
            })
        else:
            return jsonify({'error': 'User not found'}), 404
            
    except Exception as e:
        logging.error(f"❌ Error getting user stats: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Telegram Bot Functions
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = f"""
👋 Welcome *{user.first_name}* to *Space Jump*! 🚀

Tap the button below to play the game!

🎮 *How to Play:*
• Tap to make the spaceship jump
• Avoid obstacles and survive!
• Compete for high scores!

*Ready for your space mission?* 🪐
    """
    
    # Create keyboard with web app button
    keyboard = [
        [KeyboardButton("🚀 Play Space Jump", web_app={"url": f"{WEBAPP_URL}"})]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Create keyboard with web app button
    keyboard = [
        [KeyboardButton("🎮 Play Now", web_app={"url": f"{WEBAPP_URL}"})]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"🚀 Launching Space Jump for *{user.first_name}*...",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = sqlite3.connect('game_data.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT first_name, username, score FROM scores ORDER BY score DESC LIMIT 5')
        top_players = cursor.fetchall()
        conn.close()
        
        if not top_players:
            await update.message.reply_text(
                "🏆 *No scores yet!*\n\nBe the first to play! 🚀",
                parse_mode='Markdown'
            )
            return
        
        leaderboard_text = "🏆 *Space Jump Leaderboard* 🚀\n\n"
        
        for i, (first_name, username, score) in enumerate(top_players, 1):
            name = first_name or username or f"Player {i}"
            leaderboard_text += f"{i}. *{name}*: `{score}` points\n"
        
        leaderboard_text += "\nPlay with /play to climb the ranks! 🎮"
        
        await update.message.reply_text(leaderboard_text, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"❌ Error showing leaderboard: {e}")
        await update.message.reply_text("❌ Couldn't fetch leaderboard. Try again later!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🆘 *Space Jump Help* 🚀

*Commands:*
/start - Welcome message
/play - Launch the game
/leaderboard - Show top players

*Game Controls:*
• Tap to jump over obstacles
• Survive as long as possible!

*Need help?* 👨‍🚀
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle any text message that's not a command"""
    user = update.effective_user
    
    keyboard = [
        [KeyboardButton("🚀 Play Space Jump", web_app={"url": f"{WEBAPP_URL}"})]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"👋 Hello *{user.first_name}*! Ready to play? 🚀\n\nUse /play or tap the button below!",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# Configuration - Get from environment variables (.env file)
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('WEBAPP_URL')
FLASK_PORT = int(os.getenv('FLASK_PORT', '8080'))  # Use your .env value
FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')   # Use your .env value

def run_flask():
    logging.info(f"🚀 Starting Flask server on {FLASK_HOST}:{FLASK_PORT}")
    flask_app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)

def main():
    # Validate environment variables
    if not BOT_TOKEN:
        logging.error("❌ ERROR: BOT_TOKEN not found in environment variables!")
        logging.info("💡 Make sure you have a .env file with your bot token")
        return
        
    if not WEBAPP_URL:
        logging.error("❌ ERROR: WEBAPP_URL not found in environment variables!")
        return
    
    # Initialize database
    init_db()
    
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Create Telegram Bot Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", play_game))
    application.add_handler(CommandHandler("leaderboard", show_leaderboard))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    logging.info("🤖 Space Jump Bot is starting...")
    logging.info(f"🌐 WebApp URL: {WEBAPP_URL}")
    logging.info(f"🔧 Flask API running on {FLASK_HOST}:{FLASK_PORT}")
    logging.info("✅ Bot is ready! Send /start to your bot in Telegram")
    
    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()