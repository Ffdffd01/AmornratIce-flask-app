# Amornrat Ice Company - Flask Application

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Git

### Installation

1. Clone the repository:
```bash
git clone https://github.com/Ffdffd01/AmornratIce-flask-app.git
cd AmornratIce-flask-app
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Firebase Setup

1. Create a Firebase project at [Firebase Console](https://console.firebase.google.com/)
2. Generate a new private key:
   - Go to Project Settings > Service Accounts
   - Click "Generate New Private Key"
   - Save the JSON file as `firebase/amornratice-43410-firebase-adminsdk-fbsvc-765820c7a6.json`

### Environment Setup

1. Create a `.env` file in the root directory with the following content:
```
# Firebase Configuration
FIREBASE_CREDENTIALS_PATH=firebase/amornratice-43410-firebase-adminsdk-fbsvc-765820c7a6.json

# Flask Configuration
FLASK_SECRET_KEY=your-secret-key-here
FLASK_ENV=development
FLASK_DEBUG=1
```

2. Generate a secure secret key:
```bash
python -c 'import secrets; print(secrets.token_hex(32))'
```
Copy the output and replace `your-secret-key-here` in the `.env` file.

### Running the Application

1. Start the Flask development server:
```bash
flask run
```

2. Access the application at `http://localhost:5000`

## Security Notes

- Never commit the `.env` file or Firebase credentials to version control
- Keep your Firebase credentials secure and don't share them publicly
- Regularly rotate your Firebase service account keys
- Use environment variables for all sensitive configuration

## Contributing

1. Create a new branch for your feature
2. Make your changes
3. Submit a pull request

## License

This project is proprietary and confidential. Unauthorized copying, distribution, or use is strictly prohibited. 