import json
import sys
import os

# 获取当前脚本所在的目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 定义用户数据文件路径
user_data_file = os.path.join(BASE_DIR, "Datarecourses/UserData.json")

def update_balance(username, action, amount):
    try:
        # 读取用户数据文件
        with open(user_data_file, 'r', encoding='utf-8') as file:
            users = json.load(file)

        # 查找指定用户名的用户
        for user in users:
            if user["username"] == username:
                if action == "deduct":
                    # 扣除金额
                    if user["balance"] >= amount:
                        user["balance"] -= amount
                    else:
                        print("余额不足，无法扣除。")
                        return
                elif action == "add":
                    # 增加金额
                    user["balance"] += amount
                else:
                    print("无效的操作类型。")
                    return

                # 将更新后的用户数据写回文件
                with open(user_data_file, 'w', encoding='utf-8') as file:
                    json.dump(users, file, ensure_ascii=False, indent=4)
                print(f"用户 {username} 的余额已更新。")
                return

        print(f"未找到用户名 {username} 的用户。")
    except FileNotFoundError:
        print("用户数据文件未找到。")
    except json.JSONDecodeError:
        print("用户数据文件格式错误。")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("用法: python EditAccount.py <用户名> <操作类型> <金额>")
        print("操作类型: deduct（扣除）, add（增加）")
    else:
        username = sys.argv[1]
        action = sys.argv[2]
        try:
            amount = int(sys.argv[3])
            update_balance(username, action, amount)
        except ValueError:
            print("金额必须是整数。")