import firebase_admin
from firebase_admin import credentials, db
import os
from dotenv import load_dotenv

load_dotenv()

FIREBASE_KEY_PATH = os.getenv('FIREBASE_KEY_PATH', 'firebase/firebase_key.json')
DATABASE_URL = os.getenv('FIREBASE_DATABASE_URL', '')

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred, {
            'databaseURL': DATABASE_URL
        })
    except Exception as e:
        print(f"Warning: Firebase initialization failed. Please ensure '{FIREBASE_KEY_PATH}' exists.\nError: {e}")

def fetch_user_id():
    try:
        ref = db.reference('active_session')
        sessions = ref.get()
        if sessions:
            pending_sessions = {k: v for k, v in sessions.items() if v.get('status') == 'pending'}
            if pending_sessions:
                sorted_sessions = sorted(pending_sessions.items(), key=lambda x: x[1].get('timestamp', ''))
                return sorted_sessions[0][0]
        return None
    except Exception as e:
        print(f"Failed to fetch user ID: {e}")
        return None

def get_user_name():
    try:
        with open('data/user_info.txt', 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("Name:"):
                    return line.split("Name:")[1].strip()
    except Exception:
        pass
    return "Unknown User"

def upload_result(result_df, uid=None):
    if os.getenv('SKIP_FIREBASE_UPLOAD') == 'True':
        print("Skipping individual Firebase upload as requested by coordinator.")
        return

    if result_df.empty:
        print("No predictions to upload.")
        return
        
    try:
        # We upload the most recent window result to match the Colab logic
        latest_data = result_df.iloc[-1].to_dict()
        
        filtered_data = {
            'User_Name': get_user_name(),
            'Stress_Status': latest_data.get('Stress_Status'),
            'Predicted_Label': latest_data.get('Predicted_Label')
        }
        
        if uid:
            ref = db.reference(f'stress_monitoring/{uid}')
            ref.set(filtered_data)
            db.reference(f'active_session/{uid}').update({'status': 'done'})
            print(f'Successfully uploaded prediction for {filtered_data["User_Name"]} to stress_monitoring/{uid}!')
        else:
            ref = db.reference('stress_monitoring/latest')
            ref.set(filtered_data)
            print(f'Successfully uploaded latest prediction for {filtered_data["User_Name"]} to Firebase!')
    except Exception as e:
        print(f"Failed to upload to Firebase: {e}")
