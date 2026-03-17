import os
from pathlib import Path

# ==========================================
# CONFIGURATION
# ==========================================
OUTPUT_FILE = "master_code.txt"

# Folders we DO NOT want to scan or include in the tree
IGNORE_DIRS = {
    '.git', '__pycache__', '.streamlit', '.venv', 'venv', 'env', 
    'node_modules', '.idea', '.vscode'
}

# Specific files to ignore
IGNORE_FILES = {
    'master.py', OUTPUT_FILE, '.DS_Store', 'secrets.toml'
}

# Only read files with these extensions to avoid binary/image crashes
ALLOWED_EXTENSIONS = {
    '.py', '.txt', '.md', '.yml', '.yaml', '.toml', '.sql', '.json', '.csv'
}

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def generate_tree(startpath):
    """Generates a text-based folder structure tree."""
    tree_str = "📂 REPOSITORY TREE\n"
    tree_str += "========================================\n"
    
    for root, dirs, files in os.walk(startpath):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        # Calculate indentation level
        level = root.replace(startpath, '').count(os.sep)
        indent = '│   ' * level
        
        # Add the directory name
        folder_name = os.path.basename(root)
        if folder_name == '':
            folder_name = "ROOT"
        tree_str += f"{indent}├── 📁 {folder_name}/\n"
        
        # Add the files
        subindent = '│   ' * (level + 1)
        # Filter files to show in tree
        valid_files = [f for f in files if f not in IGNORE_FILES]
        
        for i, f in enumerate(valid_files):
            # Use a corner character for the last file in the list
            pointer = "└── " if i == len(valid_files) - 1 else "├── "
            tree_str += f"{subindent}{pointer}{f}\n"
            
    return tree_str + "\n\n"

def is_valid_file(filename):
    """Checks if the file should be read based on extension and ignore list."""
    if filename in IGNORE_FILES:
        return False
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS

# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    root_dir = os.getcwd()
    print(f"🔍 Scanning repository at: {root_dir}")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
        # 1. Write the directory tree
        print("🌳 Generating directory tree...")
        tree_output = generate_tree(root_dir)
        outfile.write(tree_output)
        
        # 2. Write the code content
        print("📄 Extracting code files...")
        outfile.write("💻 CODEBASE CONTENT\n")
        outfile.write("========================================\n\n")
        
        files_processed = 0
        
        for root, dirs, files in os.walk(root_dir):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in files:
                if is_valid_file(file):
                    file_path = os.path.join(root, file)
                    # Get the relative path for cleaner headers
                    rel_path = os.path.relpath(file_path, root_dir)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as infile:
                            content = infile.read()
                            
                        # Write the AI-friendly delimiter and content
                        outfile.write(f"\n{'='*60}\n")
                        outfile.write(f"📁 FILE: {rel_path}\n")
                        outfile.write(f"{'='*60}\n\n")
                        outfile.write(content)
                        outfile.write("\n\n")
                        
                        files_processed += 1
                        
                    except Exception as e:
                        print(f"⚠️ Could not read {rel_path}: {e}")

    print(f"✅ Success! Compiled {files_processed} files into '{OUTPUT_FILE}'.")

if __name__ == "__main__":
    main()
