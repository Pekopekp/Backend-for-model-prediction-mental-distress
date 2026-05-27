import os
import sys
import subprocess
import datetime
import json
import pandas as pd
from dotenv import load_dotenv

# Try loading environment variables from anxiety/.env or stress/.env
anxiety_env = os.path.join('anxiety', '.env')
stress_env = os.path.join('stress', '.env')
if os.path.exists(anxiety_env):
    load_dotenv(anxiety_env)
elif os.path.exists(stress_env):
    load_dotenv(stress_env)
else:
    load_dotenv()

# Initialize Firebase from root
import firebase_admin
from firebase_admin import credentials, db

# Resolve firebase key path
key_path = os.getenv('FIREBASE_KEY_PATH', 'firebase/firebase_key.json')
resolved_key_path = None
for prefix in ['', 'anxiety', 'stress']:
    test_path = os.path.join(prefix, key_path) if prefix else key_path
    if os.path.exists(test_path):
        resolved_key_path = test_path
        break

if not resolved_key_path:
    print(f"Error: Firebase credential key not found at '{key_path}' in root or subdirectories.")
    sys.exit(1)

DATABASE_URL = os.getenv('FIREBASE_DATABASE_URL', '')
if not DATABASE_URL:
    print("Error: FIREBASE_DATABASE_URL is not set in environment variables.")
    sys.exit(1)

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(resolved_key_path)
        firebase_admin.initialize_app(cred, {
            'databaseURL': DATABASE_URL
        })
        print(f"Firebase Admin initialized successfully using key: {resolved_key_path}")
    except Exception as e:
        print(f"Error: Firebase initialization failed. \nError: {e}")
        sys.exit(1)


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
        print(f"Failed to fetch user ID from Firebase: {e}")
        return None


MAPPING_FILE = 'user_mapping.json'

def get_or_create_user_dir(uid):
    test_uid = uid if uid else 'default_session'
    mapping = {}
    if os.path.exists(MAPPING_FILE):
        try:
            with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load user mapping file: {e}")
            mapping = {}
            
    if test_uid in mapping:
        return mapping[test_uid]
        
    # Find next S<number>
    existing_dirs = list(mapping.values())
    max_num = 0
    for d in existing_dirs:
        if d.startswith('S') and d[1:].isdigit():
            max_num = max(max_num, int(d[1:]))
            
    next_dir = f"S{max_num + 1}"
    mapping[test_uid] = next_dir
    
    try:
        with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2)
        print(f"Mapped user ID '{test_uid}' to dynamic folder '{next_dir}'.")
    except Exception as e:
        print(f"Error saving user mapping file: {e}")
        
    return next_dir


def fetch_user_details(uid):
    # Try fetching from active_session first
    try:
        ref = db.reference(f'active_session/{uid}')
        data = ref.get()
        if data:
            name = data.get('name') or data.get('User_Name') or data.get('userName') or data.get('displayName')
            age = data.get('age') or data.get('Age')
            gender = data.get('gender') or data.get('Gender')
            if name or age or gender:
                return name, age, gender
    except Exception as e:
        print(f"Failed to fetch user details from active_session: {e}")

    # Try fetching from users/{uid}
    try:
        ref = db.reference(f'users/{uid}')
        data = ref.get()
        if data:
            name = data.get('name') or data.get('User_Name') or data.get('userName') or data.get('displayName')
            age = data.get('age') or data.get('Age')
            gender = data.get('gender') or data.get('Gender')
            return name, age, gender
    except Exception as e:
        print(f"Failed to fetch user details from users node: {e}")

    return None, None, None


def safe_int_label(val):
    if val is None or pd.isna(val):
        return 'Unknown'
    try:
        return int(val)
    except Exception:
        return val


