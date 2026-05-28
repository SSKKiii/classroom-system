"""
教室空位管理系统 - 完整版 v8
包含：仪表盘/教室管理/排课管理/空闲查询/记录使用/统计分析/报告导出
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
import json
import os
from pathlib import Path
import random
import matplotlib.pyplot as plt
import scipy.stats as stats
from sklearn.preprocessing import MinMaxScaler
import plotly.express as px
import plotly.graph_objects as go
import matplotlib

matplotlib.use('Agg')  # 非交互式后端，Streamlit必须
# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'KaiTi']
plt.rcParams['axes.unicode_minus'] = False
from utils.statistics import ClassroomStatistics
from utils.visualization import ClassroomVisualization
from utils.report import ReportGenerator

st.set_page_config(
    page_title="教室空位管理系统",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ====== 大学课表时间段定义（45分钟小节，10分钟课间，20分钟大课间）======
# 上午：8:00开始
# 下午：14:00开始
# 晚上：18:30开始

MORNING_START = 8  # 上午第一节开始小时
AFTERNOON_START = 14  # 下午第一节开始小时
EVENING_START = 18  # 晚上第一节开始小时（18:00）
CLASS_DURATION = 45  # 每小节45分钟
SHORT_BREAK = 10  # 小课间10分钟
LONG_BREAK = 20  # 大课间20分钟


def generate_time_slots():
    """生成所有时间段选项"""
    slots = []

    # 上午两大节（4小节）
    for period in range(2):
        for small in range(2):
            start_hour = MORNING_START + period * 2 + small * (CLASS_DURATION // 60 + (CLASS_DURATION % 60) / 60)
            if small == 1:  # 第二小节后有大课间
                start_hour += CLASS_DURATION / 60 + SHORT_BREAK / 60
            else:
                start_hour += CLASS_DURATION / 60 + SHORT_BREAK / 60

            start_min = int((start_hour % 1) * 60)
            start_h = int(start_hour) if small == 0 else int(start_hour)
            if small > 0:
                start_h = MORNING_START + period * 2 + 1
                start_min = 0

            end_h = start_h + CLASS_DURATION // 60
            end_min = start_min + CLASS_DURATION % 60
            if end_min >= 60:
                end_h += 1
                end_min -= 60

            # 重新计算正确的起始时间
            if period == 0:
                base_start = MORNING_START * 60  # 480分钟
                first_small_start = base_start
                first_small_end = base_start + CLASS_DURATION  # 525
                second_small_start = first_small_end + SHORT_BREAK  # 535
                second_small_end = second_small_start + CLASS_DURATION  # 580

                if small == 0:
                    start_min, end_min = first_small_start, first_small_end
                else:
                    start_min, end_min = second_small_start, second_small_end
            else:
                # 大课间后
                base_start = MORNING_START * 60 + (2 * CLASS_DURATION + CLASS_DURATION + SHORT_BREAK * 2 + LONG_BREAK)
                third_small_start = base_start
                third_small_end = base_start + CLASS_DURATION
                fourth_small_start = third_small_end + SHORT_BREAK
                fourth_small_end = fourth_small_start + CLASS_DURATION

                if small == 0:
                    start_min, end_min = third_small_start, third_small_end
                else:
                    start_min, end_min = fourth_small_start, fourth_small_end

            start_h = 8 + start_min // 60
            start_m = start_min % 60
            end_h = 8 + end_min // 60
            end_m = end_min % 60

            slots.append(f"{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}")

    # 重新生成完整正确的时间段
    slots = []

    # 第一节 08:00-08:45
    slots.append("08:00-08:45")
    # 第二节 08:55-09:40
    slots.append("08:55-09:40")
    # 第三节 10:00-10:45
    slots.append("10:00-10:45")
    # 第四节 10:55-11:40
    slots.append("10:55-11:40")
    # 午休

    # 第五节 14:00-14:45
    slots.append("14:00-14:45")
    # 第六节 14:55-15:40
    slots.append("14:55-15:40")
    # 第七节 16:00-16:45
    slots.append("16:00-16:45")
    # 第八节 16:55-17:40
    slots.append("16:55-17:40")
    # 晚上第一大节
    # 第九节 18:00-18:45
    slots.append("18:00-18:45")
    # 第十节 18:55-19:40
    slots.append("18:55-19:40")

    return slots


CLASS_TIME_OPTIONS = generate_time_slots()

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def sort_classroom_names(names):
    """教室名排序：字母前缀优先(A-Z)，再按数字从小到大；无字母前缀的排最后"""

    def sort_key(name):
        # 提取字母前缀和数字部分
        alpha_part = ''
        num_part = ''
        i = 0
        while i < len(name) and name[i].isalpha():
            alpha_part += name[i]
            i += 1
        while i < len(name) and name[i].isdigit():
            num_part += name[i]
            i += 1
        # 有字母前缀的排前面(has_alpha=0)，无字母的排后面(has_alpha=1)
        has_alpha = 0 if alpha_part else 1
        return (has_alpha, alpha_part.lower(), int(num_part) if num_part else 0, name)

    return sorted(names, key=sort_key)


WEEKDAYS_SHORT = ["周一", "周二", "周三", "周四", "周五"]  # 工作日
USAGE_TYPES = ["上课", "自习", "讲座", "考试", "会议", "其他"]
# 上课/讲座/考试/会议 为优先级类型，覆盖自习/其他
PRIORITY_TYPES = {"上课", "讲座", "考试", "会议"}
SCHEDULE_TYPES = ["专业课", "公共课", "选修课", "实验课"]

# 课程名称库
COURSE_NAMES = {
    "专业课": ["高等数学", "线性代数", "概率论与数理统计", "离散数学", "数据结构", "算法设计", "计算机网络", "操作系统",
               "数据库原理", "软件工程"],
    "公共课": ["大学英语", "大学语文", "大学物理", "大学化学", "思想政治理论", "体育", "计算机基础"],
    "选修课": ["音乐欣赏", "美术鉴赏", "文学名著导读", "心理学入门", "经济学原理", "管理学基础"],
    "实验课": ["物理实验", "化学实验", "生物实验", "计算机实验", "电子技术实验"]
}

# 教师名称库
TEACHER_NAMES = ["王教授", "李副教授", "张讲师", "刘老师", "陈老师", "杨老师", "赵老师", "黄老师", "周老师", "吴老师",
                 "徐老师", "孙老师"]

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = DATA_DIR / "classroom_data.json"
SCHEDULE_FILE = DATA_DIR / "schedule_data.json"

# ====== Session State 初始化 ======
for key in ['classrooms', 'records', 'schedules']:
    if key not in st.session_state:
        st.session_state[key] = []


def load_data():
    """加载数据和排课（含安全捕获机制）"""
    try:
        if DATA_FILE.exists():
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                st.session_state.classrooms = data.get('classrooms', [])
                records = data.get('records', [])
                for r in records:
                    if 'time_slot' in r and 'time_slots' not in r:
                        r['time_slots'] = [r['time_slot']] if r['time_slot'] else []
                st.session_state.records = records
        else:
            st.session_state.classrooms = []
            st.session_state.records = []
    except Exception as e:
        st.sidebar.error(f"⚠️ 核心数据文件读取异常，已安全重置。({e})")
        st.session_state.classrooms = []
        st.session_state.records = []

    try:
        if SCHEDULE_FILE.exists():
            with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                st.session_state.schedules = json.load(f)
        else:
            st.session_state.schedules = []
    except Exception as e:
        st.sidebar.error(f"⚠️ 排课数据文件读取异常，已安全重置。({e})")
        st.session_state.schedules = []


def save_data():
    """保存数据（原子级写入防崩溃机制）"""
    try:
        # 1. 采用临时文件写入法，先写 .tmp，写完后瞬间原子替换，防止断电导致文件损坏空洞
        temp_data_file = DATA_FILE.with_suffix('.tmp')
        with open(temp_data_file, 'w', encoding='utf-8') as f:
            json.dump({
                'classrooms': st.session_state.classrooms,
                'records': st.session_state.records
            }, f, ensure_ascii=False, indent=2)
        os.replace(temp_data_file, DATA_FILE)  # 操作系统层面的原子级无缝替换

        # 2. 保存排课数据
        temp_sched_file = SCHEDULE_FILE.with_suffix('.tmp')
        with open(temp_sched_file, 'w', encoding='utf-8') as f:
            json.dump(st.session_state.schedules, f, ensure_ascii=False, indent=2)
        os.replace(temp_sched_file, SCHEDULE_FILE)

    except Exception as e:
        st.sidebar.error(f"🛑 数据持久化遭遇系统级拦截: {e}")


def is_room_in_use(classroom, date, time_slot):
    """检查教室是否被使用（来自records）"""
    for r in st.session_state.records:
        if r.get('classroom') == classroom and r.get('date') == date:
            if time_slot in r.get('time_slots', []):
                return True, r
    return False, None


def is_room_scheduled(classroom, weekday, time_slot):
    """检查教室是否有排课（来自schedules），使用时段重叠检测"""
    for s in st.session_state.schedules:
        if s.get('classroom') == classroom and s.get('weekday') == weekday:
            if slot_overlaps_45(time_slot, s.get('time_slots', [])):
                return True, s
    return False, None


def parse_time(s):
    """将 'HH:MM' 转为分钟数"""
    h, m = map(int, s.split(':'))
    return h * 60 + m


def generate_10min_slots():
    """生成所有10分钟时段（08:00-21:40）"""
    slots = []
    start_min = 8 * 60  # 08:00
    end_min = 21 * 60 + 40  # 21:40
    current = start_min
    while current < end_min:
        sh = current // 60
        sm = current % 60
        eh = (current + 10) // 60
        em = (current + 10) % 60
        slots.append(f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}")
        current += 10
    return slots


SLOT_10MIN = generate_10min_slots()


def generate_30min_slots():
    """生成所有30分钟时段（08:00-21:30）"""
    slots = []
    for h in range(8, 22):
        for m in [0, 30]:
            if h == 21 and m == 30:
                continue  # 最后一个21:30-22:00超出范围
            start_h, start_m = h, m
            end_h, end_m = h + (m + 30) // 60, (m + 30) % 60
            slots.append(f"{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}")
    return slots


SLOT_30MIN = generate_30min_slots()


def slot_overlaps_45(slot_str, schedule_slots):
    """检查一个30分钟时段是否与任意45分钟课表时段重叠"""
    try:
        s_str, e_str = slot_str.split('-')
        s_min = parse_time(s_str)
        e_min = parse_time(e_str)  # e.g., 08:30
    except:
        return False

    for sched_slot in schedule_slots:
        try:
            sc_s, sc_e = sched_slot.split('-')
            sc_s_min = parse_time(sc_s)  # e.g., 08:00
            sc_e_min = parse_time(sc_e)  # e.g., 08:45
        except:
            continue
        # 重叠条件：两个开区间有交集
        if s_min < sc_e_min and sc_s_min < e_min:
            return True
    return False


def check_schedule_conflicts(classroom, weekday, time_slots_30min):
    """检查给定30分钟时段列表是否与排课冲突，返回冲突列表"""
    conflicts = []
    for slot in time_slots_30min:
        for s in st.session_state.schedules:
            if s.get('classroom') == classroom and s.get('weekday') == weekday:
                schedule_slots = s.get('time_slots', [])
                if slot_overlaps_45(slot, schedule_slots):
                    # 找出该教室该时段已排课的所有冲突小节
                    existing = [cs for cs in time_slots_30min if slot_overlaps_45(cs, schedule_slots)]
                    conflicts.append({
                        'slot': slot,
                        'course_name': s.get('course_name', ''),
                        'teacher': s.get('teacher', ''),
                        'conflict_slots': existing
                    })
                    break
    return conflicts


def check_record_conflicts(classroom, date_str, time_slots_30min, usage_type=None, new_used_seats=0, total_seats=0):
    """检查给定30分钟时段列表是否与已有使用记录冲突

    规则：
    - 上课/讲座/考试/会议：互斥，不能覆盖彼此
    - 自习/其他：不能覆盖上课/讲座/考试/会议，只能共享座位池

    返回: (record_conflicts, remaining_seats)
      record_conflicts: 优先级类型冲突列表
      remaining_seats: 剩余座位数（仅自习/其他时有效，-1表示有优先级冲突无需检查）
    """
    record_conflicts = []
    remaining_seats = -1  # 默认-1表示无需检查座位

    # 检查时段重叠的优先级类型记录
    priority_conflict_groups = {}
    for r in st.session_state.records:
        if r.get('classroom') != classroom or r.get('date') != date_str:
            continue
        if r.get('usage_type') not in PRIORITY_TYPES:
            continue  # 只有优先级类型才算硬冲突
        for rec_slot in r.get('time_slots', []):
            rs, re = rec_slot.split('-')
            rs_min, re_min = parse_time(rs), parse_time(re)
            for sel_slot in time_slots_30min:
                ss, se = sel_slot.split('-')
                ss_min, se_min = parse_time(ss), parse_time(se)
                if ss_min < re_min and rs_min < se_min:
                    key = (r.get('user_name', ''), r.get('usage_type', ''), r.get('course_name', ''))
                    if key not in priority_conflict_groups:
                        priority_conflict_groups[key] = set()
                    priority_conflict_groups[key].add(rec_slot)

    # 无论什么类型，只要有优先级冲突就返回
    if priority_conflict_groups:
        record_conflicts = [
            {'user_name': k[0], 'usage_type': k[1], 'course_name': k[2], 'conflict_slots': sorted(v)}
            for k, v in priority_conflict_groups.items()
        ]
        return record_conflicts, -1  # 有优先级冲突，不检查座位

    # 无优先级冲突，自习/其他检查剩余座位
    if usage_type not in PRIORITY_TYPES and total_seats > 0:
        min_remaining = total_seats  # 初始化为总座位数
        for sel_slot in time_slots_30min:
            used = 0
            for r in st.session_state.records:
                if r.get('classroom') != classroom or r.get('date') != date_str:
                    continue
                if r.get('usage_type') in PRIORITY_TYPES:
                    continue  # 优先级类型不占座位池
                for rec_slot in r.get('time_slots', []):
                    rs, re = rec_slot.split('-')
                    rs_min, re_min = parse_time(rs), parse_time(re)
                    ss, se = sel_slot.split('-')
                    ss_min, se_min = parse_time(ss), parse_time(se)
                    if ss_min < re_min and rs_min < se_min:
                        used += r.get('used_seats', 0)
                        break  # 同一条记录只算一次
            remaining = total_seats - used
            min_remaining = min(min_remaining, remaining)
        remaining_seats = min_remaining

    return record_conflicts, remaining_seats


def is_room_available(classroom, date, time_slot):
    """检查教室是否空闲（时间段重叠判断，排课或使用记录都不存在才算空闲）
    优先级：排课 > 上课/讲座/考试/会议 > 自习/其他
    """
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        weekday = WEEKDAYS[date_obj.weekday()]
    except:
        return True, "未知", None

    slot_start_str, slot_end_str = time_slot.split('-')
    slot_start = parse_time(slot_start_str)
    slot_end = parse_time(slot_end_str)

    # 检查排课：遍历所有排课，时段有重叠即为占用
    for s in st.session_state.schedules:
        if s.get('classroom') == classroom and s.get('weekday') == weekday:
            for sched_slot in s.get('time_slots', []):
                ss, se = sched_slot.split('-')
                ss_min, se_min = parse_time(ss), parse_time(se)
                if slot_start < se_min and ss_min < slot_end:
                    return False, "排课", s

    # 检查使用记录：优先级类型优先返回
    priority_records = []
    seat_records = []
    for r in st.session_state.records:
        if r.get('classroom') == classroom and r.get('date') == date:
            for rec_slot in r.get('time_slots', []):
                rs, re = rec_slot.split('-')
                rs_min, re_min = parse_time(rs), parse_time(re)
                if slot_start < re_min and rs_min < slot_end:
                    if r.get('usage_type') in PRIORITY_TYPES:
                        priority_records.append(r)
                    else:
                        seat_records.append(r)
                    break  # 同一条记录只算一次

    # 有上课/讲座/考试/会议 → 直接显示（覆盖自习/其他）
    if priority_records:
        return False, "使用中", priority_records[0]

    # 只有自习/其他 → 显示占用+剩余座位
    if seat_records:
        return False, "使用中", seat_records[0]

    return True, "空闲", None


def get_total_used_seats(classroom, date, time_slot):
    """计算教室在指定日期时段的共享座位池已用数（仅自习/其他，不含上课/讲座/考试/会议）"""
    slot_start_str, slot_end_str = time_slot.split('-')
    slot_start = parse_time(slot_start_str)
    slot_end = parse_time(slot_end_str)
    total_used = 0
    for r in st.session_state.records:
        if r.get('classroom') == classroom and r.get('date') == date:
            if r.get('usage_type') in PRIORITY_TYPES:
                continue  # 上课/讲座/考试/会议不占共享座位池
            for rec_slot in r.get('time_slots', []):
                rs, re = rec_slot.split('-')
                rs_min, re_min = parse_time(rs), parse_time(re)
                if slot_start < re_min and rs_min < slot_end:
                    total_used += r.get('used_seats', 0)
                    break  # 同一条记录只算一次
    return total_used


def get_current_time_slot():
    """获取当前时间段"""
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute

    for slot in CLASS_TIME_OPTIONS:
        start_str, end_str = slot.split('-')
        start_h, start_m = map(int, start_str.split(':'))
        end_h, end_m = map(int, end_str.split(':'))
        start_min = start_h * 60 + start_m
        end_min = end_h * 60 + end_m

        if start_min <= current_minutes < end_min:
            return slot, WEEKDAYS[now.weekday()], now.strftime('%Y-%m-%d')

    return None, WEEKDAYS[now.weekday()], now.strftime('%Y-%m-%d')


def get_current_time_slot_10min():
    """获取当前10分钟时段（记录使用）"""
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    for slot in SLOT_10MIN:
        start_str, end_str = slot.split('-')
        sh = int(start_str.split(':')[0]);
        sm = int(start_str.split(':')[1])
        eh = int(end_str.split(':')[0]);
        em = int(end_str.split(':')[1])
        if sh * 60 + sm <= current_minutes < eh * 60 + em:
            return slot
    return None


def get_current_time_slot_30min():
    """获取当前30分钟时段（空闲查询）"""
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    for slot in SLOT_30MIN:
        start_str, end_str = slot.split('-')
        sh = int(start_str.split(':')[0]);
        sm = int(start_str.split(':')[1])
        eh = int(end_str.split(':')[0]);
        em = int(end_str.split(':')[1])
        if sh * 60 + sm <= current_minutes < eh * 60 + em:
            return slot
    return None


def generate_mock_schedule():
    """生成符合客观实际的模拟排课数据"""
    schedules = []

    for classroom in st.session_state.classrooms:
        cr_name = classroom['name']
        cr_type = classroom.get('type', '普通教室')

        # 计算机房优先排实验课
        # 阶梯教室优先排大班公共课
        # 其他普通教室随机排各类课程

        for weekday in WEEKDAYS_SHORT:  # 周一到周五
            # 周一到周五全部时段（上午4节 + 下午4节 + 晚上2节 = 10节）
            available_periods = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

            # 随机选择1-4个时段有课
            num_classes = random.randint(1, 4)
            selected_periods = random.sample(available_periods, min(num_classes, len(available_periods)))

            for period_idx in selected_periods:
                slot = CLASS_TIME_OPTIONS[period_idx]

                # 选择课程类型和名称
                if cr_type == "计算机房":
                    course_type = "实验课"
                elif cr_type == "阶梯教室":
                    course_type = random.choice(["公共课", "专业课"])
                else:
                    course_type = random.choice(list(COURSE_NAMES.keys()))

                course_name = random.choice(COURSE_NAMES[course_type])
                teacher = random.choice(TEACHER_NAMES)

                schedule = {
                    'id': f"sch_{cr_name}_{weekday}_{period_idx}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    'classroom': cr_name,
                    'weekday': weekday,
                    'time_slots': [slot],
                    'course_name': course_name,
                    'course_type': course_type,
                    'teacher': teacher,
                    'semester': '2026春季'
                }
                schedules.append(schedule)

    return schedules


load_data()

# ====== 全局 UI 样式优化 (双模兼容稳重版) ======
st.markdown("""
<style>
/* 1. 全局字体与主容器间距 */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
}
.block-container { padding-top: 2rem !important; padding-bottom: 2rem !important; max-width: 95% !important; }

