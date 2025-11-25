# Changelog

## [2.0.0] - 2025-11-25

### 🎉 Major Features
- **Complete project restructuring** with new modular architecture
- **Message queue system** for crash recovery (JSON-based persistence)
- **Debug mode** (`/debug` command) with dedicated debug.log file
- **Restart confirmation** - admin only notified when `/restart` was used
- **Improved error logging** with detailed error reasons during startup

### 🏗️ Architecture Improvements
- **New `core/` module** with reusable business logic:
  - `AccessManager` - unified access control and permission checking
  - `MediaSender` - unified media handling (video, audio, photo)
  - `MessageQueueManager` - message persistence and crash recovery
- **Service reorganization** - all services renamed to `*_service.py` pattern:
  - `logger_service.py` - logging and Discord webhooks
  - `cache_service.py` - runtime content caching
  - `database_service.py` - database operations
- **Handler restructuring** - all handlers renamed to `*_handler.py`:
  - `message_handler.py` - user message and link processing
  - `admin_handler.py` - admin commands and management
  - `inline_handler.py` - inline query handling

### ✨ New Commands
- `/debug` - Toggle debug mode on/off (admin only)
  - Enables full console logging
  - Creates `debug.log` file in `logs/files/`
  - Useful for troubleshooting issues

### 🐛 Bug Fixes
- Fixed `/restart` command - now uses proper system exit with code handling
- Removed unused `/check` and `/get_placeholder` commands
- Improved downloads folder cleanup on startup with better error handling
- Fixed queue logging - messages only queued, not logged on every send

### 📊 Code Quality
- **Eliminated code duplication** - 70+ lines of duplicate media sending code consolidated
- **Centralized access control** - permission checks unified across handlers
- **Better error messages** - startup errors now show actual exception messages

### 📋 Updated Menu
- `/menu` command now shows all available commands with descriptions
- Admin menu includes new `/debug` option

### 📦 System Information
- Added `VERSION` file for version tracking
- `/status` command now displays current version
- Created `CHANGELOG.md` for release notes

### 🔒 Under the Hood
- Settings now include `DEBUG` flag for mode toggling
- Restart detection via `.restart_flag` file
- Improved startup logging with specific error reasons
