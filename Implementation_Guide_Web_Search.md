# Telegram News Agent - Implementation Guide (Web Search Approach)

## 🚀 Quick Implementation Plan

Build a working news bot in **5 days** using Claude's web search. No news fetchers needed!

---

## Architecture Overview

```
Telegram Bot → Claude (with web_search) → User
                   ↑
              Scheduler (triggers daily)
```

**That's it!** Claude does all the heavy lifting:
- Searches web for news
- Filters by user interests  
- Summarizes articles
- Provides source links

---

## Day-by-Day Build Plan

### Day 1: Setup & Database (2-3 hours)

**Create project structure:**
```bash
telegram-news-agent/
├── config/
│   ├── settings.py
│   └── prompts.py
├── src/
│   ├── ai/
│   │   └── claude_client.py
│   ├── bot/
│   │   └── telegram_bot.py
│   ├── database/
│   │   ├── models.py
│   │   └── db_manager.py
│   ├── user/
│   │   └── profile_manager.py
│   └── scheduler/
│       └── news_scheduler.py
├── scripts/
│   ├── setup_db.py
│   └── run_bot.py
├── requirements.txt
└── .env
```

**1.1 Install dependencies:**
```bash
pip install python-telegram-bot anthropic apscheduler python-dotenv sqlalchemy pydantic
```

**1.2 Create `.env`:**
```bash
TELEGRAM_BOT_TOKEN=your_token_from_botfather
ANTHROPIC_API_KEY=your_claude_key
DATABASE_URL=sqlite:///news_agent.db
```

**1.3 Create `config/settings.py`:**
```python
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///news_agent.db")
    CLAUDE_MODEL = "claude-sonnet-4-20250514"
    DEFAULT_DELIVERY_TIME = "08:00"

settings = Settings()
```

**1.4 Create `src/database/models.py`:**
```python
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    user_id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    delivery_time = Column(String, default='08:00')

class UserInterest(Base):
    __tablename__ = 'user_interests'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id'))
    interest = Column(String, nullable=False)
    weight = Column(Float, default=1.0)
```

**1.5 Create `scripts/setup_db.py`:**
```python
from src.database.models import Base
from sqlalchemy import create_engine
from config.settings import settings

engine = create_engine(settings.DATABASE_URL)
Base.metadata.create_all(engine)
print("Database initialized!")
```

**Test:** Run `python scripts/setup_db.py` - should create `news_agent.db`

---

### Day 2: Claude Integration (3-4 hours)

**2.1 Create `config/prompts.py`:**
```python
DAILY_DIGEST_PROMPT = """You are an expert news curator.

User's interests: {interests}

For each interest, search the web for the most important news from the last 24 hours.
Find 1-2 significant stories per interest (total: 5-7 stories).

Format each story:
📰 **[Topic]**: [2-3 sentence summary]
📎 Source: [Publication] - [URL]

Be concise and objective."""

FOLLOW_UP_PROMPT = """User asked: {question}

Search the web and provide a detailed answer with sources."""
```

**2.2 Create `src/ai/claude_client.py`:**
```python
from anthropic import Anthropic
from config.settings import settings
from config.prompts import DAILY_DIGEST_PROMPT, FOLLOW_UP_PROMPT
import logging

logger = logging.getLogger(__name__)

class ClaudeClient:
    def __init__(self):
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.CLAUDE_MODEL
        self.web_search_tool = {"type": "web_search_20250305", "name": "web_search"}
    
    async def generate_digest(self, user_interests):
        """Generate news digest using web search"""
        try:
            interests_str = ", ".join(user_interests)
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=3000,
                tools=[self.web_search_tool],
                messages=[{
                    "role": "user",
                    "content": DAILY_DIGEST_PROMPT.format(interests=interests_str)
                }]
            )
            
            digest = self._extract_text(response)
            logger.info(f"Generated digest for: {interests_str}")
            return digest
            
        except Exception as e:
            logger.error(f"Error generating digest: {e}")
            return "Sorry, couldn't generate digest. Please try again."
    
    async def answer_question(self, question):
        """Answer questions with web search"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                tools=[self.web_search_tool],
                messages=[{
                    "role": "user",
                    "content": FOLLOW_UP_PROMPT.format(question=question)
                }]
            )
            
            return self._extract_text(response)
            
        except Exception as e:
            logger.error(f"Error answering: {e}")
            return "Sorry, couldn't find an answer."
    
    def _extract_text(self, response):
        """Extract text from Claude response"""
        return "\n".join([block.text for block in response.content if block.type == "text"])

claude_client = ClaudeClient()
```

**Test:**
```python
# test_claude.py
import asyncio
from src.ai.claude_client import claude_client

async def test():
    digest = await claude_client.generate_digest(["AI", "climate tech"])
    print(digest)

asyncio.run(test())
```

---

### Day 3: Telegram Bot (4-5 hours)

