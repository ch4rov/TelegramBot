import os

def list_files(startpath):
    # Папки, которые мы НЕ хотим видеть в отчете
    IGNORED = {'venv', '__pycache__', '.git', '.idea', '.vscode', 'downloadAndRemove', 'downloads'}

    print(f"📂 Структура проекта: {os.path.abspath(startpath)}")
    
    for root, dirs, files in os.walk(startpath):
        # Фильтрация папок на лету
        dirs[:] = [d for d in dirs if d not in IGNORED]
        
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f"{indent}📁 {os.path.basename(root)}/")
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print(f"{subindent}📄 {f}")

if __name__ == "__main__":
    list_files('.')