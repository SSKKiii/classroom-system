"""
报告生成模块
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os


class ReportGenerator:
    """报告生成类"""
    
    def __init__(self, records, classrooms):
        """
        初始化
        :param records: 使用记录列表
        :param classrooms: 教室信息列表
        """
        self.records = records
        self.classrooms = classrooms
        self.df = pd.DataFrame(records) if records else pd.DataFrame()
        # 如果没有 usage_rate 列，从 used_seats / total_seats 计算
        if not self.df.empty and 'usage_rate' not in self.df.columns:
            if 'used_seats' in self.df.columns and 'total_seats' in self.df.columns:
                self.df['usage_rate'] = self.df.apply(
                    lambda r: (r['used_seats'] / r['total_seats'] * 100) if r['total_seats'] > 0 else 0, axis=1
                )
            else:
                self.df['usage_rate'] = 0
    
    def generate_report(self, report_type, start_date=None, end_date=None):
        """
        生成报告内容
        
        :param report_type: 报告类型（日报/周报/月报/自定义时间段）
        :param start_date: 开始日期
        :param end_date: 结束日期
        :return: Markdown格式的报告内容
        """
        # 确定日期范围
        today = datetime.now()
        
        if report_type == "日报":
            start = today - timedelta(days=1)
            end = today
        elif report_type == "周报":
            start = today - timedelta(weeks=1)
            end = today
        elif report_type == "月报":
            start = today - timedelta(days=30)
            end = today
        else:
            start = start_date if start_date else today - timedelta(days=7)
            end = end_date if end_date else today
        
        start_str = start.strftime('%Y-%m-%d') if hasattr(start, 'strftime') else str(start)
        end_str = end.strftime('%Y-%m-%d') if hasattr(end, 'strftime') else str(end)
        
        # 筛选数据
        if not self.df.empty and 'date' in self.df.columns:
            df_filtered = self.df[
                (self.df['date'] >= start_str) & 
                (self.df['date'] <= end_str)
            ]
        else:
            df_filtered = self.df
        
        # 生成报告
        report = f"""# 教室使用情况{report_type}

## 报告概览

- **报告类型**: {report_type}
- **统计时段**: {start_str} 至 {end_str}
- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 一、基础统计

"""
        
        if df_filtered.empty:
            report += "**该时段内无使用记录**\n"
        else:
            # 基础统计
            total_records = len(df_filtered)
            avg_usage = df_filtered['usage_rate'].mean()
            std_usage = df_filtered['usage_rate'].std()
            max_usage = df_filtered['usage_rate'].max()
            min_usage = df_filtered['usage_rate'].min()
            
            report += f"""
| 指标 | 数值 |
|------|------|
| 记录总数 | {total_records} 条 |
| 平均使用率 | {avg_usage:.2f}% |
| 使用率标准差 | {std_usage:.2f}% |
| 最高使用率 | {max_usage:.2f}% |
| 最低使用率 | {min_usage:.2f}% |

"""
            
            # 使用类型统计
            if 'usage_type' in df_filtered.columns:
                report += "## 二、使用类型分布\n\n"
                type_counts = df_filtered['usage_type'].value_counts()
                report += "| 使用类型 | 次数 | 占比 |\n|----------|------|------|\n"
                for usage_type, count in type_counts.items():
                    ratio = count / total_records * 100
                    report += f"| {usage_type} | {count} | {ratio:.1f}% |\n"
                report += "\n"
            
            # 时段分析
            if 'time_slot' in df_filtered.columns:
                report += "## 三、时段使用分析\n\n"
                time_stats = df_filtered.groupby('time_slot')['usage_rate'].agg(['mean', 'count'])
                time_stats = time_stats.sort_values('mean', ascending=False)
                report += "| 时间段 | 平均使用率 | 记录数 |\n|--------|------------|--------|\n"
                for time_slot, row in time_stats.iterrows():
                    report += f"| {time_slot} | {row['mean']:.1f}% | {int(row['count'])} |\n"
                report += "\n"
            
            # 教室统计
            if 'classroom' in df_filtered.columns:
                report += "## 四、各教室使用情况\n\n"
                classroom_stats = df_filtered.groupby('classroom')['usage_rate'].agg(['mean', 'count', 'max', 'min'])
                classroom_stats = classroom_stats.sort_values('mean', ascending=False)
                report += "| 教室 | 平均使用率 | 使用次数 | 最高 | 最低 |\n|------|------------|----------|------|------|\n"
                for classroom, row in classroom_stats.iterrows():
                    report += f"| {classroom} | {row['mean']:.1f}% | {int(row['count'])} | {row['max']:.1f}% | {row['min']:.1f}% |\n"
                report += "\n"
            
            # 统计方法说明
            report += """## 五、统计方法说明

本报告应用了以下统计方法：

### 1. 描述性统计
- **均值**: 反映使用率的集中趋势
- **标准差**: 反映使用率的离散程度
- **极值**: 识别异常情况

### 2. 分组分析
- 按使用类型分组，分析各类用途的占比
- 按时间段分组，识别高峰和低谷时段
- 按教室分组，对比各教室的使用情况

### 3. 应用场景
- 教室资源调配：根据使用率合理安排教室开放
- 高峰预警：识别高峰时段，提前做好安排
- 使用效率评估：评估教室资源的利用效率

---

"""
        
        report += """## 六、建议与改进

基于以上统计分析，提出以下建议：

1. **资源优化**: 对于使用率长期较低的教室，可考虑减少开放或调整用途
2. **高峰应对**: 针对高峰时段，提前做好教室预约管理
3. **数据收集**: 建议持续收集数据，以便进行更深入的时间序列分析

---

*报告由教室空位管理系统自动生成*
"""
        
        return report
    
    def export_markdown(self, report_type, start_date=None, end_date=None):
        """
        导出Markdown报告文件
        """
        output_dir = 'reports'
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'report_{report_type}_{timestamp}.md'
        filepath = os.path.join(output_dir, filename)
        
        content = self.generate_report(report_type, start_date, end_date)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return filepath
    
    def export_csv(self, start_date=None, end_date=None):
        """
        导出CSV数据文件
        """
        output_dir = 'reports'
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'data_export_{timestamp}.csv'
        filepath = os.path.join(output_dir, filename)
        
        # 筛选数据
        if start_date and end_date and not self.df.empty and 'date' in self.df.columns:
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            df_export = self.df[
                (self.df['date'] >= start_str) & 
                (self.df['date'] <= end_str)
            ]
        else:
            df_export = self.df
        
        if not df_export.empty:
            df_export.to_csv(filepath, index=False, encoding='utf-8-sig')
        
        return filepath