**3.1 Create `src/user/profile_manager.py`:**
```python
from src.database.models import User, UserInterest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config.settings import settings

class ProfileManager:
    def __init__(self):
        engine = create_engine(settings.DATABASE_URL)
        self.Session = sessionmaker(bind=engine)
    
    def get_or_create_user(self, telegram_id, username=None):
        """Get user or create if doesn't exist"""
        session = self.Session()
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if not user:
            user = User(telegram_id=telegram_id, username=username)
            session.add(user)
            session.commit()
        
        user_id = user.user_id
        session.close()
        return user_id
    
    def add_interests(self, user_id, interests):
        """Add interests for user"""
        session = self.Session()
        
        # Clear existing
        session.query(UserInterest).filter_by(user_id=user_id).delete()
        
        # Add new
        for interest in interests:
            session.add(UserInterest(user_id=user_id, interest=interest.strip()))
        
        session.commit()
        session.close()
    
    def get_interests(self, user_id):
        """Get user's interests"""
        session = self.Session()
        interests = session.query(UserInterest).filter_by(user_id=user_id).all()
        result = [i.interest for i in interests]
        session.close()
        return result

profile_manager = ProfileManager()
```

**3.2 Create `src/bot/telegram_bot.py`:**
```python
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from src.ai.claude_client import claude_client
from src.user.profile_manager import profile_manager
from config.settings import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "👋 Welcome! I'm your AI news assistant.\n\n"
        "Tell me what topics interest you (e.g., 'AI, climate tech, NBA')"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text(
        "Commands:\n"
        "/start - Set up your interests\n"
        "/help - Show this message\n\n"
        "Just send me a message to ask questions about news!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages"""
    user_message = update.message.text
    telegram_id = update.effective_user.id
    username = update.effective_user.username
    
    # Get or create user
    user_id = profile_manager.get_or_create_user(telegram_id, username)
    
    # Check if this is setting interests (looks like comma-separated list)
    if ',' in user_message and len(user_message) < 200:
        # Assume this is interests
        interests = [i.strip() for i in user_message.split(',')]
        profile_manager.add_interests(user_id, interests)
        
        await update.message.reply_text(
            f"✅ Got it! I'll curate news about: {', '.join(interests)}\n\n"
            "Generating your first digest now..."
        )
        
        # Generate first digest
        digest = await claude_client.generate_digest(interests)
        await update.message.reply_text(f"📰 **News Digest**\n\n{digest}")
    
    else:
        # This is a question
        answer = await claude_client.answer_question(user_message)
        await update.message.reply_text(answer)

def main():
    """Run the bot"""
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
```

**3.3 Create `scripts/run_bot.py`:**
```python
from src.bot.telegram_bot import main

if __name__ == "__main__":
    main()
```

**Test:** 
```bash
python scripts/run_bot.py
# Open Telegram, find your bot, send /start
```

---

### Day 4: Scheduler (2-3 hours)

**4.1 Create `src/scheduler/news_scheduler.py`:**
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.ai.claude_client import claude_client
from src.user.profile_manager import profile_manager
from src.database.models import User, UserInterest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

class NewsScheduler:
    def __init__(self, bot):
        self.scheduler = AsyncIOScheduler()
        self.bot = bot
        engine = create_engine(settings.DATABASE_URL)
        self.Session = sessionmaker(bind=engine)
    
    async def send_daily_digest(self, user_id, telegram_id, interests):
        """Generate and send daily digest"""
        try:
            digest = await claude_client.generate_digest(interests)
            
            message = f"📰 **Your Daily News Digest**\n\n{digest}\n\n"
            message += "💬 Questions? Just ask!"
            
            await self.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Sent digest to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending digest: {e}")
    
    def schedule_user_digest(self, user_id, telegram_id, interests, delivery_time):
        """Schedule daily digest"""
        hour, minute = map(int, delivery_time.split(':'))
        
        self.scheduler.add_job(
            self.send_daily_digest,
            'cron',
            hour=hour,
            minute=minute,
            args=[user_id, telegram_id, interests],
            id=f'digest_{user_id}',
            replace_existing=True
        )
        
        logger.info(f"Scheduled digest for user {user_id} at {delivery_time}")
    
    def load_all_users(self):
        """Load all users and schedule their digests"""
        session = self.Session()
        
        users = session.query(User).all()
        
        for user in users:
            interests = [i.interest for i in 
                        session.query(UserInterest).filter_by(user_id=user.user_id).all()]
            
            if interests:
                self.schedule_user_digest(
                    user.user_id,
                    user.telegram_id,
                    interests,
                    user.delivery_time
                )
        
        session.close()
        logger.info(f"Loaded {len(users)} users")
    
    def start(self):
        """Start scheduler"""
        self.load_all_users()
        self.scheduler.start()
        logger.info("Scheduler started")

