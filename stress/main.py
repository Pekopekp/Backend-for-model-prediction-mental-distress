# Without logger directly from coolterm
import subprocess
import os
import sys

from data_logger import get_user_info
from txt_to_csv_converter import convert_and_clean_txt
from preprocessing import preprocess_data
from feature_extraction import extract_features
from prediction import predict_stress
from firebase_upload import upload_result, fetch_user_id

def setup_folders():
    text_dir = '../text file'
    sub_dir = os.getenv('USER_DATA_SUBDIR', '')
    data_dir = os.path.join('data', sub_dir) if sub_dir else 'data'
    folders = [
        os.path.join(data_dir, 'raw'),
        os.path.join(data_dir, 'processed'),
        os.path.join(data_dir, 'predictions'),
        'models',
        'firebase',
        text_dir
    ]
    for folder in folders:
        os.makedirs(folder, exist_ok=True)

if __name__ == "__main__":
    setup_folders()
    
    print("STEP 1 - Subject Information")
    get_user_info()
    
    text_dir = "../text file"
    
    txt_files = [f for f in os.listdir(text_dir) if f.endswith('.txt')]
    if not txt_files:
        print(f"\nError: No .txt files found in '{text_dir}'.")
        print("Please place your raw text file at that location and run the script again.")
        sys.exit(1)
        
    input_file = os.path.join(text_dir, txt_files[0])
        
    if os.path.getsize(input_file) == 0:
        print(f"\nError: The file '{input_file}' is empty. Please provide a file with data.")
        sys.exit(1)
    
    print(f"\nUsing input file: {input_file}")
    
    sub_dir = os.getenv('USER_DATA_SUBDIR', '')
    data_dir = os.path.join('data', sub_dir) if sub_dir else 'data'
    
    print("\nSTEP 2 - Convert TXT to CSV")
    cleaned_csv = os.path.join(data_dir, "cleaned_output.csv")
    convert_and_clean_txt(input_file=input_file, output_file=cleaned_csv)
    
    print("\nSTEP 3 - Preprocess")
    processed_csv_path = os.path.join(data_dir, "processed/processed_data.csv")
    processed_df = preprocess_data(cleaned_csv, output_path=processed_csv_path)
    
    if not processed_df.empty:
        print("\nSTEP 4 - Feature Extraction (with Neurokit2)")
        features_csv_path = os.path.join(data_dir, "processed/features.csv")
        feature_df = extract_features(processed_df, output_path=features_csv_path)
        
        if not feature_df.empty:
            print("\nSTEP 5 - Prediction (with Scaler)")
            predictions_csv_path = os.path.join(data_dir, "predictions/final_predictions.csv")
            result_df = predict_stress(feature_df, output_path=predictions_csv_path)
            
            if not result_df.empty:
                print("Prediction Summary:")
                print(result_df[['Time', 'Stress_Status']].tail())
                
                print("\nSTEP 6 - Upload to Firebase")
                uid = fetch_user_id()
                if uid:
                    print(f"Active session found with UID: {uid}")
                else:
                    print("No active pending session found. Uploading to latest.")
                upload_result(result_df, uid=uid)
                print('\nFULL PIPELINE COMPLETED')
            else:
                print("Prediction failed.")
        else:
            print("Feature extraction failed.")
    else:
        print("Preprocessing failed.")
