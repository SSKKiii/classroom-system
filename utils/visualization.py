"""
可视化模块 - 使用 Plotly 生成交互式图表
"""

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime
import os


class ClassroomVisualization:
    """教室使用可视化类"""
    
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
    
    def plot_usage_trend(self):
        """
        绘制使用率趋势图
        """
        if self.df.empty or 'date' not in self.df.columns:
            return None
        
        # 按日期聚合
        daily_stats = self.df.groupby('date')['usage_rate'].mean().reset_index()
        daily_stats['date'] = pd.to_datetime(daily_stats['date'])
        daily_stats = daily_stats.sort_values('date')
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=daily_stats['date'],
            y=daily_stats['usage_rate'],
            mode='lines+markers',
            name='平均使用率',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=8)
        ))
        
        # 添加趋势线
        if len(daily_stats) >= 3:
            x_numeric = np.arange(len(daily_stats))
            z = np.polyfit(x_numeric, daily_stats['usage_rate'].values, 1)
            p = np.poly1d(z)
            
            fig.add_trace(go.Scatter(
                x=daily_stats['date'],
                y=p(x_numeric),
                mode='lines',
                name='趋势线',
                line=dict(color='red', width=2, dash='dash')
            ))
        
        fig.update_layout(
            title='使用率趋势',
            xaxis_title='日期',
            yaxis_title='使用率 (%)',
            hovermode='x unified',
            template='plotly_white'
        )
        
        return fig
    
    def plot_usage_distribution(self):
        """
        绘制使用率分布直方图
        """
        if self.df.empty or 'usage_rate' not in self.df.columns:
            return None
        
        fig = go.Figure()
        
        fig.add_trace(go.Histogram(
            x=self.df['usage_rate'],
            nbinsx=20,
            name='使用率分布',
            marker_color='#1f77b4',
            opacity=0.7
        ))
        
        # 添加正态分布曲线
        mean = self.df['usage_rate'].mean()
        std = self.df['usage_rate'].std()
        
        if std > 0:
            x_range = np.linspace(0, 100, 100)
            y_normal = (1 / (std * np.sqrt(2 * np.pi))) * \
                       np.exp(-0.5 * ((x_range - mean) / std) ** 2)
            # 缩放以匹配直方图
            bin_width = 5
            scale = len(self.df) * bin_width
            y_normal = y_normal * scale
            
            fig.add_trace(go.Scatter(
                x=x_range,
                y=y_normal,
                mode='lines',
                name='正态分布',
                line=dict(color='red', width=2)
            ))
        
        fig.update_layout(
            title='使用率分布',
            xaxis_title='使用率 (%)',
            yaxis_title='频数',
            template='plotly_white'
        )
        
        return fig
    
    def plot_usage_type_pie(self):
        """
        绘制使用类型饼图
        """
        if self.df.empty or 'usage_type' not in self.df.columns:
            return None
        
        type_counts = self.df['usage_type'].value_counts()
        
        fig = go.Figure(data=[go.Pie(
            labels=type_counts.index,
            values=type_counts.values,
            hole=0.3,
            marker_colors=px.colors.qualitative.Set2
        )])
        
        fig.update_layout(
            title='使用类型分布',
            template='plotly_white'
        )
        
        return fig
    
    def plot_time_slot_analysis(self):
        """
        绘制各时段使用率分析
        """
        if self.df.empty or 'time_slot' not in self.df.columns:
            return None
        
        time_stats = self.df.groupby('time_slot')['usage_rate'].agg(['mean', 'std']).reset_index()
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=time_stats['time_slot'],
            y=time_stats['mean'],
            error_y=dict(
                type='data',
                array=time_stats['std'].fillna(0),
                visible=True
            ),
            marker_color='#2ecc71'
        ))
        
        fig.update_layout(
            title='各时段平均使用率（含标准差）',
            xaxis_title='时间段',
            yaxis_title='平均使用率 (%)',
            template='plotly_white',
            xaxis_tickangle=-45
        )
        
        return fig
    
    def plot_weekly_heatmap(self):
        """
        绘制周热力图
        """
        if self.df.empty or 'date' not in self.df.columns:
            return None
        
        df_copy = self.df.copy()
        df_copy['date'] = pd.to_datetime(df_copy['date'])
        df_copy['weekday'] = df_copy['date'].dt.day_name()
        df_copy['weekday_num'] = df_copy['date'].dt.weekday
        
        # 创建热力图数据
        heatmap_data = df_copy.groupby(['weekday', 'time_slot'])['usage_rate'].mean().reset_index()
        
        # 排序星期
        weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        heatmap_data['weekday'] = pd.Categorical(heatmap_data['weekday'], categories=weekday_order, ordered=True)
        heatmap_data = heatmap_data.sort_values('weekday')
        
        # 转换为矩阵
        pivot = heatmap_data.pivot(index='weekday', columns='time_slot', values='usage_rate')
        
        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale='RdYlGn_r',
            text=[[f'{v:.1f}%' if not pd.isna(v) else '' for v in row] for row in pivot.values],
            texttemplate='%{text}',
            colorbar=dict(title='使用率 (%)')
        ))
        
        fig.update_layout(
            title='时段-星期使用率热力图',
            xaxis_title='时间段',
            yaxis_title='星期',
            template='plotly_white'
        )
        
        return fig
    
    def plot_classroom_comparison(self):
        """
        绘制教室使用对比图
        """
        if self.df.empty or 'classroom' not in self.df.columns:
            return None
        
        classroom_stats = self.df.groupby('classroom')['usage_rate'].agg(['mean', 'std', 'count']).reset_index()
        classroom_stats = classroom_stats.sort_values('mean', ascending=True)
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            y=classroom_stats['classroom'],
            x=classroom_stats['mean'],
            orientation='h',
            error_x=dict(
                type='data',
                array=classroom_stats['std'].fillna(0),
                visible=True
            ),
            marker_color='#3498db',
            text=classroom_stats['mean'].round(1),
            texttemplate='%{text}%',
            textposition='outside'
        ))
        
        fig.update_layout(
            title='各教室平均使用率对比',
            xaxis_title='平均使用率 (%)',
            yaxis_title='教室',
            template='plotly_white'
        )
        
        return fig
    
    def plot_prediction_chart(self, prediction):
        """
        绘制预测结果图表
        """
        if not prediction or prediction['sample_count'] == 0:
            return None
        
        fig = make_subplots(
            rows=1, cols=2,
            specs=[[{'type': 'pie'}, {'type': 'bar'}]],
            subplot_titles=('空闲概率', '历史数据分布')
        )
        
        # 空闲概率饼图
        free_prob = prediction['free_probability']
        fig.add_trace(
            go.Pie(
                labels=['空闲', '占用'],
                values=[free_prob, 100 - free_prob],
                marker_colors=['#2ecc71', '#e74c3c'],
                hole=0.4
            ),
            row=1, col=1
        )
        
        # 历史数据分布
        if 'free_count' in prediction and 'busy_count' in prediction:
            fig.add_trace(
                go.Bar(
                    x=['空闲', '占用'],
                    y=[prediction['free_count'], prediction['busy_count']],
                    marker_color=['#2ecc71', '#e74c3c']
                ),
                row=1, col=2
            )
        
        fig.update_layout(
            title='空闲概率预测结果',
            template='plotly_white'
        )
        
        return fig
    
    def export_charts(self):
        """
        导出图表为HTML文件
        """
        if self.df.empty:
            return None
        
        output_dir = 'reports'
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(output_dir, f'charts_{timestamp}.html')
        
        # 收集所有图表
        charts = []
        
        trend_fig = self.plot_usage_trend()
        if trend_fig:
            charts.append(('使用率趋势', trend_fig))
        
        dist_fig = self.plot_usage_distribution()
        if dist_fig:
            charts.append(('使用率分布', dist_fig))
        
        pie_fig = self.plot_usage_type_pie()
        if pie_fig:
            charts.append(('使用类型分布', pie_fig))
        
        time_fig = self.plot_time_slot_analysis()
        if time_fig:
            charts.append(('时段分析', time_fig))
        
        compare_fig = self.plot_classroom_comparison()
        if compare_fig:
            charts.append(('教室对比', compare_fig))
        
        # 生成HTML
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('<html><head><meta charset="utf-8"><title>教室使用统计图表</title></head><body>\n')
            f.write('<h1>教室使用统计图表报告</h1>\n')
            f.write(f'<p>生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>\n')
            
            for title, fig in charts:
                f.write(f'<h2>{title}</h2>\n')
                f.write(fig.to_html(full_html=False, include_plotlyjs='cdn'))
                f.write('<hr>\n')
            
            f.write('</body></html>')
        
        return output_file