/* 🌟 2. 精准隐藏 Deploy 按钮，但【保留右侧设置菜单】，恢复暗色模式！ */
.stDeployButton, [data-testid="stAppDeployButton"] { display: none !important; }
header[data-testid="stHeader"] { background-color: transparent !important; box-shadow: none !important; }

/* 3. 侧边栏高级排版 */
section[data-testid="stSidebar"] { border-right: 1px solid var(--faded-text05); }
section[data-testid="stSidebar"] > div:first-child { padding-top: 1.5rem; }

/* 4. 数据卡片双模动态自适应 (剥离回弹动画) */
[data-testid="stMetric"], [data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {
    background-color: var(--secondary-background-color);
    border-radius: 12px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.04);
    border: 1px solid var(--faded-text05);
}
[data-testid="stMetric"] { padding: 20px 24px !important; border-top: 4px solid #4A90D9; }
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] { padding: 16px; margin-bottom: 1.5rem; }
[data-testid="stMetricLabel"] { font-size: 0.9rem !important; font-weight: 500 !important; color: var(--text-color); opacity: 0.8; margin-bottom: 0.5rem; }
[data-testid="stMetricValue"] { font-size: 2.2rem !important; font-weight: 700 !important; color: var(--text-color); }

/* 5. 胶囊分段导航 (保留高极感，去除物理位移动画) */
div[data-testid="stRadio"] { margin-bottom: 1rem; }
div[data-testid="stRadio"] > div {
    background-color: var(--secondary-background-color);
    padding: 4px !important;
    border-radius: 10px;
    display: inline-flex !important;
    gap: 4px;
    border: 1px solid var(--faded-text05);
}
div[data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child { display: none !important; }
div[data-testid="stRadio"] label {
    padding: 8px 20px !important;
    border-radius: 6px !important;
    margin: 0 !important;
    cursor: pointer;
    background-color: transparent;
}
div[data-testid="stRadio"] label[data-checked="true"] {
    background-color: var(--background-color) !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05), 0 0 0 1px var(--faded-text05);
    color: #4A90D9 !important;
}
div[data-testid="stRadio"] label[data-checked="true"] p { font-weight: 600 !important; }