# Global instance (will be initialized with bot)
news_scheduler = None
```

**4.2 Update `src/bot/telegram_bot.py`:**
```python
# Add at top:
from src.scheduler.news_scheduler import NewsScheduler

# Modify main() function:
def main():
    """Run the bot"""
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Initialize and start scheduler
    scheduler = NewsScheduler(app.bot)
    scheduler.start()
    
    logger.info("Bot and scheduler starting...")
    app.run_polling()
```

**Test:**
```bash
# Set delivery time to 1 minute from now for testing
# Then run bot and wait
python scripts/run_bot.py
```

---

### Day 5: Deploy & Test (2-3 hours)

**5.1 DigitalOcean Deployment:**
```bash
# On your droplet:
git clone your-repo
cd telegram-news-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env with your keys
nano .env

# Initialize database
python scripts/setup_db.py

# Run with systemd
sudo nano /etc/systemd/system/news-agent.service
```

**systemd service:**
```ini
[Unit]
Description=Telegram News Agent
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/telegram-news-agent
Environment="PATH=/root/telegram-news-agent/venv/bin"
ExecStart=/root/telegram-news-agent/venv/bin/python scripts/run_bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl start news-agent
sudo systemctl enable news-agent
sudo journalctl -u news-agent -f
```

**5.2 Test Everything:**
- ✅ Send `/start` to bot
- ✅ Set your interests  
- ✅ Get first digest immediately
- ✅ Ask a follow-up question
- ✅ Wait for scheduled digest tomorrow

---

## Complete File Tree

```
telegram-news-agent/
├── config/
│   ├── __init__.py
│   ├── settings.py          ✅ API keys, config
│   └── prompts.py            ✅ AI prompts
├── src/
│   ├── __init__.py
│   ├── ai/
│   │   ├── __init__.py
│   │   └── claude_client.py  ✅ Claude with web_search
│   ├── bot/
│   │   ├── __init__.py
│   │   └── telegram_bot.py   ✅ Main bot logic
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py         ✅ User, UserInterest
│   │   └── db_manager.py
│   ├── user/
│   │   ├── __init__.py
│   │   └── profile_manager.py ✅ User management
│   └── scheduler/
│       ├── __init__.py
│       └── news_scheduler.py  ✅ Daily digests
├── scripts/
│   ├── setup_db.py           ✅ Initialize DB
│   └── run_bot.py            ✅ Entry point
├── requirements.txt          ✅ 7 packages
├── .env                      ✅ Your API keys
├── .gitignore
└── README.md
```

---

## What We DON'T Build

❌ News fetcher  
❌ RSS parser  
❌ Article aggregator  
❌ Deduplication logic  
❌ Article cache  
❌ NewsAPI integration  
❌ Multi-source management  

**Claude does all of this automatically with web_search!**

---

## Cost Breakdown

**Per User Per Month:**
- Claude API: $0.75
- Server (DigitalOcean): $6
- **Total: $6.75**

Or use Raspberry Pi: **$0.75/month** 🎉

---

## Testing Checklist

**Day 1:**
- ✅ Database created
- ✅ Can connect to DB

**Day 2:**
- ✅ Claude returns news digest
- ✅ Sources are cited

**Day 3:**
- ✅ Bot responds to /start
- ✅ Can set interests
- ✅ Gets immediate digest

**Day 4:**
- ✅ Scheduler runs
- ✅ Digest delivered on time

**Day 5:**
- ✅ Bot runs on server
- ✅ Survives restarts
- ✅ Logs working

---

## Troubleshooting

**Bot not responding:**
```bash
# Check if running
ps aux | grep run_bot

# Check logs
tail -f logs/bot.log

# Verify token
curl https://api.telegram.org/bot<TOKEN>/getMe
```

**No digest generated:**
```bash
# Test Claude API
python test_claude.py

# Check API key
echo $ANTHROPIC_API_KEY
```

**Scheduler not working:**
```bash
# Check scheduler logs
grep "scheduler" logs/bot.log

# Verify user in database
sqlite3 news_agent.db "SELECT * FROM users;"
```

---

## Next Steps (Week 2)

**Add voice features:**
1. Install: `pip install openai`
2. Add `OPENAI_API_KEY` to .env
3. Create `src/voice/speech_to_text.py`
4. Create `src/voice/text_to_speech.py`
5. Add voice handlers to bot

**Add feedback:**
1. Add 👍👎 buttons with InlineKeyboard
2. Update interest weights based on reactions
3. Improve relevance over time

---

## Summary

**You just built a personalized AI news agent in 5 days!**

- **Lines of code**: ~300
- **APIs used**: 1 (Claude)
- **Monthly cost**: $7-8
- **Maintenance**: Minimal

**Key insight**: Modern AI + web search makes traditional news fetching obsolete.

**Now enjoy your personalized news every morning!** 📰☕
