#!/usr/bin/env python
"""
Script to verify that all PDF and image processing dependencies are correctly installed.
"""

import sys

def check_dependency(module_name, package_name=None):
    package_name = package_name or module_name
    try:
        __import__(module_name)
        print(f"✓ {package_name} is installed")
        return True
    except ImportError:
        print(f"✗ {package_name} is NOT installed")
        return False
    
def check_binary(binary_name):
    import subprocess
    try:
        subprocess.run([binary_name, "--version"], 
                     stdout=subprocess.PIPE, 
                     stderr=subprocess.PIPE, 
                     check=True)
        print(f"✓ {binary_name} binary is available")
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        print(f"✗ {binary_name} binary is NOT available")
        return False

def main():
    success = True
    
    # Check Python modules
    modules = [
        ("fitz", "PyMuPDF"),
        ("pdf2image", "pdf2image"),
        ("pytesseract", "pytesseract"),
        ("PIL", "Pillow"),
        ("cv2", "opencv-python"),
        ("numpy", "numpy"),
        ("pyzbar", "pyzbar"),
    ]
    
    for module, package in modules:
        if not check_dependency(module, package):
            success = False
    
    # Check binaries
    binaries = ["tesseract", "pdftoppm", "pdfinfo"]
    for binary in binaries:
        if not check_binary(binary):
            success = False
    
    # Check tesseract version and languages
    import subprocess
    try:
        result = subprocess.run(["tesseract", "--list-langs"], 
                           stdout=subprocess.PIPE, 
                           stderr=subprocess.PIPE, 
                           text=True)
        print("Available Tesseract languages:")
        for line in result.stderr.splitlines()[1:]:  # Skip the header line
            print(f"  - {line}")
    except subprocess.SubprocessError:
        print("Could not list Tesseract languages")
        success = False
        
    # Final result
    if success:
        print("\n✓ All PDF processing dependencies are installed correctly")
        return 0
    else:
        print("\n✗ Some PDF processing dependencies are missing")
        return 1

if __name__ == "__main__":
    sys.exit(main())