/* 6. 现代 UI：提示框左侧强调线 */
[data-testid="stAlert"] {
    border: none !important;
    background-color: var(--secondary-background-color) !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
    border-radius: 4px 8px 8px 4px !important;
}
[data-testid="stAlert"][data-baseweb="notification"]:has(svg[data-testid="stIconInfo"]) { border-left: 4px solid #4A90D9 !important; }
[data-testid="stAlert"][data-baseweb="notification"]:has(svg[data-testid="stIconSuccess"]) { border-left: 4px solid #2ECC71 !important; }
[data-testid="stAlert"][data-baseweb="notification"]:has(svg[data-testid="stIconWarning"]) { border-left: 4px solid #F1C40F !important; }
[data-testid="stAlert"][data-baseweb="notification"]:has(svg[data-testid="stIconError"]) { border-left: 4px solid #E74C3C !important; }

/* 7. 细节微调 */
hr { margin-top: 1rem !important; margin-bottom: 1rem !important; border-color: var(--faded-text05); }
[data-testid="stVerticalBlock"] { gap: 0.2rem !important; }
[data-testid="stVerticalBlock"] > div { padding-top: 0 !important; padding-bottom: 0 !important; }
</style>
""", unsafe_allow_html=True)
st.sidebar.title("🏫 教室空位管理系统")
st.sidebar.markdown("---")

## 1. 极简版主导航菜单（将所有统计分析功能打包收纳）
page = st.sidebar.radio(
    "功能导航",
    ["📊 仪表盘", "🔍 空闲查询", "📝 记录使用", "🔬 深度统计分析", "📋 报告导出", "⚙️ 数据源与配置"],
    index=0
)

# 2. 路由劫持 A：统计分析模块无痕展开
if page == "🔬 深度统计分析":
    st.title("🔬 深度统计分析中心")
    st.info("💡 提示：本模块汇集了多维度的空间利用率诊断与数据挖掘算法。")
    # 在这里追加 "🔮 贝叶斯空闲预测"，使其出现在评价模型的右侧
    sub_page_stat = st.radio("请选择分析模型：", ["📈 统计分析", "🔗 相关性分析", "🏆 综合评价模型", "🔮 贝叶斯空闲预测"], horizontal=True)
    st.markdown("---")
    page = sub_page_stat

# 3. 路由劫持 B：后台模块无痕展开
elif page == "⚙️ 数据源与配置":
    st.title("⚙️ 数据源与配置 (后台管理)")
    st.info("💡 提示：本模块仅供管理员进行【教室库维护】与【固定排课】。")
    # 生成横向的二级菜单
    sub_page_admin = st.radio("请选择后台维护模块：", ["🏢 教室管理", "📅 排课管理"], horizontal=True)
    st.markdown("---")
    # 重新赋值，无缝触发下方的原有代码
    page = sub_page_admin

# ====== 仪表盘 ======
if page == "📊 仪表盘":
    st.title("📊 仪表盘")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("教室总数", len(st.session_state.classrooms))
    with col2:
        st.metric("使用记录", len(st.session_state.records))
    with col3:
        st.metric("排课数量", len(st.session_state.schedules))
    with col4:
        current_slot, current_weekday, current_date = get_current_time_slot()
        available_count = 0
        for cr in st.session_state.classrooms:
            avail, _, _ = is_room_available(cr['name'], current_date, current_slot) if current_slot else (
            True, "未知", None)
            if avail:
                available_count += 1
        st.metric("当前空闲", f"{available_count}/{len(st.session_state.classrooms)}")

    st.markdown("---")

    # 当前状态概览
    if current_slot:
        st.subheader(f"📍 当前状态 ({current_weekday} {current_date} {current_slot})")

        col1, col2 = st.columns(2)
        with col1:
            st.write("**🔴 被占用的教室**")
            occupied = []
            for cr in st.session_state.classrooms:
                avail, source, info = is_room_available(cr['name'], current_date, current_slot)
                if not avail:
                    if source == "排课":
                        occupied.append(f"{cr['name']} - {info.get('course_name', '')}(排课)")
                    else:
                        occupied.append(f"{cr['name']} - {info.get('user_name', '')}({info.get('usage_type', '')})")
            if occupied:
                for item in occupied:
                    st.write(f"  • {item}")
            else:
                st.write("  无")

        with col2:
            st.write("**🟢 空闲的教室**")
            available_list = []
            for cr in st.session_state.classrooms:
                avail, _, _ = is_room_available(cr['name'], current_date, current_slot)
                if avail:
                    available_list.append(f"{cr['name']} ({cr.get('total_seats', 0)}座)")
            if available_list:
                for item in available_list:
                    st.write(f"  • {item}")
            else:
                st.write("  无")

    st.markdown("---")

    # 最近记录
    if st.session_state.records:
        recent = sorted(st.session_state.records, key=lambda x: x.get('created_at', ''), reverse=True)[:10]
        st.subheader("📝 最近使用记录")
        for r in recent:
            slots = ', '.join(r.get('time_slots', [])) if r.get('time_slots') else r.get('time_slot', '-')
            st.write(
                f"**{r.get('date', '')}** | {r.get('classroom', '')} | {r.get('user_name', '')} | {r.get('usage_type', '')}")
            st.caption(f"时段: {slots}")

    st.markdown("---")

    # 使用趋势
    if len(st.session_state.records) >= 2:
        st.subheader("📈 使用趋势")
        usage_by_date = {}
        for r in st.session_state.records:
            d = r.get('date', '')
            if d:
                usage_by_date[d] = usage_by_date.get(d, 0) + 1

        if usage_by_date:
            dates = sorted(usage_by_date.keys())[-14:]
            counts = [usage_by_date[d] for d in dates]

            # --- 优化点 1：将日期截断，去掉年份（如 2026-04-24 变为 04-24），极大节省横向空间 ---
            short_dates = [d[5:] for d in dates]
            chart_data = pd.DataFrame({'日期': short_dates, '使用次数': counts})

            # --- 优化点 2：使用 Plotly 替代原生折线图，支持数据点悬停显示和高级排版 ---
            fig_trend = px.line(
                chart_data,
                x='日期',
                y='使用次数',
                markers=True,  # 显示数据圆点
                color_discrete_sequence=['#4A90D9']
            )

            fig_trend.update_layout(
                xaxis=dict(
                    tickangle=0,  # 强制刻度文字 0度绝对水平
                    type='category',  # 保持日期的顺序不被打乱
                    title=''  # 隐藏下方多余的“日期”两个字
                ),
                yaxis=dict(title='', rangemode='tozero'),  # Y轴从0开始
                margin=dict(l=0, r=20, t=30, b=0),
                height=350,
                plot_bgcolor='white'
            )

            # 增加水平虚线网格，提升可读性
            fig_trend.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#f0f0f0')

            st.plotly_chart(fig_trend, use_container_width=True)

# ====== 教室管理 ======
elif page == "🏢 教室管理":
    st.subheader("🏢 教室管理")

    if st.session_state.get('_success_msg'):
        st.success(st.session_state['_success_msg'])
        st.session_state['_success_msg'] = ''

    tab1, tab2, tab3 = st.tabs(["➕ 添加教室", "✏️ 编辑教室", "🎲 随机教室"])

    with tab1:
        with st.form("add_classroom_form"):
            col1, col2 = st.columns(2)

            with col1:
                classroom_name = st.text_input("教室名称 *", placeholder="例如: A101")
                building = st.text_input("所在楼栋", placeholder="例如: 教学楼A")
                total_seats = st.number_input("座位总数 *", min_value=1, max_value=500, value=60)

            with col2:
                classroom_type = st.selectbox("教室类型",
                                              ["普通教室", "多媒体教室", "计算机房", "实验室", "阶梯教室"])
                floor = st.number_input("楼层", min_value=1, max_value=30, value=1)
                has_projector = st.checkbox("配备投影仪")
                has_computer = st.checkbox("配备电脑")

            notes = st.text_area("备注", placeholder="其他说明...")

            submitted = st.form_submit_button("添加教室", type="primary")

            if submitted:
                if not classroom_name:
                    st.error("请输入教室名称")
                elif any(c['name'] == classroom_name for c in st.session_state.classrooms):
                    st.error("该教室已存在")
                else:
                    new_classroom = {
                        'name': classroom_name,
                        'building': building,
                        'floor': floor,
                        'total_seats': total_seats,
                        'type': classroom_type,
                        'has_projector': has_projector,
                        'has_computer': has_computer,
                        'notes': notes,
                        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    st.session_state.classrooms.append(new_classroom)
                    save_data()
                    st.session_state['_success_msg'] = f"✅ 教室 {classroom_name} 添加成功！"
                    st.rerun()

    with tab2:
        if not st.session_state.classrooms:
            st.info("暂无教室")
        else:
            selected_name = st.selectbox("选择教室",
                                         sort_classroom_names([c['name'] for c in st.session_state.classrooms]))
            selected_classroom = next((c for c in st.session_state.classrooms if c['name'] == selected_name), None)

            if selected_classroom:
                with st.form("edit_classroom_form"):
                    col1, col2 = st.columns(2)

                    with col1:
                        new_name = st.text_input("教室名称 *", value=selected_classroom.get('name', ''))
                        new_building = st.text_input("所在楼栋", value=selected_classroom.get('building', ''))
                        new_total_seats = st.number_input("座位总数 *", min_value=1, max_value=500,
                                                          value=selected_classroom.get('total_seats', 60))

                    with col2:
                        current_type = selected_classroom.get('type', '普通教室')
                        type_options = ["普通教室", "多媒体教室", "计算机房", "实验室", "阶梯教室"]
                        type_index = type_options.index(current_type) if current_type in type_options else 0
                        new_type = st.selectbox("教室类型", type_options, index=type_index)
                        new_floor = st.number_input("楼层", min_value=1, max_value=30,
                                                    value=selected_classroom.get('floor', 1))
                        new_has_projector = st.checkbox("配备投影仪",
                                                        value=selected_classroom.get('has_projector', False))
                        new_has_computer = st.checkbox("配备电脑",
                                                       value=selected_classroom.get('has_computer', False))

                    new_notes = st.text_area("备注", value=selected_classroom.get('notes', ''))

                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        save_submitted = st.form_submit_button("💾 保存修改", type="primary")
                    with col_btn2:
                        delete_submitted = st.form_submit_button("🗑️ 删除教室", type="secondary")

                    if save_submitted:
                        if not new_name:
                            st.error("教室名称不能为空")
                        else:
                            for i, c in enumerate(st.session_state.classrooms):
                                if c['name'] == selected_name:
                                    st.session_state.classrooms[i] = {
                                        'name': new_name,
                                        'building': new_building,
                                        'floor': new_floor,
                                        'total_seats': new_total_seats,
                                        'type': new_type,
                                        'has_projector': new_has_projector,
                                        'has_computer': new_has_computer,
                                        'notes': new_notes,
                                        'created_at': c.get('created_at', ''),
                                        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    }
                                    break

                            for r in st.session_state.records:
                                if r.get('classroom') == selected_name:
                                    r['classroom'] = new_name

                            save_data()
                            st.success("✅ 教室信息已更新！")
                            st.rerun()

                    if delete_submitted:
                        st.session_state.classrooms = [c for c in st.session_state.classrooms if
                                                       c['name'] != selected_name]
                        st.session_state.records = [r for r in st.session_state.records if
                                                    r.get('classroom') != selected_name]
                        save_data()
                        st.success(f"✅ 教室 {selected_name} 已删除")
                        st.rerun()

    with tab3:
        st.subheader("🎲 随机生成教室")
        st.info("💡 自动生成符合实际情况的教室数据")

        st.write("**生成规则：**")
        st.write("• 教学楼A/B/C，每楼3-5层")
        st.write("• 每层2-5间教室")
        st.write("• 座位数：普通教室40-80，多媒体60-100，阶梯教室100-200，计算机房30-50，实验室20-40")
        st.write("• 类型分布：普通教室50%，多媒体20%，计算机房10%，实验室10%，阶梯教室10%")

        num_rooms = st.number_input("生成教室数量", min_value=1, max_value=100, value=10, key="random_rooms_count")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🎲 生成随机教室", type="primary", key="gen_random_rooms"):
                # 教学楼列表
                buildings = ["教学楼A", "教学楼B", "教学楼C"]

                # 课程类型和对应座位范围
                type_seat_ranges = {
                    "普通教室": (40, 80),
                    "多媒体教室": (60, 100),
                    "计算机房": (30, 50),
                    "实验室": (20, 40),
                    "阶梯教室": (100, 200)
                }

                # 类型权重（符合实际情况）
                type_weights = [50, 20, 10, 10, 10]  # 普通50%, 多媒体20%, 机房10%, 实验室10%, 阶梯10%
                type_names = list(type_seat_ranges.keys())

                # 收集已存在的教室名
                existing_names = set(c['name'] for c in st.session_state.classrooms)

                new_rooms = []
                added = 0

                for _ in range(num_rooms * 3):  # 多尝试几次避免重名
                    if added >= num_rooms:
                        break

                    building = random.choice(buildings)
                    floor = random.randint(1, 5)
                    room_num = random.randint(1, 10)

                    name = f"{building[-1]}{floor}{room_num:02d}"  # 如 A301, B205

                    if name in existing_names:
                        continue

                    existing_names.add(name)

                    cr_type = random.choices(type_names, weights=type_weights)[0]
                    seat_min, seat_max = type_seat_ranges[cr_type]
                    total_seats = random.randint(seat_min, seat_max)

                    new_room = {
                        'name': name,
                        'building': building,
                        'floor': floor,
                        'total_seats': total_seats,
                        'type': cr_type,
                        'has_projector': cr_type in ["多媒体教室", "阶梯教室"],
                        'has_computer': cr_type == "计算机房",
                        'notes': '',
                        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    new_rooms.append(new_room)
                    added += 1

                st.session_state.classrooms.extend(new_rooms)
                save_data()
                st.session_state['_success_msg'] = f"✅ 已生成 {len(new_rooms)} 间教室！"
                st.rerun()

        with col_btn2:
            if st.button("🗑️ 清空所有教室", key="clear_rooms"):
                st.session_state.classrooms = []
                st.session_state.records = []
                st.session_state.schedules = []
                save_data()
                st.success("已清空所有教室及相关记录")
                st.rerun()

    if st.session_state.classrooms:
        st.markdown("---")
        st.subheader(f"📋 已有教室（共 {len(st.session_state.classrooms)} 间）")
        _classrooms_sorted = sorted(st.session_state.classrooms,
                                    key=lambda c: (0 if c['name'] and c['name'][0].isalpha() else 1, c['name'].lower()))
        df_classrooms = pd.DataFrame(_classrooms_sorted)
        display_cols = ['name', 'building', 'floor', 'total_seats', 'type']
        st.dataframe(df_classrooms[[c for c in display_cols if c in df_classrooms.columns]],
                     width=1200, hide_index=True)

# ====== 排课管理 ======
elif page == "📅 排课管理":
    st.subheader("📅 排课管理")

    if st.session_state.get('_success_msg'):
        st.success(st.session_state['_success_msg'])
        st.session_state['_success_msg'] = ''

    tab1, tab2, tab3 = st.tabs(["📝 添加排课", "📋 排课列表", "🎲 模拟排课"])

    with tab1:
        if not st.session_state.classrooms:
            st.warning("暂无教室，请先在「教室管理」中添加教室")
        else:
            with st.form("add_schedule_form"):
                st.subheader("添加排课")

                col1, col2 = st.columns(2)
                with col1:
                    schedule_classroom = st.selectbox("选择教室 *", sort_classroom_names(
                        [c['name'] for c in st.session_state.classrooms]))
                    weekday = st.selectbox("星期 *", WEEKDAYS_SHORT)

                with col2:
                    course_name = st.text_input("课程名称 *", placeholder="例如：高等数学")
                    teacher = st.text_input("授课教师 *", placeholder="例如：王教授")
                    course_type = st.selectbox("课程类型", SCHEDULE_TYPES)

                st.write(f"**选择时段 *（可多选）**")
                selected_slots = st.multiselect("选择时段", CLASS_TIME_OPTIONS)

                submitted = st.form_submit_button("添加排课", type="primary")

                if submitted:
                    if not course_name or not teacher:
                        st.error("请填写完整信息")
                    elif not selected_slots:
                        st.error("请至少选择一个时段")
                    else:
                        # 检查冲突
                        conflicts = []
                        for slot in selected_slots:
                            scheduled, info = is_room_scheduled(schedule_classroom, weekday, slot)
                            if scheduled:
                                conflicts.append(f"{slot}（已有：{info.get('course_name', '')}）")

                        if conflicts:
                            st.error("⚠️ 与已有排课冲突：")
                            for c in conflicts:
                                st.write(f"  - {c}")
                        else:
                            for slot in selected_slots:
                                schedule = {
                                    'id': f"sch_{schedule_classroom}_{weekday}_{slot}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                                    'classroom': schedule_classroom,
                                    'weekday': weekday,
                                    'time_slots': [slot],
                                    'course_name': course_name,
                                    'course_type': course_type,
                                    'teacher': teacher,
                                    'semester': '2026春季'
                                }
                                st.session_state.schedules.append(schedule)

                            save_data()
                            st.session_state[
                                '_success_msg'] = f"✅ 排课成功！{schedule_classroom} {weekday} {course_name}"
                            st.rerun()

    with tab2:
        st.subheader("📋 排课列表")

        if not st.session_state.schedules:
            st.info("暂无排课")
        else:
            # 按星期和教室分组显示
            df_schedules = pd.DataFrame(st.session_state.schedules)
            if not df_schedules.empty:
                df_schedules['时段'] = df_schedules['time_slots'].apply(
                    lambda x: ', '.join(x) if isinstance(x, list) else x)
                display_df = df_schedules[['classroom', 'weekday', '时段', 'course_name', 'teacher', 'course_type']]
                display_df.columns = ['教室', '星期', '时段', '课程', '教师', '类型']

                # 排序
                weekday_order = {w: i for i, w in enumerate(WEEKDAYS_SHORT)}
                display_df['排序'] = display_df['星期'].map(weekday_order)
                display_df = display_df.sort_values(['排序', '教室', '时段'])
                display_df = display_df.drop('排序', axis=1)

                st.dataframe(display_df, width=1200, hide_index=True)

                st.markdown("---")

                # 删除功能
                # 为每条排课生成唯一标识用于删除
                delete_options = {}
                for idx, s in enumerate(st.session_state.schedules):
                    slots_str = ', '.join(s.get('time_slots', [])) if isinstance(s.get('time_slots'), list) else str(
                        s.get('time_slots', ''))
                    key = f"{s.get('classroom', '')} | {s.get('weekday', '')} | {s.get('course_name', '')} | {slots_str}"
                    delete_options[key] = idx

                selected_delete = st.multiselect("选择要删除的排课（选中后将显示序号，点击确认删除）",
                                                 list(delete_options.keys()))

                if selected_delete and st.button("确认删除", type="primary"):
                    indices_to_delete = sorted([delete_options[k] for k in selected_delete], reverse=True)
                    for idx in indices_to_delete:
                        st.session_state.schedules.pop(idx)
                    save_data()
                    st.success(f"已删除 {len(indices_to_delete)} 条排课")
                    st.rerun()

                    save_data()
                    st.success(f"已删除 {delete_count} 条排课")
                    st.rerun()

    with tab3:
        st.subheader("🎲 模拟排课")
        st.info("💡 根据教室类型和课程特点，自动生成符合客观实际的排课数据")

        st.write("**生成规则：**")
        st.write("• 周一至周五排课")
        st.write("• 上午8:00-12:00，下午14:00-18:00，晚上18:00-19:40")
        st.write("• 每大节两小节连上（45分钟/小节，10分钟课间，20分钟大课间）")
        st.write("• 计算机房优先排实验课，阶梯教室优先排大班公共课")

        if st.button("🎲 生成模拟排课", type="primary"):
            if not st.session_state.classrooms:
                st.warning("请先添加教室")
            else:
                # 清空旧排课
                st.session_state.schedules = []

                # 生成新排课
                mock_schedules = generate_mock_schedule()
                st.session_state.schedules.extend(mock_schedules)

                save_data()
                st.success(f"✅ 已生成 {len(mock_schedules)} 条模拟排课！")
                st.rerun()

        if st.button("🗑️ 清空所有排课"):
            st.session_state.schedules = []
            save_data()
            st.success("已清空所有排课")
            st.rerun()

# ====== 空闲查询 ======
elif page == "🔍 空闲查询":
    st.title("🔍 教室空闲查询")

    # 提前获取当前时间状态，用于后续判断
    current_30min = get_current_time_slot_30min()
    current_date_str = datetime.now().strftime('%Y-%m-%d')

    # 将比例调整为 1:1，让左右输入框对齐
    col_date, col_slot = st.columns(2)

    with col_date:
        query_date = st.date_input("查询日期", datetime.now())
        query_date_str = query_date.strftime('%Y-%m-%d')
        query_weekday = WEEKDAYS[query_date.weekday()]
        st.caption(f"星期：{query_weekday}")

        # 将“当前时段”提示框移动到左侧，放在日期下方
        if query_date_str == current_date_str and current_30min:
            st.success(f"📍 当前时段：{current_30min}")
        elif query_date_str == current_date_str:
            st.warning("⏰ 当前不在可选时段内，请手动选择")

    # 默认选中当前时段（当天）
    default_idx = 0
    if query_date_str == current_date_str and current_30min:
        try:
            default_idx = SLOT_30MIN.index(current_30min)
        except ValueError:
            default_idx = 0

    with col_slot:
        # 下拉框现在与左侧的查询日期完全平行
        selected_query_slot = st.selectbox("选择时段", SLOT_30MIN, index=default_idx)

    st.markdown("---")

    if not st.session_state.classrooms:
        st.warning("暂无教室数据")
    else:
        # 排序后的教室列表
        _sorted_classrooms = sorted(st.session_state.classrooms,
                                    key=lambda c: (0 if c['name'] and c['name'][0].isalpha() else 1, c['name'].lower()))

        # 统计 + 筛选器同一行
        available_count = 0
        occupied_count = 0

        for cr in _sorted_classrooms:
            avail, _, _ = is_room_available(cr['name'], query_date_str, selected_query_slot)
            if avail:
                available_count += 1
            else:
                occupied_count += 1

        col_metric1, col_metric2, col_filter = st.columns([1, 1, 2])
        with col_metric1:
            st.metric("🟢 空闲教室", available_count)
        with col_metric2:
            st.metric("🔴 占用教室", occupied_count)
        with col_filter:
            st.write("")
            filter_mode = st.radio("筛选", ["全部", "只看空闲", "只看占用"], horizontal=True, index=0,
                                   label_visibility="collapsed")

        # 教室状态列表（排序后）
        _sorted_classrooms = sorted(st.session_state.classrooms,
                                    key=lambda c: (0 if c['name'] and c['name'][0].isalpha() else 1, c['name'].lower()))
        classroom_status = []
        for cr in _sorted_classrooms:
            avail, source, info = is_room_available(cr['name'], query_date_str, selected_query_slot)

            status_text = "🟢 空闲" if avail else "🔴 占用"
            detail_text = ""
            detail_type = ""

            if not avail:
                if source == "排课":
                    detail_text = f"{info.get('course_name', '')}（{info.get('teacher', '')}）"
                    detail_type = "排课"
                elif info.get('usage_type') in PRIORITY_TYPES:
                    ut = info.get('usage_type', '')
                    if ut == '上课':
                        course = info.get('course_name', '').strip()
                        detail_text = f"{course}（{info.get('user_name', '')}）" if course else "有人上课"
                    elif ut == '考试':
                        course = info.get('course_name', '').strip()
                        detail_text = f"考试：{course}" if course else "有人考试"
                    elif ut == '讲座':
                        org = info.get('organizer', '').strip()
                        detail_text = f"讲座：{org}" if org else "有人讲座"
                    elif ut == '会议':
                        org = info.get('organizer', '').strip()
                        detail_text = f"会议：{org}" if org else "有人会议"
                    else:
                        detail_text = f"有人{ut}"
                    detail_type = ut
                else:
                    total = cr.get('total_seats', 0)
                    used = get_total_used_seats(cr['name'], query_date_str, selected_query_slot)
                    remain = max(0, total - used)
                    detail_text = f"有人自习（剩余{remain}个位置）"
                    detail_type = "自习"

            classroom_status.append({
                '教室': cr['name'],
                '楼栋': cr.get('building', ''),
                '座位': cr.get('total_seats', 0),
                '类型': cr.get('type', ''),
                '状态': status_text,
                '详情': detail_text,
                '来源': source if source else '空闲'
            })

        df_status = pd.DataFrame(classroom_status)

        if filter_mode == "只看空闲":
            df_filtered = df_status[df_status['状态'] == '🟢 空闲']
        elif filter_mode == "只看占用":
            df_filtered = df_status[df_status['状态'] == '🔴 占用']
        else:
            df_filtered = df_status

        st.dataframe(df_filtered, width=1200, hide_index=True)

# ====== 记录使用 ======
elif page == "📝 记录使用":
    st.title("📝 记录使用")

    # 显示上次操作成功提示
    if st.session_state.get('_success_msg'):
        st.success(st.session_state['_success_msg'])
        st.session_state['_success_msg'] = ''

    tab1, tab2, tab3, tab4 = st.tabs(["📝 单条录入", "📋 批量录入", "🗑️ 管理记录", "🎲 随机记录"])

    with tab1:
        if not st.session_state.classrooms:
            st.warning("暂无教室，请先在「教室管理」中添加")
        else:
            if 'current_slots' not in st.session_state:
                st.session_state.current_slots = []

            # 压缩表单间距
            st.markdown("""
            <style>
            .stForm > div > div > div { padding-top: 0.3rem !important; padding-bottom: 0.3rem !important; }
            .stForm label { font-size: 0.9rem !important; }
            </style>
            """, unsafe_allow_html=True)


            # ===== 时段辅助函数 =====
            def fmt_slot(date_str, start_h, start_m, end_h, end_m):
                return f"{date_str} {start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}"


            def build_slot(date_str, sh, sm, eh, em):
                return fmt_slot(date_str, sh, sm, eh, em)


            with st.form("add_record_form"):
                # ---- 第一行：教室 + 日期 + 姓名 + 类型 ----
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    record_classroom = st.selectbox("教室 *", sort_classroom_names(
                        [c['name'] for c in st.session_state.classrooms]))
                with c2:
                    record_date = st.date_input("日期 *", datetime.now())
                    record_date_str = record_date.strftime("%Y-%m-%d")
                    weekday = WEEKDAYS[record_date.weekday()]
                with c3:
                    user_name = st.text_input("姓名 *", placeholder="张同学")
                with c4:
                    usage_type = st.selectbox("类型 *", USAGE_TYPES)

                # ---- 第二行：课程 + 组织 + 座位数 ----
                c5, c6, c7 = st.columns([2, 2, 1])
                with c5:
                    course_name = st.text_input("课程名称", placeholder="上课/考试填写")
                with c6:
                    organizer = st.text_input("组织单位", placeholder="讲座/会议填写")
                with c7:
                    classroom = next((c for c in st.session_state.classrooms if c['name'] == record_classroom), None)
                    total_seats = classroom.get('total_seats', 0) if classroom else 0
                    used_seats = st.number_input(
                        f"座位/{total_seats}座",
                        min_value=1, max_value=max(1, total_seats),
                        value=min(1, max(1, total_seats))
                    )

                # ---- 时段选择 ----
                st.caption("🕐 时段选择")
                time_col0, time_col1, time_col2, time_col3, time_col4, time_col5 = st.columns([1, 1, 0.5, 1, 1, 1])

                hour_options = [f"{h:02d}" for h in range(8, 22)]
                min_options = [f"{m:02d}" for m in range(0, 60, 10)]

                with time_col0:
                    sh = int(st.selectbox("开始时", hour_options, index=0, label_visibility="collapsed"))
                with time_col1:
                    sm = int(st.selectbox("开始分", min_options, index=0, label_visibility="collapsed"))
                with time_col2:
                    st.markdown("<div style='text-align:center; padding-top:8px; color:gray;'>至</div>",
                                unsafe_allow_html=True)
                with time_col3:
                    eh = int(st.selectbox("结束时", hour_options, index=0, label_visibility="collapsed"))
                with time_col4:
                    em = int(st.selectbox("结束分", min_options, index=0, label_visibility="collapsed"))
                with time_col5:
                    st.write("")
                    add_clicked = st.form_submit_button("➕ 加入")

                if add_clicked:
                    start_total = sh * 60 + sm
                    end_total = eh * 60 + em
                    if end_total <= start_total:
                        st.error("结束时间必须晚于开始时间")
                    else:
                        slot_entry = build_slot(record_date_str, sh, sm, eh, em)
                        if slot_entry not in st.session_state.current_slots:
                            st.session_state.current_slots.append(slot_entry)
                            st.success(f"已添加：{slot_entry.split(' ', 1)[1]}")
                        else:
                            st.warning("该时段已添加")
                    st.rerun()

                # ---- 备注 + 提交 ----
                notes = st.text_area("备注", placeholder="其他说明...")
                submitted = st.form_submit_button("✅ 添加记录", type="primary")

            # ---- 已选时段列表（form 外部，允许按钮操作）----
            if st.session_state.current_slots:
                st.markdown("**已选时段：**")
                to_remove = []
                slot_cols = st.columns(len(st.session_state.current_slots))
                for i, s in enumerate(st.session_state.current_slots):
                    with slot_cols[i]:
                        st.caption(s)
                        if st.button("❌", key=f"rm_{i}"):
                            to_remove.append(i)
                if to_remove:
                    for i in reversed(to_remove):
                        st.session_state.current_slots.pop(i)
                    st.rerun()
            else:
                st.info("尚未添加时段，请在上方选择开始/结束时间后点击「➕ 加入」")

            # --- 提交处理 ---
            if submitted:
                if not user_name:
                    st.error("请输入使用者姓名")
                elif not st.session_state.current_slots:
                    st.error("请至少添加一个时段")
                else:
                    time_slots_only = [s.split(' ', 1)[1] for s in st.session_state.current_slots]

                    # 检查是否有过去时间
                    now = datetime.now()
                    now_date = now.strftime('%Y-%m-%d')
                    now_min = now.hour * 60 + now.minute
                    past_slots = []
                    for slot in st.session_state.current_slots:
                        parts = slot.split(' ', 1)
                        slot_date = parts[0]
                        slot_time = parts[1]
                        end_str = slot_time.split('-')[1]
                        end_min = parse_time(end_str)
                        if slot_date < now_date or (slot_date == now_date and end_min <= now_min):
                            past_slots.append(slot_time)
                    if past_slots:
                        st.error(f"⏰ 时间已过，请重新选择时间：{', '.join(past_slots)}")
                        st.stop()

                    schedule_conflicts = check_schedule_conflicts(record_classroom, weekday, time_slots_only)
                    if schedule_conflicts:
                        shown_courses = set()
                        conflict_msgs = []
                        for c in schedule_conflicts:
                            key = c['course_name']
                            if key not in shown_courses:
                                shown_courses.add(key)
                                conflict_msgs.append(
                                    f"🔴 {c['course_name']}（{c['teacher']}）在 {', '.join(c['conflict_slots'])} 有课"
                                )
                        st.error("⚠️ 该教室已有课程安排，无法添加使用记录：")
                        for msg in conflict_msgs:
                            st.write(msg)
                        st.stop()

                    record_conflicts, remaining_seats = check_record_conflicts(
                        record_classroom, record_date_str, time_slots_only,
                        usage_type=usage_type, new_used_seats=used_seats, total_seats=total_seats
                    )
                    if record_conflicts:
                        conflict_msgs = []
                        for c in record_conflicts:
                            ut = c['usage_type']
                            cn = c.get('course_name', '').strip()
                            slots = ', '.join(c['conflict_slots'])
                            if cn:
                                conflict_msgs.append(f"🔴 {cn}（{c['user_name']}）：{ut}（{slots}）")
                            else:
                                conflict_msgs.append(f"🔴 {c['user_name']}：有人{ut}（{slots}）")
                        st.error("⚠️ 该教室在以下时段已被占用：")
                        for msg in conflict_msgs:
                            st.write(msg)
                        st.stop()

                    # 自习/其他检查座位容量（remaining_seats >= 0 表示需要检查）
                    if remaining_seats >= 0:
                        if remaining_seats == 0:
                            st.error(f"🚫 该教室已满，剩余0个座位")
                            st.stop()
                        elif remaining_seats < used_seats:
                            st.error(f"🚫 该教室剩余座位不足，剩余{remaining_seats}个座位")
                            st.stop()

                    new_record = {
                        'id': datetime.now().strftime("%Y%m%d%H%M%S%f"),
                        'classroom': record_classroom,
                        'date': record_date_str,
                        'weekday': weekday,
                        'time_slots': time_slots_only,
                        'usage_type': usage_type,
                        'user_name': user_name,
                        'course_name': course_name,
                        'organizer': organizer,
                        'used_seats': used_seats,
                        'total_seats': total_seats,
                        'notes': notes,
                        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    st.session_state.records.append(new_record)
                    slot_display = '、'.join(time_slots_only)
                    st.session_state.current_slots = []
                    save_data()
                    st.session_state[
                        '_success_msg'] = f"✅ 记录成功！{user_name} 在 {record_classroom} {record_date_str} {slot_display}"
                    st.rerun()

    with tab2:
        st.subheader("📋 批量录入")
        st.caption("💡 一次性添加多条使用记录")

        sample_slots = ", ".join(SLOT_10MIN[:5])
        batch_data = st.text_area(
            "输入记录（每行一条，格式：日期,教室,开始时间-结束时间,类型,使用者）",
            placeholder=f"2026-04-18,801,08:00-08:10,自习,张三\n2026-04-18,801,08:10-08:20,自习,李四\n\n时间段示例：{sample_slots}...",
            height=200
        )

        if st.button("批量添加", type="primary"):
            if not batch_data.strip():
                st.error("请输入数据")
            else:
                added = 0
                errors = []
                for line in batch_data.strip().split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(',')
                    if len(parts) < 5:
                        errors.append(f"格式错误: {line}")
                        continue

                    try:
                        record_date, classroom, time_slot, usage_type, user_name = (
                            parts[0].strip(), parts[1].strip(), parts[2].strip(),
                            parts[3].strip(), parts[4].strip()
                        )

                        if classroom not in [c['name'] for c in st.session_state.classrooms]:
                            errors.append(f"教室不存在: {classroom}")
                            continue

                        date_obj = datetime.strptime(record_date, '%Y-%m-%d')
                        weekday = WEEKDAYS[date_obj.weekday()]

                        cr = next((c for c in st.session_state.classrooms if c['name'] == classroom), None)
                        total_seats = cr.get('total_seats', 0) if cr else 0

                        # 过去时间验证
                        now = datetime.now()
                        now_date = now.strftime('%Y-%m-%d')
                        now_min = now.hour * 60 + now.minute
                        end_str = time_slot.split('-')[1]
                        try:
                            end_minutes = parse_time(end_str)
                            if record_date < now_date or (record_date == now_date and end_minutes <= now_min):
                                errors.append(f"时间已过: {line}")
                                continue
                        except:
                            pass

                        new_record = {
                            'id': datetime.now().strftime("%Y%m%d%H%M%S%f"),
                            'classroom': classroom,
                            'date': record_date,
                            'weekday': weekday,
                            'time_slots': [time_slot],
                            'usage_type': usage_type,
                            'user_name': user_name,
                            'used_seats': 1,
                            'total_seats': total_seats,
                            'notes': '批量导入',
                            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        st.session_state.records.append(new_record)
                        added += 1
                    except Exception as e:
                        errors.append(f"处理失败: {line} ({str(e)})")

                if added > 0:
                    save_data()
                    st.success(f"✅ 成功添加 {added} 条记录")

                if errors:
                    st.warning(f"⚠️ {len(errors)} 条出错：")
                    for e in errors[:5]:
                        st.write(f"  - {e}")

                if added > 0:
                    st.rerun()

    with tab3:
        st.subheader("🗑️ 管理记录")
        st.warning("⚠️ 删除操作不可恢复")

        if not st.session_state.records:
            st.info("暂无使用记录")
        else:
            col_filter1, col_filter2 = st.columns(2)
            with col_filter1:
                filter_classroom = st.selectbox("筛选教室", ["全部"] + sort_classroom_names(
                    [c['name'] for c in st.session_state.classrooms]))
            with col_filter2:
                filter_type = st.selectbox("筛选类型", ["全部"] + USAGE_TYPES)

            filtered = st.session_state.records.copy()
            if filter_classroom != "全部":
                filtered = [r for r in filtered if r.get('classroom') == filter_classroom]
            if filter_type != "全部":
                filtered = [r for r in filtered if r.get('usage_type') == filter_type]

            st.write(f"共 {len(filtered)} 条记录")

            # 为每条记录生成唯一标识用于删除（display -> key映射）
            delete_options = {}
            for r in filtered:
                slots = ', '.join(r.get('time_slots', [])) if r.get('time_slots') else r.get('time_slot', '')
                display = f"{r.get('date', '')} | {r.get('classroom', '')} | {r.get('user_name', '')} | {slots[:20]}"
                key = (
                r.get('date', ''), r.get('classroom', ''), r.get('user_name', ''), tuple(r.get('time_slots', [])))
                delete_options[display] = key

            selected_delete = st.multiselect("选择要删除的记录", list(delete_options.keys()))

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if selected_delete and st.button("确认删除", type="primary"):
                    delete_set = set(delete_options[k] for k in selected_delete)
                    st.session_state.records = [
                        r for r in st.session_state.records
                        if (r.get('date', ''), r.get('classroom', ''), r.get('user_name', ''),
                            tuple(r.get('time_slots', []))) not in delete_set
                    ]
                    save_data()
                    st.success(f"已删除 {len(selected_delete)} 条记录")
                    st.rerun()

            with col_btn2:
                if filter_classroom != "全部" and st.button(f"清空 {filter_classroom} 的所有记录", type="secondary"):
                    st.session_state.records = [r for r in st.session_state.records if
                                                r.get('classroom') != filter_classroom]
                    save_data()
                    st.success(f"已清空 {filter_classroom} 的所有记录")
                    st.rerun()

    # ====== 随机记录 ======
    with tab4:
        st.subheader("🎲 随机生成使用记录")
        st.info("💡 自动生成符合实际情况的使用记录数据")

        if not st.session_state.classrooms:
            st.warning("请先添加教室")
        else:
            st.markdown("**数据生成规则 (引入先验偏好)：**")
            st.markdown(
                "- **空间规模马太效应**：运用二次加权算法，大容量教室拥有更高的历史被征用概率，用于拟合真实世界对大型空间的偏好。")
            st.markdown("- **时间与频次分布**：覆盖前后7天，自动规避固定排课约束，生成符合现实峰谷特征的 30 分钟粒度记录。")
            st.markdown(
                "- **动态满座率模拟**：自习占用人数不再是固定极小值，而是随空间规模动态波动（10%-80%），贴合真实上座率。")
            st.markdown(
                "- **拥挤压力测试**：激活「符合预测门槛」时，系统将定向生成极高满座率（>70%）的极端拥挤样本，专门用于校验贝叶斯引擎的预警灵敏度。")

            gen_mode = st.radio("生成模式", ["普通随机", "符合预测门槛"], horizontal=True, key="random_gen_mode")
            st.caption("💡 预测门槛模式：确保某些教室+星期+时段组合至少有3条记录，便于测试预测功能")

            num_records = st.number_input("生成记录数量", min_value=1, max_value=200, value=20,
                                          key="random_records_count")
            st.caption("单次最多生成200条记录")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("🎲 生成随机记录", type="primary", key="gen_random_records"):
                    today = datetime.now()
                    classrooms = st.session_state.classrooms
                    _weekday_map = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

                    # 使用类型权重
                    usage_types = ["自习", "上课", "讲座", "考试", "其他"]
                    type_weights = [60, 15, 10, 10, 5]

                    # 模拟人员库
                    student_names = ["张同学", "李同学", "王同学", "刘同学", "陈同学", "杨同学", "赵同学", "周同学",
                                     "吴同学", "郑同学"]
                    teacher_names = ["张老师", "李老师", "王老师", "刘老师", "陈老师"]
                    courses = ["高等数学", "线性代数", "大学物理", "程序设计", "数据结构", "操作系统", "计算机网络"]

                    new_records = []

                    # --- 🌟 核心优化 1：为相关性分析“埋雷”（大教室高频偏好）---
                    # 按照座位数的平方构造权重，座位数越大的教室，越容易被系统抽中产生记录
                    cr_weights = [c.get('total_seats', 50) ** 2 for c in classrooms]

                    if gen_mode == "符合预测门槛":
                        # --- 🌟 核心优化 2：为预测模型“埋雷”（制造极度拥挤时段）---
                        num_groups = max(1, num_records // 5)

                        # 故意挑选全校座位数最大的几个教室来做拥挤测试样本
                        sorted_cr = sorted(classrooms, key=lambda x: x.get('total_seats', 0), reverse=True)
                        chosen_classrooms = sorted_cr[:min(num_groups, len(sorted_cr))]

                        records_per_group = max(3, num_records // num_groups)
                        remaining = num_records

                        for cr in chosen_classrooms:
                            if remaining <= 0: break
                            cr_name = cr['name']
                            cr_seats = cr.get('total_seats', 50)

                            time_slot = None
                            weekday = None
                            for _attempt in range(20):
                                _wd = random.choice(_weekday_map[:5])  # 工作日
                                start_hour = random.randint(8, 20)
                                start_min = random.choice([0, 30])
                                end_hour = start_hour + 1 if start_min == 30 else start_hour
                                end_min = 0 if start_min == 30 else 30
                                if end_hour > 21 or (end_hour == 21 and end_min > 30):
                                    end_hour, end_min = 21, 30
                                _slot = f"{start_hour:02d}:{start_min:02d}-{end_hour:02d}:{end_min:02d}"

                                has_sched, _ = is_room_scheduled(cr_name, _wd, _slot)
                                if not has_sched:
                                    time_slot = _slot
                                    weekday = _wd
                                    break

                            if time_slot is None: continue

                            group_count = min(records_per_group, remaining)

                            for i in range(group_count):
                                weeks_ago = random.randint(0, 4)
                                wd_idx = _weekday_map.index(weekday)
                                base_date = datetime(2026, 4, 20) + timedelta(days=wd_idx)
                                record_date = base_date - timedelta(weeks=weeks_ago)
                                date_str = record_date.strftime('%Y-%m-%d')

                                usage_type = random.choices(usage_types, weights=type_weights)[0]
                                if usage_type == "自习":
                                    user_name = random.choice(student_names)
                                    # 🔥 核心：故意生成极高的满座率（70%~100%），确保贝叶斯预测时标红预警
                                    used_seats = random.randint(int(cr_seats * 0.7), cr_seats)
                                    course_name, organizer = "", ""
                                elif usage_type in ["上课", "考试"]:
                                    user_name = random.choice(teacher_names)
                                    used_seats, course_name, organizer = 0, random.choice(courses), ""
                                else:
                                    user_name = random.choice(teacher_names)
                                    used_seats, course_name = 0, ""
                                    organizer = random.choice(["学生会", "团委", "教务处", "研究生院", "图书馆"])

                                new_records.append({
                                    'id': f"rec_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                                    'classroom': cr_name, 'date': date_str, 'time_slots': [time_slot],
                                    'usage_type': usage_type, 'user_name': user_name, 'course_name': course_name,
                                    'organizer': organizer, 'used_seats': used_seats, 'total_seats': cr_seats,
                                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                })
                                remaining -= 1
                    else:
                        # 普通随机模式：运用权重产生符合现实的马太效应
                        _max_attempts = num_records * 3
                        _attempt_count = 0
                        while len(new_records) < num_records and _attempt_count < _max_attempts:
                            _attempt_count += 1

                            # --- 🌟 应用刚刚设置的座位权重 ---
                            classroom = random.choices(classrooms, weights=cr_weights)[0]
                            cr_name = classroom['name']
                            cr_seats = classroom.get('total_seats', 50)

                            delta_days = random.randint(-7, 7)
                            record_date = today + timedelta(days=delta_days)
                            date_str = record_date.strftime('%Y-%m-%d')

                            try:
                                record_wd = _weekday_map[datetime.strptime(date_str, '%Y-%m-%d').weekday()]
                            except:
                                record_wd = ''

                            start_hour = random.randint(8, 20)
                            start_min = random.choice([0, 30])
                            end_hour = start_hour + 1 if start_min == 30 else start_hour
                            end_min = 0 if start_min == 30 else 30
                            if end_hour > 21 or (end_hour == 21 and end_min > 30):
                                end_hour, end_min = 21, 30
                            time_slot = f"{start_hour:02d}:{start_min:02d}-{end_hour:02d}:{end_min:02d}"

                            has_sched, _ = is_room_scheduled(cr_name, record_wd, time_slot)
                            if has_sched: continue

                            usage_type = random.choices(usage_types, weights=type_weights)[0]

                            if usage_type == "自习":
                                user_name = random.choice(student_names)
                                # 提升大教室的自习人数下限，保证评价模型里大教室的满座率得分也高
                                used_seats = random.randint(int(cr_seats * 0.1), int(cr_seats * 0.8))
                                course_name, organizer = "", ""
                            elif usage_type in ["上课", "考试"]:
                                user_name = random.choice(teacher_names)
                                used_seats, course_name, organizer = 0, random.choice(courses), ""
                            else:
                                user_name = random.choice(teacher_names)
                                used_seats, course_name = 0, ""
                                organizer = random.choice(["学生会", "团委", "教务处", "研究生院", "图书馆"])

                            new_records.append({
                                'id': f"rec_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                                'classroom': cr_name, 'date': date_str, 'time_slots': [time_slot],
                                'usage_type': usage_type, 'user_name': user_name, 'course_name': course_name,
                                'organizer': organizer, 'used_seats': used_seats, 'total_seats': cr_seats,
                                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            })

                    st.session_state.records.extend(new_records)
                    save_data()
                    st.session_state['_success_msg'] = f"✅ 已生成 {len(new_records)} 条高质量的模拟使用记录！"
                    st.rerun()

            with col_btn2:
                if st.button("🗑️ 清空所有记录", key="clear_records"):
                    st.session_state.records = []
                    save_data()
                    st.success("已清空所有使用记录")
                    st.rerun()

# ====== 统计分析 ======
elif page == "📈 统计分析":
    if not st.session_state.records:
        st.warning("暂无使用记录数据")
    else:
        # --- 🌟 核心优化：增加全局时间切片器 (Date Filter) ---
        col_date1, col_date2 = st.columns([1, 2])

        with col_date1:
            # 自动提取现有数据中的最早和最晚日期作为日历默认边界
            all_dates = []
            for r in st.session_state.records:
                if r.get('date'):
                    try:
                        all_dates.append(datetime.strptime(r['date'], '%Y-%m-%d').date())
                    except:
                        pass

            if all_dates:
                min_date = min(all_dates)
                max_date = max(all_dates)
            else:
                min_date = datetime.now().date() - timedelta(days=7)
                max_date = datetime.now().date() + timedelta(days=7)

            # 使用 date_input，允许用户框选一个时间区间
            selected_date_range = st.date_input(
                "📅 调整分析时间区间（起止）",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date
            )

        # --- 根据用户选择的时间切片，动态过滤出有效的子数据集 ---
        filtered_records = []
        if isinstance(selected_date_range, tuple) and len(selected_date_range) == 2:
            start_str = selected_date_range[0].strftime('%Y-%m-%d')
            end_str = selected_date_range[1].strftime('%Y-%m-%d')
            for r in st.session_state.records:
                if r.get('date') and start_str <= r['date'] <= end_str:
                    filtered_records.append(r)
        elif isinstance(selected_date_range, tuple) and len(selected_date_range) == 1:
            # 兼容用户只点选了一天的情况
            start_str = selected_date_range[0].strftime('%Y-%m-%d')
            for r in st.session_state.records:
                if r.get('date') == start_str:
                    filtered_records.append(r)
        else:
            filtered_records = st.session_state.records

        with col_date2:
            st.write("")  # 占位换行对齐
            st.write("")
            st.info(f"💡 当前时间切片已筛选出 **{len(filtered_records)}** 条有效记录，下方统计大屏已自动联动重绘。")

        st.markdown("---")

        # 如果选中的区间内没有任何记录，则中止渲染下方图表
        if not filtered_records:
            st.warning("⚠️ 所选时间范围内没有提取到使用记录，请调整上方的切片区间。")
        else:
            tab1, tab2, tab3, tab4 = st.tabs(["📊 概览统计", "🗓️ 时段分析", "📈 教室对比", "🔥 热力图"])

            with tab1:
                st.subheader("📊 数据概览")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("区间内使用记录", len(filtered_records))  # 联动过滤数据
                with col2:
                    st.metric("系统教室总数", len(st.session_state.classrooms))
                with col3:
                    st.metric("系统排课总数", len(st.session_state.schedules))

                st.markdown("---")

                st.write("**区间内使用类型分布**")
                type_counts = {}
                for r in filtered_records:  # 联动过滤数据
                    t = r.get('usage_type', '其他')
                    type_counts[t] = type_counts.get(t, 0) + 1

                if type_counts:
                    df_types = pd.DataFrame(list(type_counts.items()), columns=['类型', '次数'])
                    df_types = df_types.sort_values('次数', ascending=False)
                    st.dataframe(df_types, width=400, hide_index=True)

            with tab2:
                st.subheader("🗓️ 时段分析")

                slot_counts = {}
                for r in filtered_records:  # 联动过滤数据
                    for slot in r.get('time_slots', []):
                        slot_counts[slot] = slot_counts.get(slot, 0) + 1

                if slot_counts:
                    sorted_slots = sorted(slot_counts.items(), key=lambda x: x[0])

                    st.write("**时段分布动态图**")
                    chart_data = pd.DataFrame(sorted_slots, columns=['时段', '使用次数'])

                    fig_time = px.bar(
                        chart_data, x='时段', y='使用次数',
                        text_auto=True, color_discrete_sequence=['#4A90D9']
                    )
                    fig_time.update_layout(
                        xaxis=dict(tickangle=45, type='category', title=''),
                        yaxis=dict(title='', rangemode='tozero'),
                        margin=dict(l=0, r=0, t=30, b=0),
                        height=350, plot_bgcolor='white'
                    )
                    fig_time.update_traces(textposition='outside')
                    fig_time.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#f0f0f0')

                    st.plotly_chart(fig_time, use_container_width=True)

                    st.markdown("---")

                    col1, col2 = st.columns(2)
                    with col1:
                        top_slots = sorted_slots[-3:][::-1] if len(sorted_slots) >= 3 else sorted_slots[::-1]
                        st.write("**🔥 区间内高峰时段 TOP3**")
                        for i, (slot, count) in enumerate(top_slots, 1):
                            st.write(f"{i}. {slot} - {count}次")
                    with col2:
                        low_slots = sorted_slots[:3] if len(sorted_slots) >= 3 else sorted_slots
                        st.write("**🕐 区间内空闲时段 TOP3**")
                        for i, (slot, count) in enumerate(low_slots, 1):
                            st.write(f"{i}. {slot} - {count}次")

            with tab3:
                st.subheader("📈 教室对比")

                rankings = []
                for cr in st.session_state.classrooms:
                    name = cr['name']
                    cr_records = [r for r in filtered_records if r.get('classroom') == name]  # 联动过滤数据
                    count = len(cr_records)
                    if count > 0:
                        rankings.append({'教室': name, '记录数': count, '座位': cr.get('total_seats', 0)})

                if rankings:
                    df_rank = pd.DataFrame(rankings)
                    df_rank = df_rank.sort_values('记录数', ascending=False)

                    df_melted = df_rank.melt(id_vars=['教室'], value_vars=['座位', '记录数'], var_name='指标',
                                             value_name='数量')
                    fig_compare = px.bar(
                        df_melted, x='教室', y='数量', color='指标', barmode='group',
                        color_discrete_map={'座位': '#4A90D9', '记录数': '#F5A623'}, text_auto='.0f'
                    )
                    fig_compare.update_layout(
                        xaxis=dict(tickangle=45, type='category', title=''),
                        yaxis=dict(title='', rangemode='tozero'),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, title=''),
                        margin=dict(l=0, r=0, t=30, b=0),
                        height=400, plot_bgcolor='white'
                    )
                    fig_compare.update_traces(textposition='outside')
                    fig_compare.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#f0f0f0')

                    st.plotly_chart(fig_compare, use_container_width=True)

                    st.markdown("---")

                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**📈 区间内使用次数最多的教室**")
                        if rankings:
                            top = df_rank.iloc[0]
                            st.success(f"{top['教室']} - {top['记录数']}次")
                    with col2:
                        st.write("**📉 区间内使用次数最少的教室**")
                        if rankings:
                            low = df_rank.iloc[-1]
                            st.info(f"{low['教室']} - {low['记录数']}次")

            with tab4:
                st.subheader("🔥 教室空间利用矩阵 (交互式热力图)")
                st.caption("💡 矩阵揭示了各教室在不同时段的占用频次。鼠标悬停可查看详情。")

                if st.session_state.classrooms and filtered_records:  # 联动过滤数据
                    classrooms_names = sort_classroom_names([c['name'] for c in st.session_state.classrooms])
                    slot_labels = [s.split('-')[0] for s in SLOT_30MIN]

                    heatmap_data = []
                    for cr_name in classrooms_names:
                        row = []
                        for slot in SLOT_30MIN:
                            count = 0
                            slot_start, slot_end = slot.split('-')
                            slot_s_min = parse_time(slot_start)
                            slot_e_min = parse_time(slot_end)
                            for r in filtered_records:  # 联动过滤数据
                                if r.get('classroom') != cr_name:
                                    continue
                                for rec_slot in r.get('time_slots', []):
                                    rs_str, re_str = rec_slot.split('-')
                                    rs_min = parse_time(rs_str)
                                    re_min = parse_time(re_str)
                                    if slot_s_min < re_min and rs_min < slot_e_min:
                                        count += 1
                                        break
                            row.append(count)
                        heatmap_data.append(row)

                    df_heatmap = pd.DataFrame(heatmap_data, index=classrooms_names, columns=slot_labels)

                    time_totals = df_heatmap.sum(axis=0)
                    room_totals = df_heatmap.sum(axis=1)

                    from plotly.subplots import make_subplots
                    import plotly.graph_objects as go

                    fig_heat = make_subplots(
                        rows=2, cols=2,
                        row_heights=[0.2, 0.8],
                        column_widths=[0.8, 0.2],
                        horizontal_spacing=0.02,
                        vertical_spacing=0.02,
                        shared_xaxes=True,
                        shared_yaxes=True
                    )

                    fig_heat.add_trace(
                        go.Heatmap(
                            z=df_heatmap.values,
                            x=slot_labels,
                            y=classrooms_names,
                            colorscale='YlOrRd',
                            colorbar=dict(title='占用频次', len=0.8, y=0.4),
                            hovertemplate='时段: %{x}<br>教室: %{y}<br>频次: %{z}<extra></extra>'
                        ),
                        row=2, col=1
                    )

                    fig_heat.add_trace(
                        go.Bar(
                            x=slot_labels,
                            y=time_totals.values,
                            marker_color='#F5A623',
                            name='时段热度',
                            hovertemplate='时段: %{x}<br>区间内总频次: %{y}<extra></extra>'
                        ),
                        row=1, col=1
                    )

                    fig_heat.add_trace(
                        go.Bar(
                            y=classrooms_names,
                            x=room_totals.values,
                            orientation='h',
                            marker_color='#4A90D9',
                            name='教室热度',
                            hovertemplate='教室: %{y}<br>区间内总频次: %{x}<extra></extra>'
                        ),
                        row=2, col=2
                    )

                    fig_heat.update_layout(
                        height=max(600, len(classrooms_names) * 25 + 200),
                        margin=dict(l=50, r=20, t=20, b=50),
                        showlegend=False,
                        plot_bgcolor='white'
                    )

                    fig_heat.update_xaxes(showgrid=False, zeroline=False)
                    fig_heat.update_yaxes(showgrid=False, zeroline=False)

                    st.plotly_chart(fig_heat, use_container_width=True)

                    st.markdown("---")
                    st.info("💡 **业务诊断提示**：\n"
                            "* **横向扫描（看教室）**：矩阵右侧的柱状图代表该教室的整体利用率，柱子越长代表该教室越抢手。\n"
                            "* **纵向扫描（看时段）**：矩阵上方的柱状图揭示了全天的资源峰谷周期，最高耸的柱子即为全校空间的极度拥挤时段。")


# ====== 相关性分析 ======
elif page == "🔗 相关性分析":
    st.markdown("探究教室的总座位数是否会显著影响其被使用的频率。")

    if not st.session_state.classrooms or not st.session_state.records:
        st.warning("暂无足够数据，请先添加教室和使用记录。")
    else:
        # 提取数据
        analysis_data = []
        for cr in st.session_state.classrooms:
            cr_name = cr['name']
            total_seats = cr.get('total_seats', 0)
            usage_count = len([r for r in st.session_state.records if r.get('classroom') == cr_name])
            if total_seats > 0:
                analysis_data.append({'教室': cr_name, '座位数': total_seats, '使用频次': usage_count})


        # 优化1：对教室名称进行提取和双重排序（先A-Z字母，再按数字从小到大）
        def sort_key(item):
            name = item['教室']
            alpha = ''.join(filter(str.isalpha, name))
            num = ''.join(filter(str.isdigit, name))
            return (alpha.upper(), int(num) if num else 0, name)


        analysis_data.sort(key=sort_key)
        df_corr = pd.DataFrame(analysis_data)

        if len(df_corr) < 3:
            st.info("有效样本量不足 3 个，无法进行可靠检验。")
        else:
            seats_array = df_corr['座位数'].values
            usage_array = df_corr['使用频次'].values

            # 计算皮尔逊相关系数
            corr_r, p_value = stats.pearsonr(seats_array, usage_array)

            # 优化2：全新的上方排版（三大核心指标横向排列）
            st.subheader("📊 检验结果")
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.metric("有效分析教室数", f"{len(df_corr)} 间")
            with col_m2:
                st.metric("Pearson 相关系数 (r)", f"{corr_r:.4f}")
            with col_m3:
                st.metric("P 值 (P-value)", f"{p_value:.4f}")

            # 核心结论居中高亮
            if p_value < 0.05:
                st.success(f"**结论**：P < 0.05，两者存在显著相关性。（r = {corr_r:.4f}）")
            else:
                st.info("**结论**：P ≥ 0.05，无显著线性相关。")

            st.markdown("---")

            # 优化2：引入 Tabs 标签页，将图表和枯燥的数据表分离，界面更透气
            tab_chart, tab_data = st.tabs(["📉 散点趋势图", "📋 数据明细"])

            with tab_chart:
                # --- 优化：使用 Plotly 绘制动态带辅助趋势线的散点图 ---
                fig_corr = px.scatter(
                    df_corr, x='座位数', y='使用频次',
                    hover_data=['教室'],  # 鼠标放上去能看到是哪个具体的教室！
                    color_discrete_sequence=['#4A90D9'], size_max=10
                )

                # 手动计算趋势线并叠加，确保不依赖额外的统计底层库
                z = np.polyfit(df_corr['座位数'], df_corr['使用频次'], 1)
                p = np.poly1d(z)
                x_trend = np.linspace(df_corr['座位数'].min(), df_corr['座位数'].max(), 100)
                y_trend = p(x_trend)

                fig_corr.add_trace(go.Scatter(
                    x=x_trend, y=y_trend, mode='lines',
                    name='线性趋势拟合', line=dict(color='#E74C3C', dash='dash')
                ))

                fig_corr.update_layout(
                    xaxis=dict(title='总座位数 (自变量 X)'),
                    yaxis=dict(title='使用频次 (因变量 Y)', rangemode='tozero'),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                    margin=dict(l=0, r=20, t=30, b=0),
                    height=400, plot_bgcolor='white'
                )
                fig_corr.update_traces(marker=dict(size=9, opacity=0.8), selector=dict(mode='markers'))
                fig_corr.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#f0f0f0')
                fig_corr.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#f0f0f0')

                st.plotly_chart(fig_corr, use_container_width=True)

            with tab_data:
                # 限制表格宽度，居中展示更美观
                st.dataframe(df_corr, hide_index=True, width=400)

# ====== 综合评价模型 ======
elif page == "🏆 综合评价模型":
    st.markdown("采用**多指标加权评分模型**，结合历史使用频次与平均满座率，计算综合利用得分。")

    if not st.session_state.classrooms or not st.session_state.records:
        st.warning("暂无足够数据，无法构建评价模型。")
    else:
        eval_data = []
        for cr in st.session_state.classrooms:
            cr_name = cr['name']
            total_seats = cr.get('total_seats', 0)
            if total_seats == 0: continue

            cr_records = [r for r in st.session_state.records if r.get('classroom') == cr_name]
            usage_count = len(cr_records)

            if usage_count > 0:
                fill_rates = [r.get('used_seats', 0) / total_seats for r in cr_records]
                avg_fill_rate = np.mean(fill_rates)
            else:
                avg_fill_rate = 0.0

            eval_data.append({
                '教室': cr_name,
                '原始频次': usage_count,
                '平均满座率': avg_fill_rate
            })

        df_eval = pd.DataFrame(eval_data)

        if len(df_eval) > 0:
            # 数据归一化 (Min-Max Scaling)
            scaler = MinMaxScaler()
            df_eval[['频次归一化', '满座率归一化']] = scaler.fit_transform(df_eval[['原始频次', '平均满座率']])

            # 设定权重计算综合得分 (频次 50%，满座率 50%)
            df_eval['综合利用得分'] = (df_eval['频次归一化'] * 0.5 + df_eval['满座率归一化'] * 0.5) * 100

            # --- 排序分流处理 ---

            # 轨道 1：为排行榜准备的数据（按得分降序）
            df_rank = df_eval.sort_values(by='综合利用得分', ascending=False).reset_index(drop=True)
            df_rank.index = df_rank.index + 1
            df_rank.reset_index(inplace=True)
            df_rank.rename(columns={'index': '排名'}, inplace=True)

            # 轨道 2：为明细表准备的数据（按教室名称：字母A-Z，数字从小到大排序）
            df_detail = df_eval.copy()
            df_detail['_alpha'] = df_detail['教室'].apply(lambda x: ''.join(filter(str.isalpha, str(x))).upper())
            df_detail['_num'] = df_detail['教室'].apply(lambda x: int(''.join(filter(str.isdigit, str(x))) or 0))
            df_detail = df_detail.sort_values(by=['_alpha', '_num']).drop(columns=['_alpha', '_num']).reset_index(
                drop=True)

            # 顶部核心指标展示
            top_cr = df_rank.iloc[0]
            bottom_cr = df_rank.iloc[-1]

            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.success(f"🏆 **最优利用效率**：{top_cr['教室']} ({top_cr['综合利用得分']:.1f}分)")
            with col_t2:
                st.error(f"⚠️ **最低利用效率**：{bottom_cr['教室']} ({bottom_cr['综合利用得分']:.1f}分)")

            st.markdown("---")

            # 采用标签页分离排行榜与明细
            tab_rank, tab_detail = st.tabs(["🏅 综合排行榜", "📊 归一化数据明细"])

            with tab_rank:
                df_display = df_rank[['排名', '教室', '原始频次', '平均满座率', '综合利用得分']].copy()
                df_display['平均满座率'] = df_display['平均满座率'].apply(lambda x: f"{x * 100:.1f}%")
                df_display['综合利用得分'] = df_display['综合利用得分'].apply(lambda x: f"{x:.1f}")
                st.dataframe(df_display, hide_index=True, use_container_width=True)

            with tab_detail:
                st.dataframe(df_detail, hide_index=True, use_container_width=True)

# ====== 🔮 贝叶斯空闲预测 ======
elif page == "🔮 贝叶斯空闲预测":
    st.markdown("基于历史观测数据的 Beta-Binomial 共轭先验模型，推断未来特定时段的空闲概率及置信区间。")

    if not st.session_state.records:
        st.warning("暂无使用记录数据，模型缺乏历史先验输入。")
    else:
        # 将三个下拉框水平并排，紧凑美观
        col_sel1, col_sel2, col_sel3 = st.columns(3)
        with col_sel1:
            pred_classroom = st.selectbox("🎯 目标教室", sort_classroom_names([c['name'] for c in st.session_state.classrooms]), key="pred_classroom")
        with col_sel2:
            pred_weekday = st.selectbox("📅 预测星期", WEEKDAYS, key="pred_weekday")
        with col_sel3:
            pred_slot = st.selectbox("🕐 预测时段", SLOT_30MIN, key="pred_slot")

        if st.button("🚀 运行概率推断", type="primary"):
            st.markdown("---")

            # 检查排课强逻辑
            schedule_hit = None
            for s in st.session_state.schedules:
                if s.get('classroom') == pred_classroom and s.get('weekday') == pred_weekday:
                    if slot_overlaps_45(pred_slot, s.get('time_slots', [])):
                        schedule_hit = s
                        break

            if schedule_hit:
                st.error(f"🔴 **绝对占用状态**：该教室 {pred_weekday} {pred_slot} 存在固定排课。")
                st.markdown(f"> **课程**：{schedule_hit.get('course_name', '')} | **教师**：{schedule_hit.get('teacher', '')} | **类型**：{schedule_hit.get('course_type', '')}")
                st.info("💡 算法解释：由于教务排课属于确定性强约束（P=0），系统自动中止概率推断引擎。")
            else:
                cr_obj = next((c for c in st.session_state.classrooms if c['name'] == pred_classroom), None)
                total_seats = cr_obj.get('total_seats', 0) if cr_obj else 0

                _weekday_map = ['周一','周二','周三','周四','周五','周六','周日']
                matched_records = []
                for r in st.session_state.records:
                    if r.get('classroom') != pred_classroom: continue
                    _r_date = r.get('date', '')
                    _r_wd = ''
                    if _r_date:
                        try: _r_wd = _weekday_map[datetime.strptime(_r_date, '%Y-%m-%d').weekday()]
                        except: pass
                    if _r_wd != pred_weekday: continue
                    for rs in r.get('time_slots', []):
                        if slot_overlaps_45(pred_slot, [rs]):
                            matched_records.append(r)
                            break

                n = len(matched_records)
                MIN_SAMPLES = 3

                if n < MIN_SAMPLES:
                    st.warning(f"⚠️ **置信度不足**：该条件下的历史样本量过低（n={n}），未能达到启动贝叶斯估计的最小数据阈值。")
                    if total_seats > 0:
                        st.success(f"📊 结合先验常识判断：该时段无固定排课，且历史被征用次数极少，极大概率处于**完全空闲**状态（资源容量：{total_seats} 座）。")
                else:
                    # Beta-Binomial 计算逻辑
                    free_count = len([r for r in matched_records if r.get('used_seats', 0) / max(1, r.get('total_seats', 1)) < 0.3])
                    alpha = 1 + free_count
                    beta_param = 1 + n - free_count
                    prob_free = alpha / (alpha + beta_param) * 100

                    p = free_count / n
                    z = 1.96
                    denominator = 1 + z**2 / n
                    centre = (p + z**2 / (2*n)) / denominator
                    margin = z * np.sqrt((p*(1-p) + z**2/(4*n)) / n) / denominator
                    ci_lower = max(0, (centre - margin) * 100)
                    ci_upper = min(100, (centre + margin) * 100)

                    avg_used = np.mean([r.get('used_seats', 0) for r in matched_records])
                    predicted_remaining = max(0, total_seats - avg_used) if total_seats > 0 else 0

                    # 引入 Plotly 仪表盘 (Gauge Chart)
                    import plotly.graph_objects as go

                    fig_gauge = go.Figure(go.Indicator(
                        mode = "gauge+number",
                        value = prob_free,
                        number = {'suffix': "%", 'valueformat': ".1f", 'font': {'size': 40}},
                        domain = {'x': [0, 1], 'y': [0, 1]},
                        title = {'text': "算法推断空闲概率", 'font': {'size': 16}},
                        gauge = {
                            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
                            'bar': {'color': "rgba(0,0,0,0.2)"},
                            'bgcolor': "white",
                            'borderwidth': 2,
                            'bordercolor': "gray",
                            'steps': [
                                {'range': [0, 40], 'color': '#ff4b4b'},    # 红色高危
                                {'range': [40, 70], 'color': '#faca2b'},   # 黄色警告
                                {'range': [70, 100], 'color': '#09ab3b'}], # 绿色安全
                            'threshold': {
                                'line': {'color': "black", 'width': 3},
                                'thickness': 0.75,
                                'value': prob_free}
                        }
                    ))
                    fig_gauge.update_layout(height=350, margin=dict(l=30, r=30, t=50, b=20))

                    # 左右图文分栏布局
                    col_res1, col_res2 = st.columns([1, 1.2])
                    with col_res1:
                        st.plotly_chart(fig_gauge, use_container_width=True)

                    with col_res2:
                        st.markdown("<br>", unsafe_allow_html=True)
                        st.subheader("📊 模型诊断报告")
                        st.markdown(f"- **模型先验样本**：`{n}` 条同条件历史记录矩阵")
                        st.markdown(f"- **95% 置信区间**：`[{ci_lower:.1f}%, {ci_upper:.1f}%]` (基于 Wilson Score)")
                        st.markdown(f"- **预期剩余席位**：约 **`{int(round(predicted_remaining))}`** 个 (总容量 {total_seats})")

                        st.markdown("<br>", unsafe_allow_html=True)
                        if prob_free > 70:
                            st.success("🟢 **系统决策建议**：极大概率处于空闲区间，资源充裕，推荐作为首选目标前往。")
                        elif prob_free > 40:
                            st.warning("🟡 **系统决策建议**：数据呈现轻度波动，存在被占用的风险，建议作为备选空间保留。")
                        else:
                            st.error("🔴 **系统决策建议**：该时段拥挤概率极高，不建议前往，请重新检索其余可用空间。")

# ====== 动态综合报告生成 ======
elif page == "📋 报告导出":
    st.title("📋 综合分析报告生成中心")
    st.markdown("💡 结合统计学诊断结论与可视化图表，自动生成专业级排版报告。")

    if not st.session_state.records or len(st.session_state.classrooms) < 3:
        st.warning("⚠️ 系统内数据量不足，无法生成具有统计学支撑的综合报告。请先补充教室资源和使用记录。")
    else:
        # --- 1. 基础概览数据提取 ---
        total_rooms = len(st.session_state.classrooms)
        total_records = len(st.session_state.records)

        # 统计教室类型分布
        type_counts = {}
        for cr in st.session_state.classrooms:
            t = cr.get('type', '未知')
            type_counts[t] = type_counts.get(t, 0) + 1
        df_types = pd.DataFrame(list(type_counts.items()), columns=['教室类型', '数量'])

        # --- 2. 相关性分析核心结论计算 ---
        analysis_data = []
        for cr in st.session_state.classrooms:
            cr_name = cr['name']
            total_seats = cr.get('total_seats', 0)
            usage_count = len([r for r in st.session_state.records if r.get('classroom') == cr_name])
            if total_seats > 0:
                analysis_data.append({'座位数': total_seats, '使用频次': usage_count})

        df_corr = pd.DataFrame(analysis_data)
        corr_str = "因数据方差异常，暂时无法计算。"
        if len(df_corr) >= 3:
            corr_r, p_value = stats.pearsonr(df_corr['座位数'], df_corr['使用频次'])
            if p_value < 0.05:
                direction = "显著正相关" if corr_r > 0 else "显著负相关"
                biz_logic = "规模越大的教室越受师生青睐，存在对大容量空间的高度需求。" if corr_r > 0 else "小规模教室的利用率反而更高，反映出师生对小型自习/研讨空间的偏好。"
                corr_str = f"通过 Pearson 相关性检验（r={corr_r:.2f}, P={p_value:.3f}），确认教室规模与使用频次存在**{direction}**。结论表明：{biz_logic}"
            else:
                corr_str = f"通过 Pearson 相关性检验（r={corr_r:.2f}, P={p_value:.3f}），教室规模与使用频次**不存在显著的线性相关**（P ≥ 0.05）。结论表明：单纯的座位数多少并非影响资源征用的核心变量。"

        # --- 3. 综合评价极值计算 ---
        eval_data = []
        for cr in st.session_state.classrooms:
            cr_name = cr['name']
            total_seats = cr.get('total_seats', 0)
            if total_seats == 0: continue

            cr_records = [r for r in st.session_state.records if r.get('classroom') == cr_name]
            usage_count = len(cr_records)

            avg_fill = np.mean([r.get('used_seats', 0) / total_seats for r in cr_records]) if usage_count > 0 else 0.0
            eval_data.append({'教室': cr_name, '频次': usage_count, '满座率': avg_fill})

        df_eval = pd.DataFrame(eval_data)
        best_room, worst_room = "计算异常", "计算异常"
        if len(df_eval) > 0:
            scaler = MinMaxScaler()
            df_eval[['频次归一化', '满座率归一化']] = scaler.fit_transform(df_eval[['频次', '满座率']])
            df_eval['得分'] = (df_eval['频次归一化'] * 0.5 + df_eval['满座率归一化'] * 0.5) * 100
            df_eval = df_eval.sort_values(by='得分', ascending=False).reset_index(drop=True)

            best_room = f"**{df_eval.iloc[0]['教室']}** (利用效率评价分: {df_eval.iloc[0]['得分']:.1f})"
            worst_room = f"**{df_eval.iloc[-1]['教室']}** (利用效率评价分: {df_eval.iloc[-1]['得分']:.1f})"

        # --- 4. 生成高级交互图表 (Plotly) ---
        # 饼图：教室资产分布
        fig_pie = px.pie(df_types, values='数量', names='教室类型', title='本校空间资产分布结构', hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_pie.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=300)

        # 柱状图：利用率 Top 10
        top10_df = df_eval.head(10).sort_values(by='得分', ascending=True)  # Plotly水平条形图默认从下往上画
        fig_bar = px.bar(top10_df, x='得分', y='教室', orientation='h', title='空间资源利用效率评级 (TOP 10)',
                         text_auto='.1f', color='得分', color_continuous_scale='Blues')
        fig_bar.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=400, coloraxis_showscale=False)

        # --- 5. 渲染图文并茂的最终报告 ---
        st.markdown("---")

        # 使用列布局，左文右图，打破沉闷
        st.subheader("一、 资源纳管与结构抽样")
        st.markdown(
            f"截至本报告生成时点，系统共纳管实体资源 **{total_rooms}** 间，沉淀有效行为记录 **{total_records}** 条。核心资产结构如下侧环形图所示。")
        st.plotly_chart(fig_pie, use_container_width=True)

        st.subheader("二、 空间规模与偏好相关性诊断")
        st.markdown(f"为验证物理容量特征是否干预利用率的假设，系统剥离了绝对座位数与被征用频次，进行统计学检验。")
        st.info(corr_str)
        st.markdown("*管理决策建议：在新校区空间规划或内部构造改造中，应将此倾向数据纳入考量，避免规模错配。*")

        st.subheader("三、 空间利用效率多维综合评价")
        st.markdown(f"本评价体系纳入了“征用活跃度”与“截面满座率”双维度。经 Min-Max 数据降维后等权重计算得出效率指数。")

        col_rank1, col_rank2 = st.columns(2)
        with col_rank1:
            st.success(f"🏆 **利用率标杆**：{best_room}")
        with col_rank2:
            st.error(f"⚠️ **低效预警**：{worst_room}")

        st.markdown("下图展示了当前综合得分排名前十的空间节点矩阵分布：")
        st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")
        st.caption(
            f"*算法声明：本报告内容系数据流过应用统计模型后自动分发生成的客观判定，预测精度受限于样本容量（n={total_records}）。*")

        # --- 6. 导出策略：支持 Markdown 及打印为 PDF 的引导 ---
        st.markdown("### 🖨️ 报告输出选项")
        col_export1, col_export2 = st.columns(2)

        with col_export1:
            st.download_button(
                label="📥 导出为 Markdown 文本",
                data=f"报告生成于 {datetime.now().strftime('%Y-%m-%d')}，详情请参考系统前端可视化展示。",
                # 简化 Markdown，引导使用 PDF
                file_name=f"统计分析报告_{datetime.now().strftime('%Y%m%d')}.md",
                mime="text/markdown",
            )

        with col_export2:
            # 这是一个极佳的用户体验设计，引导用户利用浏览器自带功能生成高清带图的 PDF
            st.button("📄 如何导出为带图的高清 PDF？",
                      help="请直接按下键盘的【Ctrl + P】(Mac系统按 Cmd + P)，将目标打印机选择为『另存为 PDF』，即可保存当前图文并茂的分析报告！")

# ====== 侧边栏业务架构说明 ======
st.sidebar.markdown("---")
st.sidebar.markdown("""
**系统业务功能地图：**

**【前台查询与业务登记】**
*   **📊 仪表盘**：系统全局状态速览。
*   **🔍 空闲查询**：支持高频的网格化空位检索。
*   **📝 记录使用**：师生进行时段预约与占用登记。

**【中台统计与算法评估】**
*   **🔬 深度统计分析**：内置描述性统计、Pearson 相关性假设检验与 Min-Max 加权空间利用率评价模型。
*   **📋 报告导出**：基于底层数据特征，一键生成图文并茂的《空间资源应用统计综合报告》。

**【后台资源维护】**
*   **⚙️ 数据源与配置**：管理员专属的底层实体库与固定排课管理。

---
*教室空间资源统计分析辅助决策系统 v9.0*
""")
