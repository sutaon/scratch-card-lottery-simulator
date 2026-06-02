# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont
import random
import json
from pypinyin import lazy_pinyin
import sys
import os

# 获取当前脚本所在的目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 图片路径和输出路径
image_path = os.path.join(BASE_DIR, "Picture/frontPicture/i_love_china_mid_uncovered_clear.png")
output_path = os.path.join(BASE_DIR, "Picture/frontPicture/i_love_china_mid_uncovered_clear_with_numbers.png")

# 字体路径
font_number_path = os.path.join(BASE_DIR, "Front/Number.ttf")  # 数字字体
font_pinyin_path = os.path.join(BASE_DIR, "Front/Pinyin.ttf")  # 拼音和金额字体

# 打开图片
image = Image.open(image_path)
draw = ImageDraw.Draw(image)

# 加载字体
font_number = ImageFont.truetype(font_number_path, 21)  # 数字字体 21 号
font_pinyin = ImageFont.truetype(font_pinyin_path, 8)  # 拼音字体 8 号
font_money = ImageFont.truetype(font_pinyin_path, 12)  # 金额字体 12 号

# 从文件加载数字和拼音的映射
number_txt_path = os.path.join(BASE_DIR, "Datarecourses/Number.txt")
with open(number_txt_path, "r", encoding="utf-8") as f:
    number_pinyin_dict = json.load(f)

# 从文件加载中奖金额和拼音的映射
winning_txt_path = os.path.join(BASE_DIR, "Datarecourses/Winning.txt")
with open(winning_txt_path, "r", encoding="utf-8") as f:
    winning_dict = json.load(f)

# 获取所有两位数
valid_numbers = [f"{i:02d}" for i in range(100)]  # 包含所有数字 00 到 99

# 用于记录连续未出现的次数
consecutive_non_appearance_count = 0

# 随机选择两个数字作为 (72, 42) 和 (72, 100) 的数字
additional_numbers = random.sample(valid_numbers, 2)

# 检查是否需要强制出现
if consecutive_non_appearance_count == 9:
    # 强制让一个额外数字出现在其他十个数字中
    selected_additional_number = random.choice(additional_numbers)
    remaining_numbers = [num for num in valid_numbers if num not in additional_numbers]
    other_numbers = random.sample(remaining_numbers, 9)
    other_numbers.append(selected_additional_number)
    random.shuffle(other_numbers)
    consecutive_non_appearance_count = 0
else:
    # 10% 的概率让 (72, 42) 和 (72, 100) 的数字出现在其他十个位置中
    if random.random() < 0.1:
        # 随机选择一个额外数字添加到其他十个数字中
        selected_additional_number = random.choice(additional_numbers)
        remaining_numbers = [num for num in valid_numbers if num not in additional_numbers]
        other_numbers = random.sample(remaining_numbers, 9)
        other_numbers.append(selected_additional_number)
        random.shuffle(other_numbers)
        consecutive_non_appearance_count = 0
    else:
        remaining_numbers = [num for num in valid_numbers if num not in additional_numbers]
        other_numbers = random.sample(remaining_numbers, 10)
        consecutive_non_appearance_count += 1

numbers = other_numbers + additional_numbers

# 坐标更新：将 (72, 57) 改为 (72, 42)
coordinates = [
    (147, 27), (219, 27), (291, 27), (363, 27), (435, 27),
    (147, 92), (219, 92), (291, 92), (363, 92), (435, 92),
    (72, 42),  # 新增数字 1 的坐标
    (72, 100)  # 新增数字 2 的坐标，确保 Y=100
]

# 获取数字的拼音（返回拼音的大写字母，逐位转换）
def get_number_pinyin(number):
    return number_pinyin_dict[str(number)].upper()

# 获取金额的拼音（返回金额拼音的大写字母）
def get_money_pinyin(money):
    return ''.join(lazy_pinyin(str(money))).upper()

# 用来保存新增数字的中奖金额
added_numbers = {}

# 在图片上绘制数字、拼音和金额
for i, number in enumerate(numbers):
    # 获取当前数字坐标
    x, y = coordinates[i]

    # 绘制数字
    number_str = str(number)
    num_bbox = draw.textbbox((x, y), number_str, font=font_number)
    num_width = num_bbox[2] - num_bbox[0]  # 计算文本的宽度
    num_height = num_bbox[3] - num_bbox[1]  # 计算文本的高度
    draw.text((x - num_width // 2, y), number_str, font=font_number, fill="black")

    pinyin_str = get_number_pinyin(number)  # 根据数字获取拼音
    pinyin_bbox = draw.textbbox((x, y + num_height + 10), pinyin_str, font=font_pinyin)
    pinyin_width = pinyin_bbox[2] - pinyin_bbox[0]
    pinyin_height = pinyin_bbox[3] - pinyin_bbox[1]
    draw.text((x - pinyin_width // 2, y + num_height), pinyin_str, font=font_pinyin, fill="black")

    # 如果是新增的数字坐标，则只绘制数字和拼音，不绘制金额
    if (x, y) in [(72, 42), (72, 100)]:
        continue  # 跳过金额和金额拼音的绘制

    # 如果不是新增的数字坐标，则绘制金额和金额拼音
    else:
        # 随机选择中奖金额
        winning_amount, winning_pinyin = random.choice(list(winning_dict.items()))

        # 去掉金额中的逗号
        winning_amount = winning_amount.replace(',', '')

        money_str = f"¥{winning_amount}"

        # 绘制金额，与数字拼音间隔 3 像素
        money_bbox = draw.textbbox((x, y + num_height + pinyin_height + 6), money_str, font=font_money)
        money_width = money_bbox[2] - money_bbox[0]
        money_height = money_bbox[3] - money_bbox[1]
        draw.text((x - money_width // 2, y + num_height + pinyin_height + 6), money_str, font=font_money, fill="black")

        # 绘制金额拼音，与金额间隔 3 像素
        money_pinyin_str = winning_pinyin.upper()  # 获取金额拼音
        money_pinyin_bbox = draw.textbbox((x, y + num_height + pinyin_height + money_height + 9), money_pinyin_str,
                                          font=font_pinyin)
        money_pinyin_width = money_pinyin_bbox[2] - money_pinyin_bbox[0]
        money_pinyin_height = money_pinyin_bbox[3] - money_pinyin_bbox[1]
        draw.text((x - money_pinyin_width // 2, y + num_height + pinyin_height + money_height + 9), money_pinyin_str,
                  font=font_pinyin, fill="black")

        # 记录该数字的中奖金额
        added_numbers[number] = winning_amount

# 保存带有数字和拼音的图片
image.save(output_path)

# 打印确认信息
print(f"图片已保存为 {output_path}")

# 计算总金额：将新增数字的金额加起来
total_money = 0
added_number_set = {(72, 42), (72, 100)}  # 新增数字的坐标集合
added_numbers_set = set(numbers[-2:])  # 新增数字的数字集合

# 遍历其他数字的坐标并与新增数字做比较
for i, (x, y) in enumerate(coordinates[:10]):  # 不包含新增的两个位置
    number = numbers[i]
    # 如果数字与新增的两个数字中的一个相同
    if number in added_numbers_set:
        # 获取该数字的中奖金额
        winning_amount = added_numbers.get(number)
        if winning_amount:
            total_money += int(winning_amount.replace(',', ''))  # 加上中奖金额

# 返回总金额
print(total_money)