# -*- coding: utf-8 -*-
import pygame
from pygame.locals import *
import subprocess
import sys
import os
import json
import time

# 获取当前脚本所在的目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def initialize_game():
    global game_active, is_winner, total_money, scratched_complete, selected_numbers, mid_uncovered_image, account_balance, mouse_mode, bonus_display_time, cost_display_time, draw_history
    mouse_mode = "scratch"
    bonus_display_time = 0
    cost_display_time = 0
    draw_history = []
    # 扣除 10 元购买新刮刮乐
    edit_account_script = os.path.join(BASE_DIR, "EditAccount.py")
    subprocess.run(["python", edit_account_script, user_name, "deduct", "10"])
    cost_display_time = time.time()
    data_file = os.path.join(BASE_DIR, "Datarecourses/UserData.json")
    with open(data_file, 'r', encoding='utf-8') as file:
        users = json.load(file)
    found_user = False
    for user in users:
        if user["username"] == user_name:
            account_balance = user["balance"]
            found_user = True
            break
    if not found_user:
        print(f"未找到用户 {user_name}，无法继续游戏。")
        pygame.quit()
        sys.exit()

    # 运行RandomPrise.py并获取总金额
    random_prise_script = os.path.join(BASE_DIR, "RandomPrise.py")
    result = subprocess.run(["python", random_prise_script, user_name,
                             str(account_balance)], capture_output=True, text=True)
    # 提取最后一行作为总金额
    output_lines = result.stdout.strip().split('\n')
    total_money = int(output_lines[-1])

    # 重新加载新生成的图片
    mid_uncovered_image_path = os.path.join(BASE_DIR, "Picture/frontPicture/i_love_china_mid_uncovered_clear_with_numbers.png")
    mid_uncovered_image = pygame.image.load(mid_uncovered_image_path).convert()

    # 重新组合基础图片
    combined_image.fill((0, 0, 0, 0))
    combined_image.blit(up_image, (0, 0))
    combined_image.blit(mid_uncovered_image, (0, up_image.get_height()))
    combined_image.blit(down_image, (0, up_image.get_height() + mid_uncovered_image.get_height()))

    # 重新加载刮擦层
    scratch_surface.fill((0, 0, 0, 0))
    scratch_mask_path = os.path.join(BASE_DIR, "Picture/frontPicture/i_love_china_combined.png")
    mask_image = pygame.image.load(scratch_mask_path).convert_alpha()
    scratch_surface.blit(mask_image, (0, 0))

    # 生成新奖品
    game_active = True
    scratched_complete = False
    is_winner = total_money > 0
    selected_numbers = []
def draw_user_info():

    # 用户信息面板
    info_panel = pygame.Surface((280, 150))
    info_panel.fill(GREY)
    pygame.draw.rect(info_panel, WHITE, (0, 0, 280, 150), 3)

    user_name_text = font.render(f"用户名: {user_name}", True, BLACK)
    balance_text = font.render(f"账户余额: ¥{account_balance:.0f}", True, BLACK)

    info_panel.blit(user_name_text, (20, 20))
    info_panel.blit(balance_text, (20, 60))

    if is_winner and time.time() - bonus_display_time < 1:
        bonus_text = font.render(f"+¥{total_money:.0f}", True, (255, 0, 0))
        info_panel.blit(bonus_text, (20, 90))

    if time.time() - cost_display_time < 1:
        cost_text = font.render(f"-¥10", True, BLACK)
        info_panel.blit(cost_text, (20, 90))

    screen.blit(info_panel, (width + 10, 20))
def draw_result_panel():
    # 结果展示面板
    result_panel = pygame.Surface((280, 150))
    result_panel.fill(GREY)
    pygame.draw.rect(result_panel, WHITE, (0, 0, 280, 150), 3)

    if is_winner:
        title = font.render("恭喜中奖！", True, (255, 0, 0))
        prize_text = font.render(f"金额: ¥{total_money:.0f}", True, BLACK)
    else:
        title = font.render("未中奖", True, BLACK)
        prize_text = font.render("下次好运！", True, BLACK)

    result_panel.blit(title, (20, 20))
    result_panel.blit(prize_text, (20, 60))
    screen.blit(result_panel, (width + 10, 200))

