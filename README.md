# Image Review System

A FastAPI-based image review system supporting multi-user collaboration.

## Quick Start

### Windows
Double-click `start.bat` or run:
```bash
start.bat
```

### Linux / Mac
```bash
chmod +x start.sh
./start.sh
```

## Features

- Multi-role image review
- Batch image import
- Review statistics
- Auto backup
- Mobile responsive

## Tech Stack

- Backend: FastAPI + SQLite
- Frontend: HTML/CSS/JavaScript
- Database: SQLite

## Project Structure

```
image-review-system/
├── backend/          # Backend code
│   ├── main.py       # Main app
│   ├── database.py   # Database
│   ├── models.py     # Data models
│   ├── services.py   # Business logic
│   └── backup.py     # Backup module
├── frontend/         # Frontend pages
│   ├── index.html   # User page
│   └── admin.html   # Admin page
├── static/          # Static resources
│   ├── css/         # Styles
│   ├── js/          # Scripts
│   └── images/      # Images
├── data/            # Data directory
├── backups/         # Backup directory
├── uploads/         # Upload directory
└── requirements.txt # Python dependencies
```

## Default Port

Access after start: http://localhost:8000

Admin page: http://localhost:8000/admin
