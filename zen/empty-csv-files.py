import os

def empty_csv_files(directory):
    # List all files in the specified directory that start with 'zen-' and end with '.csv'
    files = [f for f in os.listdir(directory) if f.startswith('zen-') and f.endswith('.csv')]

    if not files:
        print("No files found starting with 'zen-' in the specified directory.")
        return

    print(f"Found {len(files)} file(s) to empty: {files}")

    for file in files:
        file_path = os.path.join(directory, file)
        try:
            # Open the file in write mode and immediately close it to empty its contents
            with open(file_path, 'w') as f:
                pass  # Do nothing, just empty the file
            print(f"Emptied file: {file_path}")
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")

# Specify the directory containing the files
directory_path = './zen'

# Run the emptying function
empty_csv_files(directory_path)