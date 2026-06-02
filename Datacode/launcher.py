import tkinter as tk
from tkinter import ttk
import subprocess
import sys
import os
import time

# 获取当前脚本所在的目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # 获取打包后的临时路径
    except Exception:
        base_path = BASE_DIR  # 开发环境下获取当前目录路径
    return os.path.join(base_path, relative_path)

# 启动主程序
def start_main_program():
    main_program_path = resource_path('Datacode/DataStorage.py')
    try:
        # 启动主程序脚本
        subprocess.Popen([sys.executable, main_program_path])
    except Exception as e:
        print(f"启动主程序时出错: {e}")

# 启动动画并在 2 秒后结束
def start_animation():
    root = tk.Tk()
    root.title("启动中")
    root.overrideredirect(True)
    root.attributes('-topmost', True)

    # 使用相对路径加载图片
    image_path = resource_path('Picture/StartPicture.jpg')
    if not os.path.exists(image_path):
        print(f"图片文件不存在: {image_path}")
        sys.exit(1)

    try:
        img = Image.open(image_path)
        photo = ImageTk.PhotoImage(img)
        img_width, img_height = img.size
        root.geometry(f"{img_width}x{img_height}+{root.winfo_screenwidth() // 2 - img_width // 2}+{root.winfo_screenheight() // 2 - img_height // 2}")
        canvas = tk.Canvas(root, width=img_width, height=img_height)
        canvas.pack()
        canvas.create_image(img_width // 2, img_height // 2, image=photo)
    except Exception as e:
        print(f"无法加载图片: {image_path}, 错误信息: {str(e)}")
        sys.exit(1)

    progress_bar = ttk.Progressbar(root, orient='horizontal', length=img_width, mode='determinate')
    progress_bar.place(x=0, y=img_height - 30)

    start_time = time.time()

    def update_progress():
        elapsed_time = time.time() - start_time
        if elapsed_time < 2:
            progress = int((elapsed_time / 2) * 100)
            progress_bar['value'] = progress
            root.after(10, update_progress)  # 更新进度条
        else:
            progress_bar['value'] = 100  # 进度条满了
            root.after(500, root.quit)  # 500ms后退出动画窗口

    root.after(10, update_progress)
    root.mainloop()

if __name__ == '__main__':
    # 启动主程序
    start_main_program()
    # 启动动画
    start_animation()
