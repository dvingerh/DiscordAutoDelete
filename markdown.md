# AutoDelete Bot README

## Overview
AutoDelete Bot is a Discord bot designed to manage and automate message deletion tasks in Discord servers. It offers simple but powerful control over which messages are deleted.

The bot uses a rolling log system. When the channel exceeds a set message limit the oldest message that exceeded the limit will be deleted. Messages are not purged in bulk to minimize disruption. You can customize it to exclude pinned messages or and bot embeds from being deleted.

## Features
- **Automatic Message Deletion**: Configure channels to automatically delete messages exceeding a specified limit.
- **Customizable Rules**: Control whether pinned messages or bot embeds are deleted.
- **Management Roles**: Restrict bot management commands to designated roles.
- **Statistics Tracking**: View statistics for deleted messages across channels.
- **Restart and Configuration Persistence**: Seamlessly restart the bot without losing configuration.

## Requirements
- Python 3.8+
- Discord Bot Token
- Required Python packages (install with `pip install -r requirements.txt`):
  - `discord.py`
  - `python-dotenv`
  - `asyncio`

## Setup
1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd <repository-folder>
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file with the following:
   ```
   DISCORD_TOKEN=your_discord_bot_token
   BOT_STATUS=AutoDelete Bot
   ```

4. **Run the Bot**:
   ```bash
   python autodelete.py
   ```

## Commands
### **General Commands**
- **`/autodelete add`**
  Add a new auto-delete task for a specific channel.
  - Parameters:
    - `channel`: Target channel.
    - `limit`: Maximum number of messages allowed.
    - `pins`: Delete pinned messages (`True`/`False`).
    - `embeds`: Delete bot embeds (`True`/`False`).
    - `enabled`: Enable or disable the task (`True`/`False`).

- **`/autodelete remove`**
  Remove an auto-delete task from a channel.

- **`/autodelete list`**
  List all existing tasks with their configurations.

- **`/autodelete edit`**
  Edit an existing task.

- **`/autodelete stats`**
  View statistics of deleted messages across channels.

### **Management Commands**
- **`/autodelete setup`**
  Assign roles authorized to manage the bot.
  
- **`/autodelete restart`**
  Restart the bot with configuration persistence.

- **`/autodelete disable`**
  Bulk disable all tasks in the current server.

- **`/autodelete enable`**
  Bulk enable all tasks in the current server.

- **`/autodelete purge`**
  Purge all tasks for the server (requires confirmation).

- **`/autodelete help`**
  View a list of all commands.

## File Structure
- `autodelete.py`: Main bot script.
- `autodelete_config.json`: Persistent configuration file for tasks and statistics.
- `.env`: Environment variable configuration file.

## Additional Notes
- Ensure the bot has the following Discord permissions:
  - Manage Messages
  - View Channels
  - Send Messages
  - Read Message History

## License
This project is open-source and available under the [MIT License](LICENSE).