import webview
import subprocess
import os

class Api:
    def launch_call_assistant(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        app_path = os.path.abspath(os.path.join(current_dir, '..', 'emergency-calling', 'app.py'))
        
        try:
            if os.path.exists(app_path):
                # Using 'python' to execute the script at that path
                subprocess.Popen(["python", app_path])
                print(f"Launched: {app_path}")
            else:
                print(f"Error: File not found at {app_path}")
        except Exception as e:
            print(f"System Error: {e}")

def start_app():
    api = Api()
    # Opens your GazeType UI in a dedicated desktop window
    window = webview.create_window(
        'GazeType — Assistive Keyboard', 
        'index.html', 
        js_api=api,
        maximized=True,
        background_color='#0d1117'
    )
    webview.start()

if __name__ == '__main__':
    start_app()