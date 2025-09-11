import sys
import os

def replace_in_file(file_path, search_phrases, replace_phrases):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        modified = False
        for search, replace in zip(search_phrases, replace_phrases):
            if search in content:
                content = content.replace(search, replace)
                print(f"  ✓ Replaced '{search}' with '{replace}'")
                modified = True
        
        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")
        return False

if __name__ == '__main__':
    search_phrases = sys.argv[1].split('|')
    replace_phrases = sys.argv[2].split('|')
    files = sys.argv[3:]
    
    modified_count = 0
    for file in files:
        print(f"\nProcessing: {file}")
        if replace_in_file(file, search_phrases, replace_phrases):
            modified_count += 1
    
    print(f"\n=== Operation Complete ===")
    print(f"Files processed: {len(files)}")
    print(f"Files modified: {modified_count}")
    
    # Always exit with code 0 unless there's an actual error
    if modified_count == 0:
        print("No files needed modification - completing successfully")
    sys.exit(0)
