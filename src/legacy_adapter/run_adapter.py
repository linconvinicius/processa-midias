
import subprocess
import os
import sys

def run_legacy_adapter(link_id, image_path, text_path, pub_date, veiculo, canal, cliente):
    """
    Invokes the C# LegacyAdapter.exe with the provided arguments.
    """
    
    # Resolve absolute path to the executable
    base_dir = os.path.dirname(os.path.abspath(__file__))
    adapter_exe = os.path.join(base_dir, "bin", "Debug", "LegacyAdapter.exe")
    
    if not os.path.exists(adapter_exe):
        raise FileNotFoundError(f"LegacyAdapter.exe not found at {adapter_exe}")
        
    # Ensure text file exists
    if not os.path.exists(text_path):
         raise FileNotFoundError(f"Content text file not found at {text_path}")

    # Ensure image file exists
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found at {image_path}")

    cmd = [
        adapter_exe,
        str(link_id),
        image_path,
        text_path,
        pub_date, # yyyy-MM-dd
        str(veiculo),
        str(canal),
        str(cliente)
    ]
    
    print(f"🔄 invoking LegacyAdapter: {' '.join(cmd)}")
    
    try:
        # Run without capture_output to stream directly to stdout/stderr
        result = subprocess.run(cmd, check=True, text=True) 
        print("✅ LegacyAdapter Finished")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ LegacyAdapter Failed (Exit Code {e.returncode})")
        return False
        
if __name__ == "__main__":
    # Test execution
    # 8945290 "captures/instagram_DS2gSufDT4i.png" content.txt 2025-12-29 54108 17847105 130374
    test_link = 8945290
    test_img = "captures/instagram_DS2gSufDT4i.png"
    test_txt = "content.txt"
    run_legacy_adapter(test_link, test_img, test_txt, "2025-12-29", 54108, 17847105, 130374)
