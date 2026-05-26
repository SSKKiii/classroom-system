"""
统计分析模块 - 应用统计方法实现
包含：描述性统计、假设检验、回归分析、预测等
"""

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from datetime import datetime, timedelta
from collections import defaultdict


class ClassroomStatistics:
    """教室使用统计分析类"""
    
    def __init__(self, records, classrooms):
        """
        初始化
        :param records: 使用记录列表
        :param classrooms: 教室信息列表
        """
        self.records = records
        self.classrooms = classrooms
        self.df = pd.DataFrame(records) if records else pd.DataFrame()
    
    def calculate_basic_statistics(self):
        """
        计算基础描述性统计量
        应用统计方法：均值、标准差、极值、中位数
        """
        if self.df.empty or 'usage_rate' not in self.df.columns:
            return {
                'mean_rate': 0,
                'std_rate': 0,
                'max_rate': 0,
                'min_rate': 0,
                'median_rate': 0,
                'variance': 0,
                'skewness': 0,
                'kurtosis': 0
            }
        
        rates = self.df['usage_rate'].values
        
        return {
            'mean_rate': np.mean(rates),
            'std_rate': np.std(rates, ddof=1),  # 样本标准差
            'max_rate': np.max(rates),
            'min_rate': np.min(rates),
            'median_rate': np.median(rates),
            'variance': np.var(rates, ddof=1),  # 样本方差
            'skewness': scipy_stats.skew(rates),  # 偏度
            'kurtosis': scipy_stats.kurtosis(rates)  # 峰度
        }
    
    def calculate_average_usage_rate(self):
        """计算平均使用率"""
        if self.df.empty or 'usage_rate' not in self.df.columns:
            return 0
        return self.df['usage_rate'].mean()
    
    def generate_classroom_statistics(self):
        """
        生成各教室的详细统计表
        应用统计方法：分组统计、置信区间
        """
        if self.df.empty:
            return None
        
        results = []
        
        for classroom in self.classrooms:
            name = classroom['name']
            classroom_records = self.df[self.df['classroom'] == name]
            
            if classroom_records.empty:
                continue
            
            rates = classroom_records['usage_rate'].values
            
            # 计算统计量
            mean_rate = np.mean(rates)
            std_rate = np.std(rates, ddof=1) if len(rates) > 1 else 0
            n = len(rates)
            
            # 95% 置信区间
            if n > 1:
                ci = scipy_stats.t.interval(
                    0.95, 
                    n - 1, 
                    loc=mean_rate, 
                    scale=std_rate / np.sqrt(n)
                )
                ci_lower, ci_upper = ci
            else:
                ci_lower, ci_upper = mean_rate, mean_rate
            
            results.append({
                '教室': name,
                '总座位': classroom.get('total_seats', 0),
                '记录数': n,
                '平均使用率(%)': round(mean_rate, 2),
                '标准差(%)': round(std_rate, 2),
                '中位数(%)': round(np.median(rates), 2),
                '95%CI下限': round(ci_lower, 2),
                '95%CI上限': round(ci_upper, 2),
                '最高使用率(%)': round(np.max(rates), 2),
                '最低使用率(%)': round(np.min(rates), 2)
            })
        
        return pd.DataFrame(results) if results else None
    
    def identify_peak_hours(self):
        """
        识别高峰时段
        应用统计方法：按时间段分组，计算平均使用率
        """
        if self.df.empty or 'time_slot' not in self.df.columns:
            return []
        
        # 按时间段分组统计
        time_stats = self.df.groupby('time_slot')['usage_rate'].agg(['mean', 'count'])
        
        # 按平均使用率排序
        time_stats = time_stats.sort_values('mean', ascending=False)
        
        # 返回前3个高峰时段
        peak_slots = []
        for time_slot, row in time_stats.head(3).iterrows():
            peak_slots.append((time_slot, row['mean']))
        
        return peak_slots
    
    def calculate_classroom_ranking(self):
        """
        计算教室使用率排名
        """
        if self.df.empty:
            return []
        
        ranking = []
        
        for classroom in self.classrooms:
            name = classroom['name']
            classroom_records = self.df[self.df['classroom'] == name]
            
            if not classroom_records.empty:
                avg_rate = classroom_records['usage_rate'].mean()
                count = len(classroom_records)
                ranking.append((name, round(avg_rate, 2), count))
        
        # 按平均使用率降序排序
        ranking.sort(key=lambda x: x[1], reverse=True)
        
        return ranking
    
    def predict_availability(self, classroom_name, time_slot):
        """
        预测教室空闲概率
        应用统计方法：贝叶斯估计、条件概率
        
        :param classroom_name: 教室名称，'全部教室' 表示所有教室
        :param time_slot: 时间段
        :return: 预测结果字典
        """
        # 筛选数据
        if classroom_name == '全部教室':
            relevant_records = self.df[self.df['time_slot'] == time_slot]
        else:
            relevant_records = self.df[
                (self.df['classroom'] == classroom_name) & 
                (self.df['time_slot'] == time_slot)
            ]
        
        n = len(relevant_records)
        
        if n == 0:
            return {
                'free_probability': 50.0,
                'sample_count': 0,
                'confidence': 0,
                'method': '无历史数据，返回默认值'
            }
        
        # 定义空闲：使用率 < 20%
        free_threshold = 20
        free_count = (relevant_records['usage_rate'] < free_threshold).sum()
        
        # 贝叶斯估计
        # 先验概率：假设空闲概率服从 Beta(1, 1) 即均匀分布
        # 后验概率：Beta(1 + free_count, 1 + n - free_count)
        alpha = 1 + free_count
        beta = 1 + n - free_count
        
        # 后验均值作为点估计
        free_probability = alpha / (alpha + beta) * 100
        
        # 计算置信度（基于样本量）
        # 使用 Wilson 置信区间下限作为保守估计
        if n > 0:
            z = 1.96  # 95% 置信水平
            p_hat = free_count / n
            denominator = 1 + z**2 / n
            centre = (p_hat + z**2 / (2 * n)) / denominator
            margin = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denominator
            confidence = max(0, (centre - margin) * 100)
        else:
            confidence = 0
        
        return {
            'free_probability': round(free_probability, 1),
            'sample_count': n,
            'confidence': round(confidence, 1),
            'method': '贝叶斯估计 (Beta先验)',
            'free_count': free_count,
            'busy_count': n - free_count
        }
    
    def hypothesis_test_usage_difference(self, classroom1, classroom2):
        """
        假设检验：检验两个教室的使用率是否有显著差异
        应用统计方法：独立样本t检验
        
        H0: μ1 = μ2 (两个教室平均使用率无显著差异)
        H1: μ1 ≠ μ2 (两个教室平均使用率有显著差异)
        """
        if self.df.empty:
            return None
        
        rates1 = self.df[self.df['classroom'] == classroom1]['usage_rate'].values
        rates2 = self.df[self.df['classroom'] == classroom2]['usage_rate'].values
        
        if len(rates1) < 2 or len(rates2) < 2:
            return {
                'test': '独立样本t检验',
                'result': '样本量不足（需要至少2个样本）',
                'significant': False
            }
        
        # 独立样本t检验
        t_stat, p_value = scipy_stats.ttest_ind(rates1, rates2)
        
        # 判断显著性（α = 0.05）
        significant = p_value < 0.05
        
        return {
            'test': '独立样本t检验',
            'classroom1': classroom1,
            'classroom2': classroom2,
            'mean1': round(np.mean(rates1), 2),
            'mean2': round(np.mean(rates2), 2),
            't_statistic': round(t_stat, 4),
            'p_value': round(p_value, 4),
            'significant': significant,
            'result': '存在显著差异' if significant else '无显著差异',
            'alpha': 0.05
        }
    
    def chi_square_test_usage_type(self):
        """
        卡方检验：检验使用类型与时间段是否独立
        应用统计方法：卡方独立性检验
        
        H0: 使用类型与时间段独立
        H1: 使用类型与时间段不独立
        """
        if self.df.empty or 'usage_type' not in self.df.columns:
            return None
        
        # 构建列联表
        contingency = pd.crosstab(self.df['time_slot'], self.df['usage_type'])
        
        if contingency.size == 0:
            return None
        
        # 卡方检验
        chi2, p_value, dof, expected = scipy_stats.chi2_contingency(contingency)
        
        return {
            'test': '卡方独立性检验',
            'chi2_statistic': round(chi2, 4),
            'p_value': round(p_value, 4),
            'degrees_of_freedom': dof,
            'significant': p_value < 0.05,
            'result': '使用类型与时间段相关' if p_value < 0.05 else '使用类型与时间段独立',
            'contingency_table': contingency.to_dict()
        }
    
    def correlation_analysis(self):
        """
        相关性分析：分析使用率与其他变量的相关性
        应用统计方法：皮尔逊相关系数
        """
        if self.df.empty:
            return None
        
        results = []
        
        # 使用座位数与使用率的相关性
        if 'used_seats' in self.df.columns and 'usage_rate' in self.df.columns:
            corr, p_value = scipy_stats.pearsonr(
                self.df['used_seats'].values,
                self.df['usage_rate'].values
            )
            results.append({
                '变量对': '使用座位数 - 使用率',
                '相关系数': round(corr, 4),
                'p值': round(p_value, 4),
                '显著性': '显著' if p_value < 0.05 else '不显著'
            })
        
        return results if results else None
    
    def anova_test_time_slots(self):
        """
        单因素方差分析：检验不同时间段的使用率是否有显著差异
        应用统计方法：单因素ANOVA
        
        H0: 所有时间段的平均使用率相等
        H1: 至少有一个时间段的平均使用率不同
        """
        if self.df.empty or 'time_slot' not in self.df.columns:
            return None
        
        # 按时间段分组
        groups = []
        time_slots = self.df['time_slot'].unique()
        
        for slot in time_slots:
            rates = self.df[self.df['time_slot'] == slot]['usage_rate'].values
            if len(rates) >= 2:  # 至少需要2个样本
                groups.append(rates)
        
        if len(groups) < 2:
            return {
                'test': '单因素ANOVA',
                'result': '时间段数量不足',
                'significant': False
            }
        
        # 执行ANOVA
        f_stat, p_value = scipy_stats.f_oneway(*groups)
        
        return {
            'test': '单因素方差分析 (ANOVA)',
            'f_statistic': round(f_stat, 4),
            'p_value': round(p_value, 4),
            'significant': p_value < 0.05,
            'result': '不同时间段使用率存在显著差异' if p_value < 0.05 else '不同时间段使用率无显著差异',
            'num_groups': len(groups)
        }
