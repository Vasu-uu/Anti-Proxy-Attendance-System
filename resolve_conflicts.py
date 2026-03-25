import sys

def resolve_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    resolved_lines = []
    in_head = False
    in_new = False
    
    for line in lines:
        if line.startswith('<<<<<<< HEAD'):
            in_head = True
            continue
        elif line.startswith('======='):
            in_head = False
            in_new = True
            continue
        elif line.startswith('>>>>>>> 9ed820ca'):
            in_new = False
            continue
            
        if in_head:
            pass  # Skip HEAD lines
        else:
            resolved_lines.append(line)
            
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(resolved_lines)
    
    print(f"Resolved {filepath}")

if __name__ == '__main__':
    for file in sys.argv[1:]:
        resolve_file(file)