def draw_control_buttons():
    small_button_width = 160  # 修改画笔按钮宽度，使其和再来一次按钮一致
    big_button_width = 160
    button_height = 50
    button_gap = 3
    start_x = width + 70
    top_button_y = height - 240
    # 计算按钮之间的垂直间距
    spacing = 5
    # 绘制刮刮按钮
    scratch_button_rect = pygame.Rect(start_x, top_button_y, big_button_width, button_height)
    pygame.draw.rect(screen, BUTTON_COLOR, scratch_button_rect, border_radius=10)
    pygame.draw.rect(screen, WHITE, scratch_button_rect, 3, border_radius=10)
    scratch_text = button_font.render("刮刮", True, WHITE)
    scratch_text_rect = scratch_text.get_rect(center=scratch_button_rect.center)
    screen.blit(scratch_text, scratch_text_rect)

    # 绘制画笔按钮
    brush_button_rect = pygame.Rect(start_x, scratch_button_rect.bottom + spacing, small_button_width, button_height)
    pygame.draw.rect(screen, BUTTON_COLOR, brush_button_rect, border_radius=10)
    pygame.draw.rect(screen, WHITE, brush_button_rect, 3, border_radius=10)
    brush_text = button_font.render("画笔", True, WHITE)
    brush_text_rect = brush_text.get_rect(center=brush_button_rect.center)
    screen.blit(brush_text, brush_text_rect)

    # 绘制查看结果按钮
    check_result_button_rect = pygame.Rect(start_x, brush_button_rect.bottom + spacing, big_button_width, button_height)
    pygame.draw.rect(screen, BUTTON_COLOR, check_result_button_rect, border_radius=10)
    pygame.draw.rect(screen, WHITE, check_result_button_rect, 3, border_radius=10)
    check_result_text = button_font.render("查看结果", True, WHITE)
    check_result_text_rect = check_result_text.get_rect(center=check_result_button_rect.center)
    screen.blit(check_result_text, check_result_text_rect)

    # 绘制再来一次按钮
    again_button_rect = pygame.Rect(start_x, check_result_button_rect.bottom + spacing, big_button_width, button_height)
    pygame.draw.rect(screen, BUTTON_COLOR, again_button_rect, border_radius=10)
    pygame.draw.rect(screen, WHITE, again_button_rect, 3, border_radius=10)
    again_text = button_font.render("再来一次", True, WHITE)
    again_text_rect = again_text.get_rect(center=again_button_rect.center)
    screen.blit(again_text, again_text_rect)

    return scratch_button_rect, brush_button_rect, check_result_button_rect, again_button_rect


def clear_scratch_area():
    global scratched_complete, mouse_mode
    target_rect = pygame.Rect(13, 482, 507 - 13, 650 - 482)
    target_surface = scratch_surface.subsurface(target_rect)
    target_surface.fill((0, 0, 0, 0))
    scratched_complete = True
    mouse_mode = "draw"


# 获取传递的用户信息
user_name = sys.argv[1]
data_file = os.path.join(BASE_DIR, "Datarecourses/UserData.json")
with open(data_file, 'r', encoding='utf-8') as file:
    users = json.load(file)
found_user = False
for user in users:
    if user["username"] == user_name:
        account_balance = user["balance"]
        found_user = True
        break
if not found_user:
    print(f"未找到用户 {user_name}，无法继续游戏。")
    pygame.quit()
    sys.exit()

# 初始化pygame
pygame.init()

# 设置窗口的宽度和高度
width, height = 520, 780
screen = pygame.display.set_mode((width + 300, height))
pygame.display.set_caption('刮刮乐游戏')

# 定义颜色
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREY = (200, 200, 200)
BUTTON_COLOR = (50, 150, 50)
CIRCLE_COLOR = (255, 0, 0)
RED = (255, 0, 0)

# 图片路径
down_image_path = os.path.join(BASE_DIR, "Picture/frontPicture/i_love_china_down.png")
up_image_path = os.path.join(BASE_DIR, "Picture/frontPicture/i_love_china_up.png")
scratch_mask_path = os.path.join(BASE_DIR, "Picture/frontPicture/i_love_china_combined.png")

