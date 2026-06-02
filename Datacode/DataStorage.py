# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox
import subprocess
import json
import uuid
import re
import os
import sys

# 获取当前脚本所在的目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 构建数据文件的相对路径
DATA_FILE = os.path.join(BASE_DIR, "Datarecourses/UserData.json")

# 确保数据目录存在
data_dir = os.path.join(BASE_DIR, "Datarecourses")
if not os.path.exists(data_dir):
    os.mkdir(data_dir)

# 初始化用户数据文件
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump([], f)


def register_user():
    uid = str(uuid.uuid4())
    username = username_entry.get()
    password = password_entry.get()
    balance = 200

    if not username or not password:
        messagebox.showwarning("输入错误", "用户名和密码不能为空！")
        return

    if not re.match(r'^[a-zA-Z0-9]+$', password):
        messagebox.showwarning("输入错误", "密码只能包含字母和数字！")
        return

    # 读取现有用户数据
    try:
        with open(DATA_FILE, "r", encoding='utf-8') as f:
            users = json.load(f)
    except json.JSONDecodeError:
        users = []  # 如果文件为空或者格式错误，初始化为空列表

    # 检查用户名是否已存在
    if any(user["username"] == username for user in users):
        messagebox.showwarning("用户名已存在", "该用户名已被注册！")
        return

    # 添加新用户
    users.append({
        "UID": uid,
        "username": username,
        "password": password,
        "balance": balance
    })

    # 将新数据写回文件
    with open(DATA_FILE, "w", encoding='utf-8') as f:
        json.dump(users, f, indent=4)

    messagebox.showinfo("注册成功", f"注册成功！UID: {uid}, 初始余额: ¥{balance}")
    register_window.destroy()


def login_user():
    username = login_username_entry.get()
    password = login_password_entry.get()

    if not username or not password:
        messagebox.showwarning("输入错误", "用户名和密码不能为空！")
        return

    # 读取用户数据
    try:
        with open(DATA_FILE, "r", encoding='utf-8') as f:
            users = json.load(f)
    except json.JSONDecodeError:
        messagebox.showerror("错误", "用户数据文件格式错误")
        return

    # 检查用户名和密码
    for user in users:
        if user["username"] == username and user["password"] == password:
            account_balance = user['balance']
            if account_balance < 10:
                messagebox.showinfo("余额提示", "由于您是第一次游玩，系统赠送10元！")
                user['balance'] += 10
                # 将更新后的数据写回文件
                with open(DATA_FILE, "w", encoding='utf-8') as f:
                    json.dump(users, f, indent=4)
                account_balance = user['balance']

            # 登录成功，将用户名和余额传递给 Generatescratchcards.py
            user_name = username
            messagebox.showinfo("登录成功", f"欢迎回来，{username}！余额: ¥{account_balance}")
            login_window.destroy()

            # 调用 Generatescratchcards.py 脚本并传递用户信息
            script_path = os.path.join(BASE_DIR, "Datacode/Generatescratchcards.py")
            try:
                subprocess.run(["python", script_path, user_name, str(account_balance)])
            except FileNotFoundError:
                messagebox.showerror("错误", "找不到脚本文件 Generatescratchcards.py")
            return

    messagebox.showerror("登录失败", "用户名或密码错误！")


def open_register_window():
    global register_window, username_entry, password_entry
    register_window = tk.Toplevel(login_window)
    register_window.title("注册界面")

    # 注册窗口布局设置
    window_width = 400
    window_height = 180
    center_window(register_window, window_width, window_height)

    # 配置列权重
    register_window.grid_columnconfigure(0, weight=1)
    register_window.grid_columnconfigure(1, weight=3)

    # 用户名输入框
    tk.Label(register_window, text="用户名（中文或英文）:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
    username_entry = tk.Entry(register_window, width=25, bd=2, relief="solid", font=("Arial", 12))
    username_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

    # 密码输入框
    tk.Label(register_window, text="密码（字母和数字）:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
    password_entry = tk.Entry(register_window, width=25, show="*", bd=2, relief="solid", font=("Arial", 12))
    password_entry.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

    # 注册按钮（跨列居中）
    register_button = tk.Button(
        register_window,
        text="注册",
        command=register_user,
        relief="flat",
        bg="#4CAF50",
        fg="white",
        font=("Arial", 12, "bold"),
        width=12
    )
    register_button.grid(row=2, column=0, columnspan=2, pady=20, sticky="n")


def center_window(window, width, height):
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    window.geometry(f"{width}x{height}+{x}+{y}")


def create_login_window():
    global login_window, login_username_entry, login_password_entry
    login_window = tk.Tk()
    login_window.title("登录界面")

    # 禁用最大化功能
    login_window.resizable(False, False)

    # 登录窗口布局设置
    window_width = 400  # 适当增加宽度以改善布局
    window_height = 180
    center_window(login_window, window_width, window_height)

    # 配置列权重
    login_window.grid_columnconfigure(0, weight=1)
    login_window.grid_columnconfigure(1, weight=3)

    # 用户名输入
    tk.Label(login_window, text="用户名:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
    login_username_entry = tk.Entry(login_window, width=25, bd=2, relief="solid", font=("Arial", 12))
    login_username_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

    # 密码输入
    tk.Label(login_window, text="密码:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
    login_password_entry = tk.Entry(login_window, width=25, show="*", bd=2, relief="solid", font=("Arial", 12))
    login_password_entry.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

    # 按钮容器框架
    button_frame = tk.Frame(login_window)
    button_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")
    button_frame.grid_columnconfigure(0, weight=1)
    button_frame.grid_columnconfigure(1, weight=1)

    # 登录按钮
    login_button = tk.Button(
        button_frame,
        text="登录",
        command=login_user,
        relief="flat",
        bg="#4CAF50",
        fg="white",
        font=("Arial", 12, "bold"),
        width=12
    )
    login_button.grid(row=0, column=0, padx=5)

    # 注册按钮
    register_button = tk.Button(
        button_frame,
        text="注册",
        command=open_register_window,
        relief="flat",
        bg="#008CBA",
        fg="white",
        font=("Arial", 12, "bold"),
        width=12
    )
    register_button.grid(row=0, column=1, padx=5)

    login_window.mainloop()


create_login_window()