def main():
    print("\n==============================================")
    print("      MindCare Unified Pipeline Coordinator   ")
    print("==============================================\n")
    
    # 1. Check for input files
    text_dir = 'text file'
    os.makedirs(text_dir, exist_ok=True)
    txt_files = [f for f in os.listdir(text_dir) if f.endswith('.txt')]
    if not txt_files:
        print(f"Error: No .txt files found in '{text_dir}' directory.")
        print("Please place your raw physiological data file (.txt) there and run again.")
        sys.exit(1)
        
    input_file = os.path.join(text_dir, txt_files[0])
    print(f"Found input file: {input_file}")

    # 2. Get user metadata from Firebase
    uid = fetch_user_id()
    name, age, gender = None, None, None
    if uid:
        print(f"Active pending session found in Firebase with UID: {uid}")
        name, age, gender = fetch_user_details(uid)
    else:
        print("No active pending session found in Firebase. (Using defaults)")

    # Apply defaults if missing
    if not name:
        name = "Firebase User"
    if not age:
        age = "Unknown"
    if not gender:
        gender = "Unknown"

    print(f"Loaded User Profile:")
    print(f"  Name:   {name}")
    print(f"  Age:    {age}")
    print(f"  Gender: {gender}\n")
    
    # Map UID to subject folder and timestamp run folder
    user_dir = get_or_create_user_dir(uid)
    run_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    user_data_subdir = f"{user_dir}/{run_time}"
    
    print(f"Assigning dynamic storage subdirectory: data/{user_data_subdir}\n")
    
    # Write user info to respective directories to satisfy any localized reading
    os.makedirs(f'anxiety/data/{user_data_subdir}', exist_ok=True)
    os.makedirs(f'stress/data/{user_data_subdir}', exist_ok=True)
    for user_info_file in [f'anxiety/data/{user_data_subdir}/user_info.txt', f'stress/data/{user_data_subdir}/user_info.txt']:
        with open(user_info_file, 'w', encoding='utf-8') as f:
            f.write(f"Name: {name}\n")
            f.write(f"Age: {age}\n")
            f.write(f"Gender: {gender}\n")

    # 3. Setup subprocess environment
    sub_env = os.environ.copy()
    sub_env['SKIP_FIREBASE_UPLOAD'] = 'True'
    sub_env['USER_DATA_SUBDIR'] = user_data_subdir
    
    stdin_input = f"{name}\n{age}\n{gender}\n"

    # 4. Run Anxiety Pipeline
    print("\n----------------------------------------------")
    print(" Running Anxiety Detection Pipeline... ")
    print("----------------------------------------------")
    
    try:
        res_anx = subprocess.run(
            [sys.executable, 'main.py'],
            cwd='anxiety',
            input=stdin_input,
            text=True,
            capture_output=True,
            env=sub_env,
            check=True
        )
        print(res_anx.stdout)
    except subprocess.CalledProcessError as e:
        print("Anxiety Pipeline failed with error:")
        print(e.stdout)
        print(e.stderr)
        sys.exit(1)

    # 5. Run Stress Pipeline
    print("\n----------------------------------------------")
    print(" Running Stress Detection Pipeline... ")
    print("----------------------------------------------")
    
    try:
        res_str = subprocess.run(
            [sys.executable, 'main.py'],
            cwd='stress',
            input=stdin_input,
            text=True,
            capture_output=True,
            env=sub_env,
            check=True
        )
        print(res_str.stdout)
    except subprocess.CalledProcessError as e:
        print("Stress Pipeline failed with error:")
        print(e.stdout)
        print(e.stderr)
        sys.exit(1)

    # 6. Parse predictions
    anxiety_csv = f'anxiety/data/{user_data_subdir}/predictions/final_predictions.csv'
    stress_csv = f'stress/data/{user_data_subdir}/predictions/final_predictions.csv'
    
    anxiety_status = 'Unknown'
    anxiety_label = 'Unknown'
    stress_status = 'Unknown'
    stress_label = 'Unknown'

    if os.path.exists(anxiety_csv):
        try:
            df_anx = pd.read_csv(anxiety_csv)
            if not df_anx.empty:
                latest_anx = df_anx.iloc[-1].to_dict()
                anxiety_status = latest_anx.get('Anxiety_Status', 'Unknown')
                anxiety_label = safe_int_label(latest_anx.get('Predicted_Label', 'Unknown'))
        except Exception as e:
            print(f"Warning: Could not parse anxiety predictions from CSV: {e}")
            
    if os.path.exists(stress_csv):
        try:
            df_str = pd.read_csv(stress_csv)
            if not df_str.empty:
                latest_str = df_str.iloc[-1].to_dict()
                stress_status = latest_str.get('Stress_Status', 'Unknown')
                stress_label = safe_int_label(latest_str.get('Predicted_Label', 'Unknown'))
        except Exception as e:
            print(f"Warning: Could not parse stress predictions from CSV: {e}")

    # 7. Consolidate results
    combined_payload = {
        'User_Name': name,
        'Age': age,
        'Gender': gender,
        'Anxiety_Status': anxiety_status,
        'Anxiety_Predicted_Label': anxiety_label,
        'Stress_Status': stress_status,
        'Stress_Predicted_Label': stress_label,
        'Timestamp': datetime.datetime.now().isoformat()
    }
    
    print("\n==============================================")
    print("              Consolidated Results            ")
    print("==============================================")
    print(f"User Name               : {name}")
    print(f"Age                     : {age}")
    print(f"Gender                  : {gender}")
    print(f"Anxiety Status / Label  : {anxiety_status} ({anxiety_label})")
    print(f"Stress Status / Label   : {stress_status} ({stress_label})")
    print("==============================================\n")

    # 8. Upload to Firebase
    print("Uploading consolidated results to Firebase...")
    try:
        if uid:
            # Upload to combined node
            db.reference(f'combined_monitoring/{uid}').set(combined_payload)
            
            # Mark session as done
            db.reference(f'active_session/{uid}').update({'status': 'done'})
            print(f"Successfully uploaded combined session results for UID: {uid}!")
        else:
            db.reference('combined_monitoring/latest').set(combined_payload)
            print("Successfully uploaded latest results to Firebase!")
            
        print("\nUNIFIED PIPELINE COORDINATION SUCCESSFULLY COMPLETED!")
    except Exception as e:
        print(f"Failed to upload combined results to Firebase: {e}")


if __name__ == "__main__":
    main()