# 加载图像
try:
    down_image = pygame.image.load(down_image_path).convert()
    up_image = pygame.image.load(up_image_path).convert()
except pygame.error as e:
    print(f"图片加载失败: {e}")
    pygame.quit()
    sys.exit()

# 创建合成图像
total_height = up_image.get_height() + down_image.get_height() + 500
combined_image = pygame.Surface((width, total_height), pygame.SRCALPHA)
scratch_surface = pygame.Surface((width, total_height), pygame.SRCALPHA)

# 加载字体
font_path = os.path.join(BASE_DIR, "Front/MSYHBD.TTC")
font = pygame.font.Font(font_path, 24)
button_font = pygame.font.Font(font_path, 28)

# 定义变量
game_active = True
is_winner = False
total_money = 0
scratched_complete = False
selected_numbers = []
mouse_mode = "scratch"
bonus_display_time = 0
cost_display_time = 0
draw_history = []

# 初始化游戏
initialize_game()

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            (scratch_button_rect, brush_button_rect,
             check_result_button_rect, again_button_rect) = draw_control_buttons()
            if scratch_button_rect.collidepoint(event.pos):
                mouse_mode = "scratch"
            elif brush_button_rect.collidepoint(event.pos):
                mouse_mode = "draw"
            elif check_result_button_rect.collidepoint(event.pos) and not scratched_complete:
                clear_scratch_area()
                if is_winner:
                    # 增加中奖金额到账户
                    edit_account_script = os.path.join(BASE_DIR, "EditAccount.py")
                    subprocess.run(["python", edit_account_script, user_name, "add",
                                    str(total_money)])
                    data_file = os.path.join(BASE_DIR, "Datarecourses/UserData.json")
                    with open(data_file, 'r', encoding='utf-8') as file:
                        users = json.load(file)
                    for user in users:
                        if user["username"] == user_name:
                            account_balance = user["balance"]
                    bonus_display_time = time.time()
            elif again_button_rect.collidepoint(event.pos) and scratched_complete:
                data_file = os.path.join(BASE_DIR, "Datarecourses/UserData.json")
                with open(data_file, 'r', encoding='utf-8') as file:
                    users = json.load(file)
                found_user = False
                for user in users:
                    if user["username"] == user_name:
                        account_balance = user["balance"]
                        found_user = True
                        break
                if not found_user:
                    print(f"未找到用户 {user_name}，无法继续游戏。")
                    pygame.quit()
                    sys.exit()
                if account_balance < 10:
                    balance_warning = font.render("余额不足", True, (255, 0, 0))
                    # 计算提示信息的位置，显示在刮刮按钮上边
                    warning_x = scratch_button_rect.left + balance_warning.get_height() + 2
                    warning_y = scratch_button_rect.top - balance_warning.get_height() - 5
                    screen.blit(balance_warning, (warning_x, warning_y))
                    pygame.display.flip()
                    time.sleep(2)
                else:
                    initialize_game()
        elif event.type == pygame.MOUSEBUTTONUP:
            if mouse_mode == "draw":
                if draw_history and draw_history[-1]:
                    draw_history.append([])

    # 鼠标操作
    mouse_pos = pygame.mouse.get_pos()
    mouse_pressed = pygame.mouse.get_pressed()
    if mouse_pressed[0]:
        if mouse_mode == "scratch":
            pygame.draw.circle(scratch_surface, (0, 0, 0, 0), mouse_pos, 20)
        elif mouse_mode == "draw":
            pygame.draw.circle(combined_image, RED, mouse_pos, 1)
            if not draw_history:
                draw_history.append([mouse_pos])
            else:
                draw_history[-1].append(mouse_pos)

    screen.fill(BLACK)
    screen.blit(combined_image, (0, 0))
    screen.blit(scratch_surface, (0, 0))

    draw_user_info()
    if scratched_complete:
        draw_result_panel()
    (scratch_button_rect, brush_button_rect,
     check_result_button_rect, again_button_rect) = draw_control_buttons()

    pygame.display.flip()

pygame.quit()
